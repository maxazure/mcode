"""Core Agent implementation"""

from __future__ import annotations

import json
import asyncio
import inspect
import time
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

from maxagent.config import Config
from maxagent.llm import LLMClient, Message, ChatResponse, Usage, create_llm_client
from maxagent.tools import ToolRegistry, ToolResult, create_default_registry
from maxagent.core.instructions import load_instructions
from maxagent.core.prompts import (
    build_architect_prompt,
    build_coder_prompt,
    build_default_system_prompt,
    build_tester_prompt,
)
from maxagent.config.agent_profiles import load_agent_profile
from maxagent.utils.tokens import TokenTracker, get_token_tracker
from maxagent.utils.context import ContextManager, get_context_manager


@dataclass
class AgentConfig:
    """Agent configuration"""

    name: str = "default"
    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)  # Empty = all tools
    max_iterations: int = 100
    temperature: Optional[float] = None  # None = use config default


class Agent:
    """Core Agent class with tool calling support"""

    def __init__(
        self,
        config: Config,
        agent_config: AgentConfig,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        on_tool_call: Optional[Callable[..., None]] = None,
        on_request_end: Optional[Callable[..., None]] = None,
        token_tracker: Optional[TokenTracker] = None,
        context_manager: Optional[ContextManager] = None,
        debug_context: bool = False,
        auto_compress: bool = True,
    ) -> None:
        self.config = config
        self.agent_config = agent_config
        self.llm = llm_client
        self.tools = tool_registry
        self.on_tool_call = on_tool_call
        self.on_request_end = on_request_end
        self.messages: list[Message] = []
        # Use provided tracker or global tracker
        self.token_tracker = token_tracker or get_token_tracker()
        # Use provided context manager or global one
        self.context_manager = context_manager or get_context_manager()
        # Debug mode for context
        self.debug_context = debug_context
        # Auto compression
        self.auto_compress = auto_compress
        # Last response for accessing usage
        self._last_response: Optional[ChatResponse] = None

        # Recent tool call cache to avoid redundant context growth
        self._recent_tool_calls: deque[dict[str, Any]] = deque(maxlen=12)
        # Simple per-file versioning to invalidate cached reads after edits/writes
        self._file_versions: dict[str, int] = {}
        # Track the latest full read_file message per path to avoid keeping multiple full copies
        # of the same file content in the prompt history.
        self._latest_read_file_msg_index: dict[str, int] = {}
        # Track edit counts per file to detect excessive edits pattern
        self._edit_count_per_file: dict[str, int] = {}
        # Threshold for warning about excessive edits (lowered to 2 to enforce batched edits)
        self._excessive_edit_threshold = 2

        # Cache callback arity to support backward-compatible signatures
        self._on_tool_call_accepts_request_id = False
        if self.on_tool_call:
            try:
                self._on_tool_call_accepts_request_id = (
                    len(inspect.signature(self.on_tool_call).parameters) >= 4
                )
            except (TypeError, ValueError):
                self._on_tool_call_accepts_request_id = False

        self._on_request_end_arity = 0
        if self.on_request_end:
            try:
                self._on_request_end_arity = len(inspect.signature(self.on_request_end).parameters)
            except (TypeError, ValueError):
                self._on_request_end_arity = 2

        # Debug logging for tool calls analysis
        self._debug_log_path = os.environ.get("MAXAGENT_DEBUG_LOG")
        if self._debug_log_path:
            self._init_debug_log()

        # Configure context manager with model
        self.context_manager.model = llm_client.config.model
        self.context_manager.debug = debug_context

    def _init_debug_log(self) -> None:
        """Initialize the debug log file."""
        if not self._debug_log_path:
            return
        with open(self._debug_log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"Session started: {datetime.now().isoformat()}\n")
            f.write(f"Model: {self.llm.config.model}\n")
            f.write(f"Agent: {self.agent_config.name}\n")
            f.write(f"{'='*80}\n\n")

    def _log_debug(self, request_id: int, category: str, data: dict[str, Any]) -> None:
        """Write debug information to log file."""
        if not self._debug_log_path:
            return
        try:
            with open(self._debug_log_path, "a", encoding="utf-8") as f:
                f.write(f"[Request {request_id}] {category}\n")
                f.write(json.dumps(data, ensure_ascii=False, indent=2))
                f.write("\n\n")
        except Exception:
            pass  # Silently ignore logging errors

    def _log_llm_response(self, request_id: int, response: ChatResponse) -> None:
        """Log LLM response details for debugging."""
        if not self._debug_log_path:
            return

        tool_calls_info = []
        if response.tool_calls:
            for tc in response.tool_calls:
                # Parse args to extract key info
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = tc.function.arguments

                # Summarize args for readability
                args_summary = {}
                if isinstance(args, dict):
                    for k, v in args.items():
                        if isinstance(v, str) and len(v) > 100:
                            args_summary[k] = f"{v[:50]}...({len(v)} chars)"
                        elif isinstance(v, list):
                            args_summary[k] = f"[{len(v)} items]"
                        else:
                            args_summary[k] = v
                else:
                    args_summary = args

                tool_calls_info.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "args_summary": args_summary,
                    }
                )

        data = {
            "timestamp": datetime.now().isoformat(),
            "tool_calls_count": len(response.tool_calls) if response.tool_calls else 0,
            "tool_calls": tool_calls_info,
            "has_content": bool(response.content),
            "content_preview": response.content[:200] if response.content else None,
            "finish_reason": getattr(response, "finish_reason", None),
        }
        self._log_debug(request_id, "LLM_RESPONSE", data)

    def _emit_tool_callback(
        self, name: str, args: str, result: ToolResult, request_id: int
    ) -> None:
        """Invoke on_tool_call with backward-compatible signature."""
        if not self.on_tool_call:
            return
        if self._on_tool_call_accepts_request_id:
            self.on_tool_call(name, args, result, request_id)
        else:
            self.on_tool_call(name, args, result)

    def _emit_request_end(
        self, request_id: int, response: ChatResponse, elapsed_s: Optional[float] = None
    ) -> None:
        """Invoke on_request_end with flexible signature."""
        if not self.on_request_end:
            return
        stats = self.get_context_stats()
        if elapsed_s is not None:
            stats["elapsed_s"] = elapsed_s
        if self._on_request_end_arity >= 3:
            self.on_request_end(request_id, stats, response)
        elif self._on_request_end_arity == 2:
            self.on_request_end(request_id, stats)
        else:
            self.on_request_end(stats)

    def _normalize_tool_args(self, args: str) -> str:
        """Normalize tool args JSON for stable duplicate detection."""
        if not args:
            return ""
        try:
            parsed = json.loads(args)
            return json.dumps(parsed, sort_keys=True, ensure_ascii=False)
        except Exception:
            return args

    def _extract_path_from_args(self, name: str, args_norm: str) -> Optional[str]:
        """Extract a primary path/file_path from normalized args if present."""
        try:
            parsed = json.loads(args_norm) if args_norm else {}
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        if name == "read_file":
            return parsed.get("path")
        if name == "edit":
            return parsed.get("file_path") or parsed.get("path")
        if name == "write_file":
            return parsed.get("path") or parsed.get("file_path")
        return parsed.get("path") or parsed.get("file_path")

    def _normalize_path_key(self, path: str) -> str:
        """Normalize a path key for per-file tracking."""
        return str(path).strip().lstrip("./")

    def _is_ranged_read_file(self, args_raw: str) -> bool:
        """Whether a read_file call used a line range (start_line/end_line)."""
        try:
            parsed = json.loads(args_raw) if args_raw else {}
        except Exception:
            return False
        if not isinstance(parsed, dict):
            return False
        return parsed.get("start_line") is not None or parsed.get("end_line") is not None

    def _compact_tool_message_content(self, msg: Message, replacement: str) -> None:
        """Replace a tool message's content with a compact placeholder."""
        msg.content = replacement

    def _postprocess_tool_message(
        self,
        tool_msg: Message,
        name: str,
        args_raw: str,
        result: ToolResult,
    ) -> None:
        """Post-process tool messages to reduce redundant context growth.

        - Keep only the latest full `read_file` content per file path (older reads are compacted).
        - After a successful `edit`, update the latest `read_file` content (if present) to reflect the new file.
        """
        if not result.success:
            return

        # Prefer metadata path when available (usually normalized to project-relative)
        path = (result.metadata or {}).get("path") or self._extract_path_from_args(
            name, self._normalize_tool_args(args_raw)
        )
        if not path or not isinstance(path, str):
            return
        path_key = self._normalize_path_key(path)

        if name == "read_file":
            # Only treat full reads as canonical content; ranged reads are usually small snippets.
            if (result.metadata or {}).get("cached"):
                return
            if self._is_ranged_read_file(args_raw):
                return

            prev_idx = self._latest_read_file_msg_index.get(path_key)
            if prev_idx is not None and 0 <= prev_idx < len(self.messages):
                prev_msg = self.messages[prev_idx]
                if (
                    prev_msg is not tool_msg
                    and prev_msg.role == "tool"
                    and prev_msg.name == "read_file"
                ):
                    self._compact_tool_message_content(
                        prev_msg,
                        f"(superseded) read_file for {path_key}; newer content available in a later tool result.",
                    )
            # Current message becomes the canonical full content for this path
            self._latest_read_file_msg_index[path_key] = len(self.messages) - 1
            return

        if name == "edit":
            final_content = (result.metadata or {}).get("final_content")
            if isinstance(final_content, str):
                prev_idx = self._latest_read_file_msg_index.get(path_key)
                if prev_idx is not None and 0 <= prev_idx < len(self.messages):
                    prev_msg = self.messages[prev_idx]
                    if prev_msg.role == "tool" and prev_msg.name == "read_file":
                        prev_msg.content = final_content
            return

        if name == "write_file":
            # If we've previously read this file, keep that content in sync with the write.
            try:
                parsed = json.loads(args_raw) if args_raw else {}
            except Exception:
                parsed = {}
            if isinstance(parsed, dict):
                content = parsed.get("content")
                if isinstance(content, str):
                    prev_idx = self._latest_read_file_msg_index.get(path_key)
                    if prev_idx is not None and 0 <= prev_idx < len(self.messages):
                        prev_msg = self.messages[prev_idx]
                        if prev_msg.role == "tool" and prev_msg.name == "read_file":
                            prev_msg.content = content
            return

    def _append_tool_result_message(
        self,
        tool_call_id: str,
        name: str,
        args_raw: str,
        result: ToolResult,
    ) -> None:
        """Append a tool result message and run post-processing hooks."""
        tool_msg = Message(
            role="tool",
            tool_call_id=tool_call_id,
            name=name,
            content=result.output if result.success else f"Error: {result.error}",
        )
        self.messages.append(tool_msg)
        self._postprocess_tool_message(tool_msg, name, args_raw, result)

    def _build_cache_hit_output(self, name: str, args_norm: str, cached: dict[str, Any]) -> str:
        """Build a compact cache-hit message to avoid re-sending large outputs."""
        path = cached.get("path") or self._extract_path_from_args(name, args_norm)
        if name == "read_file" and path:
            return f"(cache hit) read_file for {path}; content unchanged, see previous output."
        return f"(cache hit) {name} with same arguments; see previous output."

    def _get_recent_cached_result(self, name: str, args_norm: str) -> Optional[ToolResult]:
        """Return a cached ToolResult if this call is a safe recent duplicate."""
        cacheable = {
            "read_file",
            "list_files",
            "search_code",
            "grep",
            "glob",
            "find_files",
            "todoread",
            "todowrite",
        }
        if name not in cacheable:
            return None

        for prev in reversed(self._recent_tool_calls):
            if prev.get("name") == name and prev.get("args_norm") == args_norm:
                # Invalidate cached read_file if file changed since last read
                if name == "read_file":
                    path = prev.get("path")
                    version = prev.get("version", 0)
                    if path and self._file_versions.get(path, 0) != version:
                        return None
                cached_result: ToolResult = prev["result"]
                return ToolResult(
                    success=cached_result.success,
                    output=self._build_cache_hit_output(name, args_norm, prev),
                    error=cached_result.error,
                    metadata={**(cached_result.metadata or {}), "cached": True},
                )
        return None

    def _record_tool_call(self, name: str, args_norm: str, result: ToolResult) -> None:
        """Record a tool call for future duplicate detection."""
        path: Optional[str] = None
        version: Optional[int] = None

        if name in {"edit", "write_file"} and result.success:
            path = self._extract_path_from_args(name, args_norm)
            if path:
                self._file_versions[path] = self._file_versions.get(path, 0) + 1
                # Track edit count for excessive edit detection
                if name == "edit":
                    self._edit_count_per_file[path] = self._edit_count_per_file.get(path, 0) + 1

        if name == "read_file":
            path = self._extract_path_from_args(name, args_norm)
            version = self._file_versions.get(path, 0) if path else 0

        self._recent_tool_calls.append(
            {
                "name": name,
                "args_norm": args_norm,
                "result": result,
                "path": path,
                "version": version,
            }
        )

    def _check_excessive_edits(self, path: str) -> Optional[str]:
        """Check if excessive edits have been made to a file, return warning/error message if so."""
        edit_count = self._edit_count_per_file.get(path, 0)
        if edit_count >= self._excessive_edit_threshold:
            return (
                f"\n\n🚨🚨🚨 CRITICAL VIOLATION: You have made {edit_count} SEPARATE edit calls to '{path}'. "
                f"THIS IS FORBIDDEN! You MUST use the `edits` array parameter to batch ALL changes "
                f"to the same file in ONE edit call.\n\n"
                f"CORRECT PATTERN:\n"
                f"```python\n"
                f"edit(\n"
                f'    file_path="{path}",\n'
                f"    edits=[\n"
                f'        {{"old_string": "...", "new_string": "..."}},\n'
                f'        {{"old_string": "...", "new_string": "..."}},\n'
                f"        # ALL changes in ONE call!\n"
                f"    ]\n"
                f")\n"
                f"```\n\n"
                f"STOP making separate edit calls! Use `edits` array for ALL remaining changes to this file."
            )
        return None

    def _extract_recommended_files_from_text(self, text: str) -> list[str]:
        """Best-effort extract of recommended_files JSON from explore output."""
        import re

        if not text:
            return []
        m = re.search(r"\{[\s\S]*?\"recommended_files\"[\s\S]*?\}", text)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except Exception:
            return []
        rec = data.get("recommended_files")
        if isinstance(rec, list):
            return [str(p) for p in rec if isinstance(p, (str, int))]
        return []

    async def _auto_read_file(self, path: str, request_id: int) -> None:
        """Auto-read a file and inject its content as an assistant message."""
        args_raw = json.dumps({"path": path}, ensure_ascii=False)
        args_norm = self._normalize_tool_args(args_raw)
        cached = self._get_recent_cached_result("read_file", args_norm)
        if cached is not None:
            result = cached
        else:
            result = await self.tools.execute("read_file", args_raw)

        self._record_tool_call("read_file", args_norm, result)
        self._emit_tool_callback("read_file", args_raw, result, request_id)

        if result.success:
            content = result.output
            msg = f"### Auto-loaded recommended file: {path}\n```text\n{content}\n```"
        else:
            msg = f"### Auto-loaded recommended file: {path}\nError: {result.error}"
        self.messages.append(Message(role="assistant", content=msg))

    async def _auto_follow_explore_recommendations(
        self, exec_results: list[tuple[str, str, ToolResult]], request_id: int
    ) -> None:
        """After an explore subagent, auto-read its recommended files."""
        rec_paths: list[str] = []
        for name, args_raw, result in exec_results:
            if name != "subagent" or not result.success:
                continue
            try:
                parsed = json.loads(args_raw) if args_raw else {}
            except Exception:
                parsed = {}
            if isinstance(parsed, dict) and parsed.get("agent_type") == "explore":
                meta_rec = (result.metadata or {}).get("recommended_files")
                if isinstance(meta_rec, list) and meta_rec:
                    rec_paths.extend([str(p) for p in meta_rec])
                else:
                    rec_paths.extend(self._extract_recommended_files_from_text(result.output))

        # Dedupe while preserving order
        ordered: list[str] = []
        for p in rec_paths:
            p_norm = str(p).strip().lstrip("./")
            if p_norm and p_norm not in ordered:
                ordered.append(p_norm)

        if not ordered:
            return

        await asyncio.gather(*(self._auto_read_file(p, request_id) for p in ordered))

    def _tool_planner_enabled(self) -> bool:
        """Check if agent-side tool planner is enabled."""
        return bool(getattr(self.config.model, "enable_tool_planner", False))

    def _is_planner_safe_tool(self, name: str) -> bool:
        """Whether a tool is safe to batch/parallelize."""
        safe_tools = {
            "read_file",
            "list_files",
            "search_code",
            "grep",
            "glob",
            "find_files",
            "webfetch",
            "search_memory",
            "todoread",
            # git read-only tools
            "git_status",
            "git_diff",
            "git_log",
            "git_branch",
        }
        return name in safe_tools

    async def _execute_single_tool_call(self, tool_call: Any) -> tuple[str, str, ToolResult]:
        """Execute one tool call with caching/recording."""
        name = tool_call.function.name
        args_raw = tool_call.function.arguments
        args_norm = self._normalize_tool_args(args_raw)

        cached = self._get_recent_cached_result(name, args_norm)
        if cached is not None:
            result = cached
        else:
            result = await self.tools.execute(name, args_raw)

        self._record_tool_call(name, args_norm, result)

        # Check for excessive edits - REJECT second edit to same file
        if name == "edit" and result.success:
            path = self._extract_path_from_args(name, args_norm)
            if path:
                edit_count = self._edit_count_per_file.get(path, 0)
                if edit_count >= self._excessive_edit_threshold:
                    # Return a FAILURE result to force LLM to use batched edits
                    error_msg = (
                        f"🚨🚨🚨 EDIT REJECTED: You have already edited '{path}' {edit_count} times! "
                        f"This violates the ONE-EDIT-PER-FILE rule.\n\n"
                        f"YOU MUST use the `edits` array parameter to batch ALL changes in ONE call.\n\n"
                        f"CORRECT PATTERN:\n"
                        f"```python\n"
                        f"edit(\n"
                        f'    file_path="{path}",\n'
                        f"    edits=[\n"
                        f'        {{"old_string": "change1_old", "new_string": "change1_new"}},\n'
                        f'        {{"old_string": "change2_old", "new_string": "change2_new"}},\n'
                        f"        # Include ALL your changes here!\n"
                        f"    ]\n"
                        f")\n"
                        f"```\n\n"
                        f"The edit was NOT applied. Please re-read the file and submit ALL changes in ONE edit call with the `edits` array."
                    )
                    result = ToolResult(
                        success=False,
                        output="",
                        error=error_msg,
                        metadata=result.metadata,
                    )

        return name, args_raw, result

    async def _execute_tool_calls(self, tool_calls: list[Any]) -> list[tuple[str, str, ToolResult]]:
        """Execute tool calls, optionally batching independent safe calls."""
        if (
            self._tool_planner_enabled()
            and len(tool_calls) > 1
            and all(self._is_planner_safe_tool(tc.function.name) for tc in tool_calls)
        ):
            # De-duplicate identical safe calls within the same model response
            unique_calls: list[Any] = []
            unique_keys: list[tuple[str, str]] = []
            key_to_index: dict[tuple[str, str], int] = {}

            for tc in tool_calls:
                name = tc.function.name
                args_norm = self._normalize_tool_args(tc.function.arguments)
                key = (name, args_norm)
                if key not in key_to_index:
                    key_to_index[key] = len(unique_calls)
                    unique_calls.append(tc)
                    unique_keys.append(key)

            unique_results = await asyncio.gather(
                *(self._execute_single_tool_call(tc) for tc in unique_calls)
            )

            key_to_result: dict[tuple[str, str], tuple[str, str, ToolResult]] = {
                k: r for k, r in zip(unique_keys, unique_results)
            }

            results: list[tuple[str, str, ToolResult]] = []
            seen_keys: set[tuple[str, str]] = set()
            for tc in tool_calls:
                name = tc.function.name
                args_raw = tc.function.arguments
                args_norm = self._normalize_tool_args(args_raw)
                key = (name, args_norm)
                first = key_to_result[key]
                if key not in seen_keys:
                    results.append(first)
                    seen_keys.add(key)
                else:
                    # Return a lightweight cached result for duplicates
                    cached_out = self._build_cache_hit_output(name, args_norm, {})
                    first_res = first[2]
                    results.append(
                        (
                            name,
                            args_raw,
                            ToolResult(
                                success=first_res.success,
                                output=cached_out,
                                error=first_res.error,
                                metadata={**(first_res.metadata or {}), "cached": True},
                            ),
                        )
                    )

            return results

        results: list[tuple[str, str, ToolResult]] = []
        for tc in tool_calls:
            results.append(await self._execute_single_tool_call(tc))
        return results

    async def run(
        self,
        task: str,
        stream: bool = False,
    ) -> str:
        """
        Run the agent with a task.

        Args:
            task: User task/message
            stream: Whether to stream the response

        Returns:
            Final response string
        """
        # Initialize messages
        self.messages = [
            Message(role="system", content=self.agent_config.system_prompt),
            Message(role="user", content=task),
        ]

        # Get available tools
        tool_schemas = self._get_tool_schemas()

        # Agent loop
        for iteration in range(self.agent_config.max_iterations):
            # Check and display context status before API call
            if self.debug_context:
                from rich.console import Console

                console = self.context_manager.console or Console()
                console.print(
                    f"\n[dim]─── Iteration {iteration + 1}/{self.agent_config.max_iterations} ───[/dim]"
                )
                self.context_manager.display_status(self.messages, console, detailed=True)

            # Auto-compress if needed
            if self.auto_compress and self.context_manager.needs_compression(self.messages):
                if hasattr(self.context_manager, "compress_messages_with_summary"):
                    self.messages = await self.context_manager.compress_messages_with_summary(
                        self.messages, self.llm
                    )
                else:
                    self.messages = self.context_manager.compress_messages(self.messages)

            # Auto-inject relevant memories before model call
            self._inject_relevant_memories()

            request_start = time.perf_counter()
            response = await self.llm.chat(
                messages=self.messages,
                tools=tool_schemas if tool_schemas else None,
                stream=False,  # Tool calling requires non-streaming
                temperature=self.agent_config.temperature,
            )

            # Type assertion for non-streaming response
            assert isinstance(response, ChatResponse)

            # Track token usage
            self._last_response = response
            if response.usage:
                self.token_tracker.add_usage(response.usage, self.llm.config.model)

            request_id = iteration + 1

            # Log LLM response for debugging (run method)
            self._log_llm_response(request_id, response)

            # Handle tool calls (only when tools are enabled for this run)
            if response.tool_calls and tool_schemas:
                # Add assistant message with tool calls
                self.messages.append(
                    Message(
                        role="assistant",
                        content=response.content,
                        tool_calls=response.tool_calls,
                    )
                )

                exec_results = await self._execute_tool_calls(response.tool_calls)

                for tool_call, (name, args_raw, result) in zip(response.tool_calls, exec_results):
                    # Callback for tool execution
                    self._emit_tool_callback(name, args_raw, result, request_id)

                    # Add tool result message (with context de-duplication)
                    self._append_tool_result_message(tool_call.id, name, args_raw, result)
                # If explore subagent returned recommendations, auto-read them now
                await self._auto_follow_explore_recommendations(exec_results, request_id)
                elapsed_s = time.perf_counter() - request_start
                self._emit_request_end(request_id, response, elapsed_s)
            elif response.tool_calls and not tool_schemas:
                # Tools are disabled but the model attempted to call them.
                warning = (
                    "工具已禁用（--no-tools），但模型仍返回了工具调用；"
                    "已忽略这些调用。请重试或启用工具。"
                )
                self.messages.append(Message(role="assistant", content=warning))
                elapsed_s = time.perf_counter() - request_start
                self._emit_request_end(request_id, response, elapsed_s)
                return warning
            else:
                # No tool calls, return final response
                if response.content:
                    self.messages.append(Message(role="assistant", content=response.content))
                elapsed_s = time.perf_counter() - request_start
                self._emit_request_end(request_id, response, elapsed_s)
                return response.content or ""

        return "Max iterations reached without completion"

    async def _continue_conversation(self) -> str:
        """
        Continue the conversation with existing messages.

        Unlike run(), this method does NOT reset self.messages,
        allowing multi-turn conversations to maintain history.

        Returns:
            Final response string
        """
        # Get available tools
        tool_schemas = self._get_tool_schemas()

        # Agent loop
        for iteration in range(self.agent_config.max_iterations):
            # Check and display context status before API call
            if self.debug_context:
                from rich.console import Console

                console = self.context_manager.console or Console()
                console.print(
                    f"\n[dim]─── Iteration {iteration + 1}/{self.agent_config.max_iterations} ───[/dim]"
                )
                self.context_manager.display_status(self.messages, console, detailed=True)

            # Auto-compress if needed
            if self.auto_compress and self.context_manager.needs_compression(self.messages):
                if hasattr(self.context_manager, "compress_messages_with_summary"):
                    self.messages = await self.context_manager.compress_messages_with_summary(
                        self.messages, self.llm
                    )
                else:
                    self.messages = self.context_manager.compress_messages(self.messages)

            # Auto-inject relevant memories before model call
            self._inject_relevant_memories()

            request_start = time.perf_counter()
            response = await self.llm.chat(
                messages=self.messages,
                tools=tool_schemas if tool_schemas else None,
                stream=False,  # Tool calling requires non-streaming
                temperature=self.agent_config.temperature,
            )

            # Type assertion for non-streaming response
            assert isinstance(response, ChatResponse)

            # Track token usage
            self._last_response = response
            if response.usage:
                self.token_tracker.add_usage(response.usage, self.llm.config.model)

            request_id = iteration + 1

            # Log LLM response for debugging (_continue_conversation method)
            self._log_llm_response(request_id, response)

            # Handle tool calls (only when tools are enabled for this run)
            if response.tool_calls and tool_schemas:
                # Add assistant message with tool calls
                self.messages.append(
                    Message(
                        role="assistant",
                        content=response.content,
                        tool_calls=response.tool_calls,
                    )
                )

                exec_results = await self._execute_tool_calls(response.tool_calls)

                for tool_call, (name, args_raw, result) in zip(response.tool_calls, exec_results):
                    # Callback for tool execution
                    self._emit_tool_callback(name, args_raw, result, request_id)

                    # Add tool result message (with context de-duplication)
                    self._append_tool_result_message(tool_call.id, name, args_raw, result)

                await self._auto_follow_explore_recommendations(exec_results, request_id)

                # Emit request-level callback after processing tools
                elapsed_s = time.perf_counter() - request_start
                self._emit_request_end(request_id, response, elapsed_s)
            elif response.tool_calls and not tool_schemas:
                warning = (
                    "工具已禁用（--no-tools），但模型仍返回了工具调用；"
                    "已忽略这些调用。请重试或启用工具。"
                )
                self.messages.append(Message(role="assistant", content=warning))
                elapsed_s = time.perf_counter() - request_start
                self._emit_request_end(request_id, response, elapsed_s)
                return warning
            else:
                # No tool calls, return final response
                # Add assistant response to history for multi-turn conversations
                if response.content:
                    self.messages.append(Message(role="assistant", content=response.content))
                elapsed_s = time.perf_counter() - request_start
                self._emit_request_end(request_id, response, elapsed_s)
                return response.content or ""

        return "Max iterations reached without completion"

    def _inject_relevant_memories(self) -> None:
        """Inject relevant long-term memories into the prompt.

        This looks up `.maxagent/memory.json` using the latest user message
        as query, and inserts a compact memory block right before that user
        message. Older injected memory blocks are removed to avoid growth.
        """
        # Feature gate
        if not getattr(self.context_manager, "enable_memory_injection", False):
            return

        try:
            from maxagent.utils.context_summary import (
                MemoryStore,
                get_project_memory_path,
            )
            from maxagent.utils.context import _truncate_text
        except Exception:
            return

        # Remove previously injected memory blocks
        self.messages = [
            m for m in self.messages if not (m.role == "assistant" and m.name == "memory_context")
        ]

        # Find last user message
        last_user_idx: Optional[int] = None
        last_user_text: Optional[str] = None
        for i in range(len(self.messages) - 1, -1, -1):
            m = self.messages[i]
            if m.role == "user" and m.content:
                last_user_idx = i
                last_user_text = m.content
                break

        if last_user_idx is None or not last_user_text:
            return

        root = self.context_manager.project_root or Path.cwd()
        store = MemoryStore(get_project_memory_path(root))
        top_k = int(getattr(self.context_manager, "memory_top_k", 5) or 5)
        memories = store.search(last_user_text, top_k=top_k)
        if not memories:
            return

        lines = ["## Relevant Memories"]
        for card in memories:
            tags = f" (tags: {', '.join(card.tags)})" if card.tags else ""
            lines.append(f"- [{card.type}] {card.content}{tags}")

        mem_text = "\n".join(lines).strip()
        max_tokens = int(getattr(self.context_manager, "memory_max_tokens", 800) or 800)
        mem_text, _ = _truncate_text(mem_text, max_tokens)

        # Insert before last user message so the final role stays user
        self.messages.insert(
            last_user_idx,
            Message(role="assistant", name="memory_context", content=mem_text),
        )

    async def _stream_final_response(self) -> AsyncIterator[str]:
        """Stream the final response"""
        response_iter = await self.llm.chat(
            messages=self.messages,
            stream=True,
            temperature=self.agent_config.temperature,
        )

        # Type assertion for streaming response
        assert not isinstance(response_iter, ChatResponse)

        async for delta in response_iter:
            if delta.content:
                yield delta.content

    def _get_tool_schemas(self) -> list[dict[str, Any]]:
        """Get tool schemas for enabled tools"""
        if not self.agent_config.tools:
            # Empty = use all enabled tools from config
            enabled_tools = list(self.config.tools.enabled)
        else:
            enabled_tools = list(self.agent_config.tools)

        # Filter out disabled tools
        disabled = set(self.config.tools.disabled)
        enabled_tools = [t for t in enabled_tools if t not in disabled]

        # Auto-include MCP tools (tools starting with "mcp_")
        all_tools = self.tools.list_tools()
        for tool_name in all_tools:
            if tool_name.startswith("mcp_") and tool_name not in enabled_tools:
                enabled_tools.append(tool_name)

        return self.tools.get_openai_schemas(enabled_tools)

    async def chat(
        self,
        message: str,
        history: Optional[list[Message]] = None,
    ) -> str:
        """
        Simple chat method that continues from history.

        Args:
            message: User message
            history: Optional message history

        Returns:
            Assistant response
        """
        if history:
            self.messages = history.copy()
        elif not self.messages:
            self.messages = [
                Message(role="system", content=self.agent_config.system_prompt),
            ]

        self.messages.append(Message(role="user", content=message))
        # Use _continue_conversation instead of run() to preserve history
        result = await self._continue_conversation()
        return result

    def get_history(self) -> list[Message]:
        """Get current message history"""
        return self.messages.copy()

    def clear_history(self) -> None:
        """Clear message history"""
        self.messages = []

    def get_last_usage(self) -> Optional[Usage]:
        """Get usage from the last API response

        Returns:
            Usage object or None if no response yet
        """
        if self._last_response:
            return self._last_response.usage
        return None

    def get_token_stats(self) -> dict:
        """Get accumulated token statistics

        Returns:
            Dictionary with token usage summary
        """
        return self.token_tracker.get_summary()

    def get_context_stats(self) -> dict:
        """Get current context statistics

        Returns:
            Dictionary with context usage info
        """
        stats = self.context_manager.analyze_messages(self.messages)
        return {
            "current_tokens": stats.current_tokens,
            "max_tokens": stats.max_tokens,
            "usage_percent": stats.usage_percent,
            "messages_count": stats.messages_count,
            "remaining_tokens": stats.remaining_tokens,
            "is_near_limit": stats.is_near_limit,
            "model": self.context_manager.model,
        }

    def display_context_status(self, detailed: bool = False) -> None:
        """Display current context status

        Args:
            detailed: Show detailed breakdown
        """
        self.context_manager.display_status(self.messages, detailed=detailed)


def create_agent(
    config: Config,
    project_root: Optional[Path] = None,
    agent_name: str = "default",
    llm_client: Optional[LLMClient] = None,
    tool_registry: Optional[ToolRegistry] = None,
    on_tool_call: Optional[Callable[..., None]] = None,
    on_request_end: Optional[Callable[..., None]] = None,
    use_new_prompts: bool = True,
    yolo_mode: bool = False,
    debug_context: bool = False,
    auto_compress: bool = True,
    max_iterations: Optional[int] = None,
    interactive_mode: bool = True,
) -> Agent:
    """
    Factory function to create an agent.

    Args:
        config: Application configuration
        project_root: Project root directory
        agent_name: Name of agent to use from config
        llm_client: Optional pre-created LLM client
        tool_registry: Optional pre-created tool registry
        on_tool_call: Callback for tool executions
        on_request_end: Callback after each LLM request
        use_new_prompts: Use the new structured prompt system (default True)
        yolo_mode: If True, allow unrestricted file access (YOLO mode)
        debug_context: If True, show context debug info before each API call
        auto_compress: If True, auto-compress context when near limit (default True)
        max_iterations: Maximum tool call iterations (overrides config if provided)
        interactive_mode: If True, agent will ask for plan confirmation (chat mode)
                         If False, agent will auto-execute plans (pipe/headless mode)

    Returns:
        Configured Agent instance
    """
    profile = load_agent_profile(agent_name)

    # Create LLM client if not provided (or if a profile override is present)
    if llm_client is None or (profile and (profile.provider or profile.model)):
        llm_client = create_llm_client(
            config,
            provider_override=(profile.provider if profile else None),
            model_override=(profile.model if profile else None),
        )

    # Create tool registry if not provided
    if tool_registry is None:
        root = project_root or Path.cwd()
        tool_registry = create_default_registry(root, allow_outside_project=yolo_mode)

    root = project_root or Path.cwd()

    # Load project instructions (MAXAGENT.md, AGENTS.md, CLAUDE.md, etc.)
    project_instructions = load_instructions(config.instructions, root)

    if use_new_prompts:
        # Use the new structured prompt system (specialize per agent when available)
        if agent_name == "architect":
            system_prompt = build_architect_prompt(
                working_directory=root,
                project_instructions=project_instructions,
            )
        elif agent_name == "coder":
            system_prompt = build_coder_prompt(
                working_directory=root,
                project_instructions=project_instructions,
            )
        elif agent_name == "tester":
            system_prompt = build_tester_prompt(
                working_directory=root,
                project_instructions=project_instructions,
            )
        else:
            system_prompt = build_default_system_prompt(
                working_directory=root,
                project_instructions=project_instructions,
                tool_registry=tool_registry,
                include_tool_descriptions=False,  # Tool schemas sent separately
                yolo_mode=yolo_mode,
                interactive_mode=interactive_mode,
            )
    else:
        # Legacy: Get agent config from app config
        agent_prompts = config.agents
        if agent_name == "architect":
            system_prompt = agent_prompts.architect.system_prompt
        elif agent_name == "coder":
            system_prompt = agent_prompts.coder.system_prompt
        elif agent_name == "tester":
            system_prompt = agent_prompts.tester.system_prompt
        else:
            system_prompt = agent_prompts.default.system_prompt

        # Append project instructions
        if project_instructions:
            system_prompt = f"{system_prompt}\n\n{project_instructions}"

    # Append user agent profile prompt last (highest priority)
    if profile and profile.system_prompt:
        system_prompt = (
            f"{system_prompt}\n\n{profile.system_prompt}"
            if system_prompt
            else profile.system_prompt
        )

    # Determine max_iterations: CLI arg > config > default
    effective_max_iterations = max_iterations or config.model.max_iterations

    agent_config = AgentConfig(
        name=agent_name,
        system_prompt=system_prompt,
        tools=config.tools.enabled,
        max_iterations=effective_max_iterations,
    )

    # Configure global context manager with project root for memory persistence
    context_manager = get_context_manager()
    context_manager.set_project_root(root)
    # Set config for model-specific context limits
    context_manager.set_config(config)
    # Set provider for provider-specific context limits
    provider = config.litellm.provider
    provider_name = (
        provider.value if hasattr(provider, "value") else str(provider) if provider else None
    )
    if provider_name:
        context_manager.set_provider(provider_name)

    return Agent(
        config=config,
        agent_config=agent_config,
        llm_client=llm_client,
        tool_registry=tool_registry,
        on_tool_call=on_tool_call,
        on_request_end=on_request_end,
        context_manager=context_manager,
        debug_context=debug_context,
        auto_compress=auto_compress,
    )
