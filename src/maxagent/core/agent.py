"""Core Agent implementation"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

from maxagent.config import Config
from maxagent.llm import LLMClient, LLMConfig, Message, ChatResponse, Usage
from maxagent.tools import ToolRegistry, ToolResult, create_default_registry
from maxagent.core.instructions import load_instructions
from maxagent.core.prompts import build_default_system_prompt
from maxagent.utils.tokens import TokenTracker, get_token_tracker


@dataclass
class AgentConfig:
    """Agent configuration"""

    name: str = "default"
    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)  # Empty = all tools
    max_iterations: int = 10
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
    ) -> None:
        self.config = config
        self.agent_config = agent_config
        self.llm = llm_client
        self.tools = tool_registry
        self.on_tool_call = on_tool_call
        self.messages: list[Message] = []
        # Use provided tracker or global tracker
        self.token_tracker = token_tracker or get_token_tracker()
        # Last response for accessing usage
        self._last_response: Optional[ChatResponse] = None

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

            # Handle tool calls
            if response.tool_calls:
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
            else:
                # No tool calls, return final response
                return response.content or ""

        return "Max iterations reached without completion"

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
        result = await self.run(message)
        # run() now always returns str
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


def create_agent(
    config: Config,
    project_root: Optional[Path] = None,
    agent_name: str = "default",
    llm_client: Optional[LLMClient] = None,
    tool_registry: Optional[ToolRegistry] = None,
    on_tool_call: Optional[Callable[[str, str, ToolResult], None]] = None,
    use_new_prompts: bool = True,
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

    Returns:
        Configured Agent instance
    """
    # Create LLM client if not provided
    if llm_client is None:
        llm_config = LLMConfig(
            base_url=config.litellm.base_url,
            api_key=config.litellm.api_key,
            model=config.model.default,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens,
        )
        llm_client = LLMClient(llm_config)

    # Create tool registry if not provided
    if tool_registry is None:
        root = project_root or Path.cwd()
        tool_registry = create_default_registry(root)

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

    agent_config = AgentConfig(
        name=agent_name,
        system_prompt=system_prompt,
        tools=config.tools.enabled,
    )

    return Agent(
        config=config,
        agent_config=agent_config,
        llm_client=llm_client,
        tool_registry=tool_registry,
        on_tool_call=on_tool_call,
    )
