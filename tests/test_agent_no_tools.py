"""Tests for Agent behavior when tools are disabled."""

from __future__ import annotations

from maxagent.config.schema import Config
from maxagent.core.agent import Agent, AgentConfig
from maxagent.llm.models import ChatResponse, ToolCall, ToolCallFunction, Usage
from maxagent.tools.registry import ToolRegistry
from maxagent.utils.context import ContextManager
from maxagent.utils.tokens import TokenTracker


class FakeLLM:
    """Minimal fake LLM client returning a preset response."""

    def __init__(self, response: ChatResponse) -> None:
        self.config = type("Cfg", (), {"model": "fake-model"})()
        self._response = response

    async def chat(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._response


class GuardRegistry(ToolRegistry):
    """Tool registry that counts execute calls."""

    def __init__(self) -> None:
        super().__init__()
        self.execute_calls = 0

    async def execute(self, name, arguments):  # type: ignore[no-untyped-def]
        self.execute_calls += 1
        return await super().execute(name, arguments)


async def test_no_tools_ignores_tool_calls() -> None:
    """When tools are disabled, model tool_calls should be ignored."""
    config = Config()
    config.tools.enabled = []

    agent_config = AgentConfig(system_prompt="", tools=[], max_iterations=1)

    tool_calls = [
        ToolCall(
            id="call-1",
            function=ToolCallFunction(name="read_file", arguments="{}"),
        )
    ]
    response = ChatResponse(
        id="resp-1",
        model="fake-model",
        content=None,
        tool_calls=tool_calls,
        finish_reason="tool_calls",
        usage=Usage(),
    )

    agent = Agent(
        config=config,
        agent_config=agent_config,
        llm_client=FakeLLM(response),  # type: ignore[arg-type]
        tool_registry=GuardRegistry(),
        token_tracker=TokenTracker(),
        context_manager=ContextManager(model="fake-model"),
        auto_compress=False,
    )

    out = await agent.run("hi")
    assert "工具已禁用" in out
    assert agent.tools.execute_calls == 0

