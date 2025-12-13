"""SubAgent tool for spawning specialized agents during conversation"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional, TYPE_CHECKING, Callable

from .base import BaseTool, ToolParameter, ToolResult

if TYPE_CHECKING:
    from pathlib import Path
    from maxagent.config import Config
    from maxagent.llm import LLMClient
    from maxagent.tools import ToolRegistry


class SubAgentTool(BaseTool):
    """Launch specialized sub-agents for complex, multi-step tasks

    This tool allows the main agent to delegate tasks to specialized agents:
    - explore: Fast agent for codebase exploration and searches
    - architect: Agent for analyzing requirements and designing solutions
    - coder: Agent for generating and modifying code
    - tester: Agent for generating and analyzing tests
    - shell: Agent for running CLI/debugging environment
    - general: General-purpose agent for research and multi-step tasks

    Use this when:
    - A task requires specialized expertise
    - You need to perform parallel independent searches
    - The task is complex and would benefit from focused analysis
    """

    name = "subagent"
    description = """Launch a specialized sub-agent to handle complex tasks autonomously.

Available agent types:
- explore: Fast agent for codebase exploration (finding files, searching code, answering questions about the codebase)
- architect: Analyzes requirements and creates implementation plans
- coder: Generates and modifies code based on specifications
- tester: Creates tests and analyzes test results
- shell: Runs command-line workflows (install deps, run servers/tests) and reports succinctly
- general: General-purpose agent for research and multi-step tasks

The sub-agent will execute the task and return a single result. Use this for:
- Complex multi-step tasks that require focused attention
- Codebase exploration and research
- Code generation or modification tasks
- Test generation tasks

The sub-agent has access to the same tools as the main agent."""

    parameters = [
        ToolParameter(
            name="agent_type",
            type="string",
            description="Type of specialized agent to use",
            enum=["explore", "architect", "coder", "tester", "shell", "general"],
        ),
        ToolParameter(
            name="root",
            type="string",
            description=(
                "Root directory to explore (relative to project root). "
                "Required when agent_type is 'explore'."
            ),
            required=False,
        ),
        ToolParameter(
            name="task",
            type="string",
            description="Detailed task description for the sub-agent to perform",
        ),
        ToolParameter(
            name="context",
            type="string",
            description="Additional context or background information for the task",
            required=False,
            default="",
        ),
    ]
    risk_level = "medium"

    def __init__(
        self,
        project_root: "Path",
        config: "Config",
        llm_client: Optional["LLMClient"] = None,
        tool_registry: Optional["ToolRegistry"] = None,
        max_iterations: int = 50,
        trace: bool = False,
    ) -> None:
        """Initialize the SubAgent tool

        Args:
            project_root: Project root directory
            config: Application configuration
            llm_client: Optional LLM client to share
            tool_registry: Optional tool registry to share
            max_iterations: Max iterations for sub-agent (default 50)
        """
        self.project_root = project_root
        self.config = config
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations
        self.trace = trace

    def _truncate_value(self, value: str, max_len: int = 120) -> str:
        if len(value) <= max_len:
            return value
        return value[: max_len - 3] + "..."

    def _summarize_tool_args(self, name: str, args: str) -> str:
        """Create a compact arg summary for tracing."""
        try:
            parsed = json.loads(args) if args else {}
        except Exception:
            return self._truncate_value(args)

        if not isinstance(parsed, dict):
            return self._truncate_value(str(parsed))

        if name in {"read_file", "write_file"}:
            path = parsed.get("path") or parsed.get("file_path")
            if path:
                return f"path={path}"
        if name == "edit":
            fp = parsed.get("file_path") or parsed.get("path")
            if fp:
                return f"file_path={fp}"

        highlights: list[str] = []
        for key in ("path", "file_path", "pattern", "command", "query", "url", "name"):
            if key in parsed:
                highlights.append(f"{key}={parsed[key]}")
        if highlights:
            return ", ".join(highlights)

        return self._truncate_value(json.dumps(parsed, ensure_ascii=False))

    def _make_trace_callbacks(
        self, agent_type: str
    ) -> tuple[Optional[Callable[..., None]], Optional[Callable[..., None]]]:
        """Build per-subagent trace callbacks for interactive CLI."""
        if not self.trace:
            return None, None

        from rich.console import Console

        console = Console()
        prefix = f"[subagent:{agent_type}] "
        last_request_id: Optional[int] = None

        def on_tool_call(name: str, args: str, result: ToolResult, request_id: int) -> None:
            nonlocal last_request_id
            if request_id != last_request_id:
                console.print(f"[dim]{prefix}── Request {request_id} ──[/dim]")
                last_request_id = request_id
            status = "[green]OK[/green]" if result.success else "[red]FAILED[/red]"
            summary = self._summarize_tool_args(name, args)
            summary_part = f" {summary}" if summary else ""
            console.print(
                f"[dim]{prefix}Tool(req {request_id}): {name}{summary_part} {status}[/dim]"
            )

        def on_request_end(request_id: int, stats: dict, *_: object) -> None:
            try:
                current_tokens = stats.get("current_tokens", 0)
                max_tokens = stats.get("max_tokens", 0)
                usage_percent = stats.get("usage_percent", 0)
                messages_count = stats.get("messages_count", 0)
                remaining = stats.get("remaining_tokens", 0)
                model = stats.get("model")
                elapsed_s = stats.get("elapsed_s")
                elapsed_part = (
                    f", time={elapsed_s:.2f}s" if isinstance(elapsed_s, (int, float)) else ""
                )
                console.print(
                    f"[dim]{prefix}Context(req {request_id}): "
                    f"{current_tokens}/{max_tokens} tokens ({usage_percent:.1f}%), "
                    f"msgs={messages_count}, remaining={remaining}"
                    + (f", model={model}" if model else "")
                    + elapsed_part
                    + "[/dim]"
                )
            except Exception:
                console.print(f"[dim]{prefix}Context(req {request_id}): {stats}[/dim]")

        return on_tool_call, on_request_end

    def _map_agent_type_to_profile_name(self, agent_type: str) -> str:
        # Keep naming consistent with ~/.llc/agents/<name>.md
        mapping = {
            "explore": "explore",
            "architect": "architect",
            "coder": "coder",
            "tester": "tester",
            "shell": "shell",
            "general": "general",
        }
        return mapping.get(agent_type, agent_type or "general")

    def _apply_profile_prompt(self, base_prompt: str, agent_type: str) -> str:
        from maxagent.config.agent_profiles import load_agent_profile

        profile = load_agent_profile(self._map_agent_type_to_profile_name(agent_type))
        if profile and profile.system_prompt:
            return (
                f"{base_prompt}\n\n{profile.system_prompt}"
                if base_prompt
                else profile.system_prompt
            )
        return base_prompt

    def _get_profile_llm_client(self, agent_type: str) -> Optional["LLMClient"]:
        from maxagent.config.agent_profiles import load_agent_profile
        from maxagent.llm import create_llm_client

        profile = load_agent_profile(self._map_agent_type_to_profile_name(agent_type))
        if not profile or not (profile.provider or profile.model):
            return None

        return create_llm_client(
            self.config,
            provider_override=profile.provider,
            model_override=profile.model,
        )

    def _guess_base_path(self, text: str) -> "Path":
        """Best-effort guess of a target directory mentioned in task/context."""
        from pathlib import Path
        import re

        candidates = re.findall(r"[\w\-/\.]+", text)
        # Prefer longer, path-like candidates containing /
        path_like = [c for c in candidates if "/" in c]
        for cand in sorted(path_like, key=len, reverse=True):
            cand = cand.strip("\"'`,.()[]{}")
            if not cand:
                continue
            p = (self.project_root / cand).resolve()
            if p.exists():
                return p if p.is_dir() else p.parent

        # If no explicit path found, try to narrow to a top-level directory
        lowered = text.lower()
        dir_matches: list[tuple[int, Path]] = []
        try:
            for child in self.project_root.iterdir():
                if not child.is_dir():
                    continue
                name = child.name
                if name.startswith("."):
                    continue
                if name.lower() in lowered:
                    dir_matches.append((len(name), child))
        except Exception:
            dir_matches = []

        if dir_matches:
            dir_matches.sort(key=lambda x: x[0], reverse=True)
            return dir_matches[0][1]
        return self.project_root

    def _collect_text_files(
        self, base_path: "Path", respect_gitignore: bool = True
    ) -> list["Path"]:
        """Collect safe, indexable text files under base_path.

        By default, this respects the project-root `.gitignore`. If the exploration
        target itself is ignored and the caller explicitly wants to explore it,
        pass `respect_gitignore=False` to avoid filtering everything out.
        """
        from maxagent.tools.file import SecurityChecker

        checker = SecurityChecker(self.project_root)
        files: list["Path"] = []
        gitignore_patterns = self._load_gitignore_patterns() if respect_gitignore else []
        # Skip common large/vendor/cache dirs even if not hidden
        skip_dir_names = {
            "venv",
            "env",
            "node_modules",
            "dist",
            "build",
            "out",
            "target",
            "__pycache__",
            "site-packages",
            ".git",
            ".venv",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".cache",
            "coverage",
        }

        import os

        # Walk with pruning to avoid traversing ignored dirs
        for dirpath, dirnames, filenames in os.walk(base_path):
            dir_path = type(base_path)(dirpath)

            # Prune dirs in-place
            pruned: list[str] = []
            for d in list(dirnames):
                if d.startswith(".") or d in skip_dir_names:
                    pruned.append(d)
                    continue
                full_dir = dir_path / d
                try:
                    rel_dir = str(full_dir.relative_to(self.project_root))
                except Exception:
                    pruned.append(d)
                    continue
                if gitignore_patterns and self._is_ignored_by_gitignore(
                    rel_dir, gitignore_patterns
                ):
                    pruned.append(d)
            for d in pruned:
                if d in dirnames:
                    dirnames.remove(d)

            for fname in filenames:
                if fname.startswith("."):
                    continue
                p = dir_path / fname
                if any(part.startswith(".") for part in p.parts):
                    continue
                if any(part in skip_dir_names for part in p.parts):
                    continue
                if not p.is_file():
                    continue
                if not checker.is_safe_path(p):
                    continue
                try:
                    rel = str(p.relative_to(self.project_root))
                except Exception:
                    continue
                if gitignore_patterns and self._is_ignored_by_gitignore(rel, gitignore_patterns):
                    continue
                if p.suffix.lower() in {
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".pdf",
                    ".zip",
                    ".tar",
                    ".gz",
                    ".mp4",
                    ".mov",
                    ".ico",
                }:
                    continue
                files.append(p)

        files.sort()
        return files

    def _load_gitignore_patterns(self) -> list[dict[str, Any]]:
        """Load and cache patterns from project-root .gitignore."""
        if hasattr(self, "_gitignore_patterns"):
            return getattr(self, "_gitignore_patterns")  # type: ignore[return-value]

        patterns: list[dict[str, Any]] = []
        gi = self.project_root / ".gitignore"
        try:
            if gi.exists() and gi.is_file():
                for raw_line in gi.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    neg = line.startswith("!")
                    if neg:
                        line = line[1:].strip()
                    if not line or line.startswith("#"):
                        continue
                    dir_only = line.endswith("/")
                    if dir_only:
                        line = line.rstrip("/")
                    anchored = line.startswith("/")
                    if anchored:
                        line = line.lstrip("/")
                    patterns.append(
                        {
                            "pattern": line,
                            "neg": neg,
                            "dir": dir_only,
                            "anchored": anchored,
                        }
                    )
        except Exception:
            patterns = []

        setattr(self, "_gitignore_patterns", patterns)
        return patterns

    def _gitignore_match(self, rel_path: str, pat: dict[str, Any]) -> bool:
        """Approximate gitignore matching for a single pattern."""
        import fnmatch

        pattern = pat.get("pattern") or ""
        if not pattern:
            return False
        is_dir = bool(pat.get("dir"))

        # Directory pattern: ignore everything under that directory.
        if is_dir:
            prefix = pattern + "/"
            if rel_path == pattern or rel_path.startswith(prefix):
                return True
            return fnmatch.fnmatch(rel_path, pattern + "/**")

        # File pattern
        if "/" in pattern:
            return fnmatch.fnmatch(rel_path, pattern)

        name = rel_path.rsplit("/", 1)[-1]
        # Basename match or anywhere match (approx)
        return fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel_path, pattern)

    def _is_ignored_by_gitignore(self, rel_path: str, patterns: list[dict[str, Any]]) -> bool:
        """Apply gitignore patterns in order, honoring negation."""
        ignored = False
        for pat in patterns:
            if self._gitignore_match(rel_path, pat):
                ignored = not bool(pat.get("neg"))
        return ignored

    def _build_tree_text(
        self, base_path: "Path", rel_paths: list[str], max_listed: int = 400
    ) -> str:
        """Build a compact tree/stat snapshot for LLM planning."""
        # Top-level directory counts
        top_counts: dict[str, int] = {}
        ext_counts: dict[str, int] = {}
        root_files: list[str] = []

        for rel in rel_paths:
            parts = rel.split("/")
            top = parts[0] if len(parts) > 1 else "."
            top_counts[top] = top_counts.get(top, 0) + 1
            ext = (rel.rsplit(".", 1)[-1] if "." in rel else "").lower()
            ext_key = f".{ext}" if ext else "(no-ext)"
            ext_counts[ext_key] = ext_counts.get(ext_key, 0) + 1
            if len(parts) == 1:
                root_files.append(rel)

        top_lines = [f"- {k}/ ({v} files)" for k, v in sorted(top_counts.items())]
        ext_lines = [
            f"- {k}: {v}" for k, v in sorted(ext_counts.items(), key=lambda x: (-x[1], x[0]))
        ]
        root_lines = [f"- {p}" for p in sorted(root_files)[:50]]

        listed = rel_paths[:max_listed]
        listed_lines = [f"- {p}" for p in listed]
        truncated_note = ""
        if len(rel_paths) > max_listed:
            truncated_note = (
                f"\n(note: {len(rel_paths) - max_listed} more files omitted from listing)"
            )

        return (
            f"Base directory: {base_path.relative_to(self.project_root)}\n\n"
            f"Top-level dirs:\n" + ("\n".join(top_lines) if top_lines else "- (none)") + "\n\n"
            f"Extensions:\n" + ("\n".join(ext_lines[:30]) if ext_lines else "- (none)") + "\n\n"
            f"Root files:\n" + ("\n".join(root_lines) if root_lines else "- (none)") + "\n\n"
            f"File paths (sample {len(listed)}/{len(rel_paths)}):\n"
            + ("\n".join(listed_lines) if listed_lines else "- (none)")
            + truncated_note
        )

    def _parse_file_selection(self, content: str) -> tuple[list[str], list[str], list[str]]:
        """Parse LLM file selection response into (include_paths, patterns, recommended_files)."""
        import re

        text = (content or "").strip()
        if not text:
            return [], [], []

        # Try direct JSON parse first
        data = None
        try:
            data = json.loads(text)
        except Exception:
            data = None

        if data is None:
            # Extract JSON from fenced block or first {...}/[...] span
            m = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
            candidate = m.group(1).strip() if m else ""
            if not candidate:
                m2 = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
                candidate = m2.group(1).strip() if m2 else ""
            if candidate:
                try:
                    data = json.loads(candidate)
                except Exception:
                    data = None

        include: list[str] = []
        patterns: list[str] = []
        recommended: list[str] = []

        if isinstance(data, list):
            include = [str(x) for x in data if isinstance(x, (str, int))]
        elif isinstance(data, dict):
            raw_inc = data.get("include") or data.get("files") or data.get("paths") or []
            raw_pat = data.get("patterns") or data.get("globs") or []
            raw_rec = (
                data.get("recommended_files")
                or data.get("recommended")
                or data.get("next_read_files")
                or []
            )
            if isinstance(raw_inc, list):
                include = [str(x) for x in raw_inc if isinstance(x, (str, int))]
            if isinstance(raw_pat, list):
                patterns = [str(x) for x in raw_pat if isinstance(x, (str, int))]
            if isinstance(raw_rec, list):
                recommended = [str(x) for x in raw_rec if isinstance(x, (str, int))]

        # Fallback: parse bullet/line list if still empty
        if not include and not patterns and not recommended:
            lines = [ln.strip(" -\t") for ln in text.splitlines() if ln.strip()]
            include = [ln for ln in lines if "/" in ln or "." in ln]

        return include, patterns, recommended

    async def _select_files_with_llm(
        self,
        llm_client: "LLMClient",
        task: str,
        tree_text: str,
        rel_paths: list[str],
        max_files: int = 120,
    ) -> list[str]:
        """Ask LLM to choose relevant files before loading contents."""
        from maxagent.llm.models import Message

        system = (
            "You are a codebase exploration planner. "
            "Given a directory tree and task, choose the most relevant files to read. "
            "Prefer source/config/docs over generated/vendor files."
        )
        user = (
            f"## Exploration task\n{task}\n\n"
            f"## Directory tree / stats\n{tree_text}\n\n"
            "Return JSON only. Acceptable formats:\n"
            '1) ["path1", "path2", ...]  (ordered by importance)\n'
            '2) {"include": ["path1", ...], "patterns": ["glob1", ...], '
            '"recommended_files": ["pathA", ...]}\n\n'
            f"Rules:\n"
            f"- Only choose from the listed file paths or via patterns that match them.\n"
            f"- Keep include list <= {max_files} files.\n"
            f"- Keep recommended_files <= 10 and make it a subset of include/patterns.\n"
            "- Use patterns for groups when many similar files matter.\n"
        )

        resp = await self._chat_with_trace(
            llm_client,
            messages=[Message(role="system", content=system), Message(role="user", content=user)],
            temperature=0.1,
            max_tokens=800,
            label="file selection",
            agent_type="explore",
        )
        include, patterns, recommended = self._parse_file_selection(resp.content or "")

        available_set = set(rel_paths)
        chosen_set: set[str] = set()

        # Add explicit includes
        for p in include:
            p_norm = p.strip().lstrip("./")
            if p_norm in available_set:
                chosen_set.add(p_norm)

        # Apply patterns
        if patterns:
            import fnmatch

            for pat in patterns:
                pat_norm = pat.strip()
                if not pat_norm:
                    continue
                for rel in rel_paths:
                    if fnmatch.fnmatch(rel, pat_norm):
                        chosen_set.add(rel)

        if not chosen_set:
            # Selection failed; fall back to all files
            # Still provide a conservative recommended list for the main agent.
            self._last_recommended_files = rel_paths[:10]  # type: ignore[attr-defined]
            return rel_paths

        # Preserve stable order and cap count
        ordered = [p for p in rel_paths if p in chosen_set]
        ordered = ordered[:max_files]

        # Store a small recommended list for the main agent (<=10)
        rec_set: set[str] = set()
        for p in recommended:
            p_norm = p.strip().lstrip("./")
            if p_norm in available_set:
                rec_set.add(p_norm)
        if not rec_set:
            rec_set.update(ordered[:10])
        self._last_recommended_files = [p for p in ordered if p in rec_set][:10]  # type: ignore[attr-defined]

        return ordered

    def _batch_files_by_tokens(
        self, file_items: list[tuple[str, str, int]], batch_budget: int, max_batches: int = 10
    ) -> tuple[list[list[tuple[str, str, int]]], int]:
        """Batch (path, content, tokens) into groups under batch_budget."""
        batches: list[list[tuple[str, str, int]]] = []
        current: list[tuple[str, str, int]] = []
        current_tokens = 0
        dropped_files = 0

        for item in file_items:
            _, _, toks = item
            if toks <= 0:
                continue
            if current and current_tokens + toks > batch_budget:
                batches.append(current)
                current = []
                current_tokens = 0
            current.append(item)
            current_tokens += toks

        if current:
            batches.append(current)

        if len(batches) > max_batches:
            # Drop tail batches to cap cost; report dropped count.
            for b in batches[max_batches:]:
                dropped_files += len(b)
            batches = batches[:max_batches]

        return batches, dropped_files

    async def _summarize_batch(
        self,
        llm_client: "LLMClient",
        task: str,
        tree_text: str,
        batch: list[tuple[str, str, int]],
        batch_idx: int,
        total_batches: int,
    ) -> str:
        """Call LLM to summarize one batch."""
        from maxagent.llm.models import Message

        file_list = "\n".join([f"- {path} (≈{toks} tok)" for path, _, toks in batch])

        files_blob_parts: list[str] = []
        for path, content, _toks in batch:
            files_blob_parts.append(f"\n### {path}\n```\n{content}\n```")

        files_blob = "\n".join(files_blob_parts)

        system = (
            "You are a codebase exploration summarizer. "
            "Summarize the following batch of files for later merging. "
            "Focus on each file's role, key APIs/classes, and how files relate. "
            "Be concise and structured."
        )

        user = (
            f"## Original exploration task\n{task}\n\n"
            f"## Directory snapshot (partial)\n{tree_text}\n\n"
            f"## Batch {batch_idx + 1}/{total_batches} files\n{file_list}\n\n"
            f"{files_blob}\n\n"
            "Return:\n"
            "1. 5-10 bullet summary of this batch\n"
            "2. Key files in this batch and why they matter"
        )

        resp = await self._chat_with_trace(
            llm_client,
            messages=[Message(role="system", content=system), Message(role="user", content=user)],
            temperature=0.2,
            max_tokens=1200,
            label=f"batch {batch_idx + 1}/{total_batches} summary",
            agent_type="explore",
        )
        return resp.content or ""

    async def _chat_with_retry(
        self,
        llm_client: "LLMClient",
        messages: list["Message"],
        temperature: float,
        max_tokens: int,
        retries: int = 2,
    ) -> "ChatResponse":
        """Call llm_client.chat with small retry/backoff for flaky networks/timeouts."""
        last_exc: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                return await llm_client.chat(
                    messages=messages,
                    tools=None,
                    stream=False,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )  # type: ignore[return-value]
            except Exception as e:  # noqa: BLE001
                last_exc = e
                if attempt >= retries:
                    raise
                # linear backoff to avoid thundering herd
                await asyncio.sleep(1.5 * (attempt + 1))
        assert last_exc is not None
        raise last_exc

    async def _chat_with_trace(
        self,
        llm_client: "LLMClient",
        messages: list["Message"],
        temperature: float,
        max_tokens: int,
        label: str,
        agent_type: str,
    ) -> "ChatResponse":
        """Chat with retry and optional per-call trace + cost output."""
        # Increment per-exploration request id
        if not hasattr(self, "_internal_llm_request_id"):
            self._internal_llm_request_id = 0  # type: ignore[attr-defined]
        self._internal_llm_request_id += 1  # type: ignore[attr-defined]
        req_id = self._internal_llm_request_id  # type: ignore[attr-defined]

        console = None
        if self.trace:
            # Use plain print for robustness under rich Live/status.
            print(
                f"[subagent:{agent_type}] ── LLM Request {req_id} ({label}) ──",
                flush=True,
            )

        resp = await self._chat_with_retry(
            llm_client,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Track and show usage/cost if available
        try:
            from maxagent.utils.tokens import get_token_tracker

            if resp.usage and resp.usage.total_tokens > 0:
                tracker = get_token_tracker()
                tracker.add_usage(resp.usage, llm_client.config.model)
                if self.trace:
                    line = tracker.format_last(resp.usage, llm_client.config.model)
                    # strip rich dim tags if any
                    line = line.replace("[dim]", "").replace("[/dim]", "")
                    print(line, flush=True)
        except Exception:
            # Never fail exploration due to tracing
            pass

        return resp

    async def _run_batched_explore(
        self, llm_client: "LLMClient", full_task: str, root: Optional[str] = None
    ) -> str:
        """Efficient exploration: tree + token batching + map-reduce summaries."""
        from maxagent.utils.context import estimate_tokens, get_model_context_limit

        if root:
            # Security: only allow relative paths within project
            root_norm = root.strip()
            # If root is project-wide (.), try to narrow based on task text.
            if root_norm in {".", "./"}:
                base_path = self._guess_base_path(full_task)
            else:
                if root_norm.startswith("~") or root_norm.startswith("/") or ".." in root_norm:
                    return f"Invalid explore root: {root_norm}"
                base_path = (self.project_root / root_norm).resolve()
                try:
                    base_path.relative_to(self.project_root)
                except ValueError:
                    return f"Explore root outside project: {root_norm}"
                if not base_path.exists():
                    return f"Explore root not found: {root_norm}"
                if base_path.is_file():
                    base_path = base_path.parent
        else:
            base_path = self._guess_base_path(full_task)

        # Respect .gitignore unless it would filter out the entire target base_path.
        # Many repos ignore demo/build dirs, but users may explicitly ask to explore them.
        respect_gitignore = True
        gitignore_patterns = self._load_gitignore_patterns()
        try:
            base_rel = str(base_path.relative_to(self.project_root))
        except Exception:
            base_rel = ""
        if (
            gitignore_patterns
            and base_rel
            and base_rel not in {".", ""}
            and self._is_ignored_by_gitignore(base_rel, gitignore_patterns)
        ):
            respect_gitignore = False

        files = self._collect_text_files(base_path, respect_gitignore=respect_gitignore)

        # Convert to relative string paths for planning
        rel_paths = [str(p.relative_to(self.project_root)) for p in files]

        if not rel_paths:
            return "No readable project files found for exploration."

        # Reset internal request id for this exploration run (selection + summaries)
        self._internal_llm_request_id = 0
        # Clear previous recommended files
        self._last_recommended_files = []  # type: ignore[attr-defined]

        tree_text = self._build_tree_text(base_path, rel_paths)

        # Ask LLM to select relevant files before loading contents
        selected_rel_paths = await self._select_files_with_llm(
            llm_client,
            task=full_task,
            tree_text=tree_text,
            rel_paths=rel_paths,
        )

        selected_set = set(selected_rel_paths)

        # Read and estimate tokens only for selected files
        file_items: list[tuple[str, str, int]] = []
        max_file_bytes = 200_000  # avoid huge blobs
        for p in files:
            rel = str(p.relative_to(self.project_root))
            if rel not in selected_set:
                continue
            try:
                size = p.stat().st_size
                if size > max_file_bytes:
                    # Read head/tail only for large text files
                    text = p.read_text(encoding="utf-8", errors="replace")
                    head = text[:8000]
                    tail = text[-4000:] if len(text) > 12000 else ""
                    content = head + ("\n...[truncated]...\n" + tail if tail else "")
                else:
                    content = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            toks = estimate_tokens(content)
            file_items.append((rel, content, toks))

        if not file_items:
            return "No readable selected files found for exploration."

        total_tokens = sum(t for _, _, t in file_items)
        limit = get_model_context_limit(llm_client.config.model)
        # Keep headroom for prompt overhead
        batch_budget = int(limit * 0.75)

        batches, dropped = self._batch_files_by_tokens(
            file_items, batch_budget=batch_budget, max_batches=10
        )

        batch_summaries: list[str] = []
        for i, batch in enumerate(batches):
            batch_summaries.append(
                await self._summarize_batch(
                    llm_client,
                    task=full_task,
                    tree_text=tree_text,
                    batch=batch,
                    batch_idx=i,
                    total_batches=len(batches),
                )
            )

        # Reduce step: merge summaries (skip if only one batch)
        merged: str
        if len(batch_summaries) == 1:
            merged = batch_summaries[0]
        else:
            from maxagent.llm.models import Message

            reduce_system = (
                "You are an expert codebase exploration agent. "
                "Merge the batch summaries into a single coherent overview. "
                "Then list the <=10 most important files for the main agent to read next."
            )
            reduce_user = (
                f"## Original task\n{full_task}\n\n"
                f"## Directory snapshot\n{tree_text}\n\n"
                f"## Batch summaries ({len(batch_summaries)} batches, total≈{total_tokens} tok)\n\n"
                + "\n\n---\n\n".join(
                    [f"### Batch {i+1}\n{s}" for i, s in enumerate(batch_summaries)]
                )
                + (f"\n\nNote: {dropped} files were omitted due to batch cap." if dropped else "")
            )

            final_resp = await self._chat_with_trace(
                llm_client,
                messages=[
                    Message(role="system", content=reduce_system),
                    Message(role="user", content=reduce_user),
                ],
                temperature=0.2,
                max_tokens=1500,
                label="reduce merge",
                agent_type="explore",
            )
            merged = final_resp.content or ""

        batches_block = "\n\n".join([f"## Batch {i+1}\n{s}" for i, s in enumerate(batch_summaries)])
        rec_files: list[str] = []
        try:
            rec_files = list(getattr(self, "_last_recommended_files", []))
        except Exception:
            rec_files = []
        if not rec_files:
            rec_files = selected_rel_paths[:10]

        rec_json = json.dumps({"recommended_files": rec_files}, ensure_ascii=False)

        return (
            f"### Batched Exploration Summaries\n{batches_block}\n\n"
            f"### Merged Overview\n{merged}\n\n"
            f"### Recommended Files for Main Agent (read all at once)\n"
            f"```json\n{rec_json}\n```"
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute a task using a specialized sub-agent

        Args:
            agent_type: Type of agent (explore, architect, coder, tester, shell, general)
            task: Task description
            context: Additional context

        Returns:
            ToolResult with the sub-agent's response
        """
        agent_type = kwargs.get("agent_type", "general")
        root = kwargs.get("root")
        task = kwargs.get("task", "")
        context = kwargs.get("context", "")

        if not task:
            return ToolResult(
                success=False,
                output="",
                error="Task description is required",
            )

        if agent_type == "explore" and not root:
            return ToolResult(
                success=False,
                output="",
                error="Parameter 'root' is required for explore subagent",
                metadata={"agent_type": agent_type},
            )

        try:
            # Import here to avoid circular imports
            from maxagent.core.agent import Agent, AgentConfig, create_agent
            from maxagent.llm import LLMClient, create_llm_client
            from maxagent.tools import create_default_registry

            # Build the full task with context
            full_task = task
            if context:
                full_task = f"""## Context
{context}

## Task
{task}"""

            # Create/select LLM client (profile override > shared > default)
            llm_client = self._get_profile_llm_client(agent_type) or self.llm_client
            if llm_client is None:
                llm_client = create_llm_client(self.config)

            # Create tool registry if not provided
            tool_registry = self.tool_registry
            if tool_registry is None:
                tool_registry = create_default_registry(self.project_root)

            trace_tool_cb, trace_req_cb = self._make_trace_callbacks(agent_type)

            # Create the appropriate agent based on type
            if agent_type == "explore":
                # High-efficiency exploration: tree + token batching + summaries
                result = await self._run_batched_explore(llm_client, full_task, root=root)
                rec_files: list[str] = []
                try:
                    rec_files = list(getattr(self, "_last_recommended_files", []))
                except Exception:
                    rec_files = []
                return ToolResult(
                    success=True,
                    output=result,
                    metadata={
                        "agent_type": agent_type,
                        "task": task[:100] + "..." if len(task) > 100 else task,
                        "recommended_files": rec_files,
                    },
                )

            elif agent_type == "architect":
                agent_config = AgentConfig(
                    name="architect",
                    system_prompt=self._apply_profile_prompt(
                        self._get_architect_prompt(), agent_type
                    ),
                    tools=["read_file", "list_files", "search_code", "grep", "glob"],
                    max_iterations=self.max_iterations,
                    temperature=0.3,
                )
                agent = Agent(
                    config=self.config,
                    agent_config=agent_config,
                    llm_client=llm_client,
                    tool_registry=tool_registry,
                    on_tool_call=trace_tool_cb,
                    on_request_end=trace_req_cb,
                )

            elif agent_type == "coder":
                agent_config = AgentConfig(
                    name="coder",
                    system_prompt=self._apply_profile_prompt(self._get_coder_prompt(), agent_type),
                    tools=["read_file", "list_files", "search_code", "write_file", "grep", "glob"],
                    max_iterations=self.max_iterations,
                    temperature=0.2,
                )
                agent = Agent(
                    config=self.config,
                    agent_config=agent_config,
                    llm_client=llm_client,
                    tool_registry=tool_registry,
                    on_tool_call=trace_tool_cb,
                    on_request_end=trace_req_cb,
                )

            elif agent_type == "tester":
                agent_config = AgentConfig(
                    name="tester",
                    system_prompt=self._apply_profile_prompt(self._get_tester_prompt(), agent_type),
                    tools=["read_file", "list_files", "search_code", "run_command", "grep", "glob"],
                    max_iterations=self.max_iterations,
                    temperature=0.2,
                )
                agent = Agent(
                    config=self.config,
                    agent_config=agent_config,
                    llm_client=llm_client,
                    tool_registry=tool_registry,
                    on_tool_call=trace_tool_cb,
                    on_request_end=trace_req_cb,
                )

            elif agent_type == "shell":
                agent_config = AgentConfig(
                    name="shell",
                    system_prompt=self._apply_profile_prompt(self._get_shell_prompt(), agent_type),
                    tools=["run_command", "read_file", "list_files", "grep", "glob"],
                    max_iterations=self.max_iterations,
                    temperature=0.2,
                )
                agent = Agent(
                    config=self.config,
                    agent_config=agent_config,
                    llm_client=llm_client,
                    tool_registry=tool_registry,
                    on_tool_call=trace_tool_cb,
                    on_request_end=trace_req_cb,
                )

            else:  # general
                agent_config = AgentConfig(
                    name="general",
                    system_prompt=self._apply_profile_prompt(
                        self._get_general_prompt(), agent_type
                    ),
                    tools=[],  # Empty means all tools
                    max_iterations=self.max_iterations,
                    temperature=0.5,
                )
                agent = Agent(
                    config=self.config,
                    agent_config=agent_config,
                    llm_client=llm_client,
                    tool_registry=tool_registry,
                    on_tool_call=trace_tool_cb,
                    on_request_end=trace_req_cb,
                )

            # Execute the task
            result = await agent.run(full_task)

            return ToolResult(
                success=True,
                output=result,
                metadata={
                    "agent_type": agent_type,
                    "task": task[:100] + "..." if len(task) > 100 else task,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"SubAgent execution failed: {str(e)}",
                metadata={"agent_type": agent_type},
            )

    def _get_explore_prompt(self) -> str:
        """Get specialized prompt for exploration agent"""
        return """You are an Exploration Agent specialized in quickly finding information in codebases.

Your strengths:
- Fast file pattern matching using glob patterns
- Efficient code searching using grep/ripgrep
- Understanding codebase structure
- Locating specific functions, classes, or patterns

Instructions:
1. Use glob to find files by name patterns (e.g., "**/*.py", "src/**/*.ts")
2. Use grep to search for code patterns (e.g., function names, imports)
3. Use read_file to examine specific files when needed
4. Provide concise, focused answers

Be thorough but efficient. Return only the relevant information requested."""

    def _get_architect_prompt(self) -> str:
        """Get specialized prompt for architect agent"""
        return """You are a Senior Software Architect Agent.

Your responsibilities:
1. Analyze requirements and understand what needs to be done
2. Explore the codebase to understand the project structure
3. Identify relevant files and modules
4. Create detailed implementation plans
5. Identify potential risks and suggest mitigations

Use the available tools to:
- Read existing code to understand patterns
- Search for related functionality
- List files to understand project structure

Output Format:
- Requirements Understanding
- Files Involved
- Implementation Steps
- Potential Risks
- Testing Strategy

Be thorough but concise. Use tools to gather information before making recommendations."""

    def _get_coder_prompt(self) -> str:
        """Get specialized prompt for coder agent"""
        return """You are an Expert Software Engineer Agent.

Your responsibilities:
1. Write high-quality, clean, maintainable code
2. Follow project coding conventions and patterns
3. Generate code changes in unified diff format when modifying existing files
4. Handle edge cases and error scenarios

Guidelines:
1. Read the relevant files FIRST before making changes
2. Understand existing code structure and style
3. Make minimal, focused changes
4. Add helpful comments for complex logic
5. Follow project conventions

Output code changes as unified diff patches when modifying existing files:
```diff
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -10,6 +10,8 @@
 existing line
+new line
 existing line
```"""

    def _get_tester_prompt(self) -> str:
        """Get specialized prompt for tester agent"""
        return """You are an Expert Test Engineer Agent.

Your responsibilities:
1. Generate comprehensive test cases
2. Cover normal paths, edge cases, and error scenarios
3. Follow project testing conventions
4. Use the project's testing framework

Guidelines:
1. Read existing tests FIRST to understand conventions
2. Match the testing framework and style used in the project
3. Create focused, single-purpose tests
4. Include docstrings explaining what each test verifies
5. Test both success and failure scenarios

Generate tests as complete, runnable code that can be directly added to test files."""

    def _get_shell_prompt(self) -> str:
        """Get specialized prompt for shell/CLI agent"""
        return """You are a Command-Line SubAgent specialized in running shell workflows safely and efficiently.

Your responsibilities:
1. Execute necessary commands via `run_command`
2. Diagnose environment/dependency issues (pip/npm/uvicorn/etc.)
3. Keep command output noise low by summarizing
4. Return a clear, actionable report to the main agent

## Python Testing Commands

**IMPORTANT**: 
1. If the project has a `.venv` directory, always use `.venv/bin/python -m pytest`
2. Use `timeout=120` for running all tests (default 30s is often too short)

```python
# First check for .venv
list_files(path=".")  # Look for .venv/ directory

# Run all tests with longer timeout
run_command(command=".venv/bin/python -m pytest tests/ -v --tb=short", timeout=120)

# Run specific test file
run_command(command=".venv/bin/python -m pytest tests/test_module.py -v --tb=short")

# Run and stop at first failure
run_command(command=".venv/bin/python -m pytest tests/ -x -v --tb=short")

# Run with coverage (needs longer timeout)
run_command(command=".venv/bin/python -m pytest tests/ --cov=src --cov-report=term-missing", timeout=180)
```

## Guidelines
1. Prefer whitelisted, non-destructive commands; avoid risky operations unless explicitly required
2. Batch related commands when possible (e.g., check python version, then pip list, then install)
3. If a command output is long, summarize key lines and omit the rest
4. Always state what you ran and the outcome
5. Suggest next steps if something fails
6. For Python projects, use `python -m` prefix for tools (pytest, pip, etc.)

Output format:
- Commands run (with cwd if relevant)
- Key findings / errors
- Suggested fixes or next actions
Be concise."""

    def _get_general_prompt(self) -> str:
        """Get specialized prompt for general agent"""
        return """You are a General-Purpose Research Agent.

Your responsibilities:
1. Research and gather information
2. Analyze complex problems
3. Execute multi-step tasks autonomously
4. Provide comprehensive answers

You have access to all available tools. Use them efficiently to:
- Search and explore the codebase
- Read and analyze files
- Execute commands when needed
- Fetch web content for research

Be thorough and systematic in your approach. Return a comprehensive result when done."""


class TaskTool(BaseTool):
    """Alias for SubAgent tool with task-oriented interface

    This provides a simpler interface focused on launching autonomous tasks.
    """

    name = "task"
    description = """Launch an autonomous agent to handle a complex task.

This tool spawns a specialized agent that will:
1. Analyze the task requirements
2. Use available tools to gather information
3. Execute the necessary steps
4. Return a comprehensive result

Best used for:
- Multi-step research tasks
- Code exploration and analysis
- Complex file operations
- Tasks requiring multiple tool calls

The agent works autonomously and returns when complete."""

    parameters = [
        ToolParameter(
            name="description",
            type="string",
            description="Short (3-5 words) description of the task",
        ),
        ToolParameter(
            name="root",
            type="string",
            description=(
                "Root directory to explore (relative to project root). "
                "Required when agent_type is 'explore'."
            ),
            required=False,
        ),
        ToolParameter(
            name="prompt",
            type="string",
            description="Detailed task instructions for the agent",
        ),
        ToolParameter(
            name="agent_type",
            type="string",
            description="Type of agent: explore (fast searches), general (research), coder (code changes)",
            required=False,
            default="general",
            enum=["explore", "general", "coder", "architect", "tester", "shell"],
        ),
    ]
    risk_level = "medium"

    def __init__(
        self,
        project_root: "Path",
        config: "Config",
        llm_client: Optional["LLMClient"] = None,
        tool_registry: Optional["ToolRegistry"] = None,
        max_iterations: int = 50,
        trace: bool = False,
    ) -> None:
        self.subagent = SubAgentTool(
            project_root=project_root,
            config=config,
            llm_client=llm_client,
            tool_registry=tool_registry,
            max_iterations=max_iterations,
            trace=trace,
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute an autonomous task

        Args:
            description: Short task description
            prompt: Detailed task instructions
            agent_type: Type of agent to use

        Returns:
            ToolResult with the task output
        """
        description = kwargs.get("description", "")
        root = kwargs.get("root")
        prompt = kwargs.get("prompt", "")
        agent_type = kwargs.get("agent_type", "general")

        return await self.subagent.execute(
            agent_type=agent_type,
            root=root,
            task=prompt,
            context=f"Task: {description}",
        )
