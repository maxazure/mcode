"""Tests for recent tool-call de-duplication cache."""

from __future__ import annotations

import pytest

from maxagent.config.schema import Config
from maxagent.core.agent import Agent, AgentConfig
from maxagent.llm.models import ChatResponse, ToolCall, ToolCallFunction, Usage
from maxagent.tools.base import BaseTool, ToolResult
from maxagent.tools.registry import ToolRegistry
from maxagent.utils.context import ContextManager
from maxagent.utils.tokens import TokenTracker


class CountingReadTool(BaseTool):
    """A fake read_file tool that counts executions."""

    name = "read_file"
    description = "fake read"
    parameters = []

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, path: str, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        return ToolResult(success=True, output=f"content for {path}")


class QueueLLM:
    """Fake LLM client returning responses in sequence."""

    def __init__(self, responses: list[ChatResponse]) -> None:
        self.config = type("Cfg", (), {"model": "fake-model"})()
        self._responses = responses
        self._idx = 0

    async def chat(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        resp = self._responses[self._idx]
        self._idx += 1
        return resp


@pytest.mark.asyncio
async def test_recent_duplicate_read_file_is_cached() -> None:
    config = Config()
    config.tools.enabled = ["read_file"]

    agent_config = AgentConfig(system_prompt="", tools=[], max_iterations=3)

    responses = [
        ChatResponse(
            id="resp-1",
            model="fake-model",
            content=None,
            tool_calls=[
                ToolCall(
                    id="call-1",
                    function=ToolCallFunction(
                        name="read_file", arguments='{"path":"a.txt"}'
                    ),
                )
            ],
            finish_reason="tool_calls",
            usage=Usage(),
        ),
        ChatResponse(
            id="resp-2",
            model="fake-model",
            content=None,
            tool_calls=[
                ToolCall(
                    id="call-2",
                    function=ToolCallFunction(
                        name="read_file", arguments='{"path":"a.txt"}'
                    ),
                )
            ],
            finish_reason="tool_calls",
            usage=Usage(),
        ),
        ChatResponse(
            id="resp-3",
            model="fake-model",
            content="done",
            tool_calls=None,
            finish_reason="stop",
            usage=Usage(),
        ),
    ]

    registry = ToolRegistry()
    read_tool = CountingReadTool()
    registry.register(read_tool)

    agent = Agent(
        config=config,
        agent_config=agent_config,
        llm_client=QueueLLM(responses),  # type: ignore[arg-type]
        tool_registry=registry,
        token_tracker=TokenTracker(),
        context_manager=ContextManager(model="fake-model"),
        auto_compress=False,
    )

    out = await agent.run("hi")
    assert out == "done"
    assert read_tool.calls == 1

    tool_msgs = [m for m in agent.messages if m.role == "tool" and m.name == "read_file"]
    assert any(m.content and "(cache hit)" in m.content for m in tool_msgs)

