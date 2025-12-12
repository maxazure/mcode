"""Core Agent implementation"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

from maxagent.config import Config
from maxagent.llm import LLMClient, Message, ChatResponse, Usage, create_llm_client
from maxagent.tools import ToolRegistry, ToolResult, create_default_registry
from maxagent.core.instructions import load_instructions
from maxagent.core.prompts import build_default_system_prompt
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
        on_tool_call: Optional[Callable[[str, str, ToolResult], None]] = None,
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

        # Configure context manager with model
        self.context_manager.model = llm_client.config.model
        self.context_manager.debug = debug_context

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

                # Execute each tool call
                for tool_call in response.tool_calls:
                    result = await self.tools.execute(
                        tool_call.function.name,
                        tool_call.function.arguments,
                    )

                    # Callback for tool execution
                    if self.on_tool_call:
                        self.on_tool_call(
                            tool_call.function.name,
                            tool_call.function.arguments,
                            result,
                        )

                    # Add tool result message
                    self.messages.append(
                        Message(
                            role="tool",
                            tool_call_id=tool_call.id,
                            name=tool_call.function.name,
                            content=result.output if result.success else f"Error: {result.error}",
                        )
                    )
            elif response.tool_calls and not tool_schemas:
                # Tools are disabled but the model attempted to call them.
                warning = (
                    "工具已禁用（--no-tools），但模型仍返回了工具调用；"
                    "已忽略这些调用。请重试或启用工具。"
                )
                self.messages.append(Message(role="assistant", content=warning))
                return warning
            else:
                # No tool calls, return final response
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

                # Execute each tool call
                for tool_call in response.tool_calls:
                    result = await self.tools.execute(
                        tool_call.function.name,
                        tool_call.function.arguments,
                    )

                    # Callback for tool execution
                    if self.on_tool_call:
                        self.on_tool_call(
                            tool_call.function.name,
                            tool_call.function.arguments,
                            result,
                        )

                    # Add tool result message
                    self.messages.append(
                        Message(
                            role="tool",
                            tool_call_id=tool_call.id,
                            name=tool_call.function.name,
                            content=result.output if result.success else f"Error: {result.error}",
                        )
                    )
            elif response.tool_calls and not tool_schemas:
                warning = (
                    "工具已禁用（--no-tools），但模型仍返回了工具调用；"
                    "已忽略这些调用。请重试或启用工具。"
                )
                self.messages.append(Message(role="assistant", content=warning))
                return warning
            else:
                # No tool calls, return final response
                # Add assistant response to history for multi-turn conversations
                if response.content:
                    self.messages.append(
                        Message(role="assistant", content=response.content)
                    )
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
            m
            for m in self.messages
            if not (m.role == "assistant" and m.name == "memory_context")
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
    on_tool_call: Optional[Callable[[str, str, ToolResult], None]] = None,
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
    # Create LLM client if not provided
    if llm_client is None:
        llm_client = create_llm_client(config)

    # Create tool registry if not provided
    if tool_registry is None:
        root = project_root or Path.cwd()
        tool_registry = create_default_registry(root, allow_outside_project=yolo_mode)

    root = project_root or Path.cwd()

    # Load project instructions (MAXAGENT.md, AGENTS.md, CLAUDE.md, etc.)
    project_instructions = load_instructions(config.instructions, root)

    if use_new_prompts:
        # Use the new structured prompt system
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

    return Agent(
        config=config,
        agent_config=agent_config,
        llm_client=llm_client,
        tool_registry=tool_registry,
        on_tool_call=on_tool_call,
        context_manager=context_manager,
        debug_context=debug_context,
        auto_compress=auto_compress,
    )
