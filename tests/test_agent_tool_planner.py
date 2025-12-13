"""Tests for optional agent-side tool planner (batching safe tool calls)."""

from __future__ import annotations

import asyncio

import pytest

from maxagent.config.schema import Config
from maxagent.core.agent import Agent, AgentConfig
from maxagent.llm.models import ChatResponse, ToolCall, ToolCallFunction, Usage
from maxagent.tools.base import BaseTool, ToolResult
from maxagent.tools.registry import ToolRegistry
from maxagent.utils.context import ContextManager
from maxagent.utils.tokens import TokenTracker


class ConcurrencyCounter:
    def __init__(self) -> None:
        self.current = 0
        self.max_seen = 0

    def inc(self) -> None:
        self.current += 1
        self.max_seen = max(self.max_seen, self.current)

    def dec(self) -> None:
        self.current -= 1


class SafeTool(BaseTool):
    """A fake safe tool that yields to event loop."""

    def __init__(self, name: str, counter: ConcurrencyCounter) -> None:
        self.name = name
        self.description = "safe"
        self.parameters = []
        self._counter = counter

    async def execute(self, **kwargs):  # type: ignore[no-untyped-def]
        self._counter.inc()
        # Yield so other tasks can start if run in parallel
        await asyncio.sleep(0.05)
        self._counter.dec()
        return ToolResult(success=True, output="ok")


class QueueLLM:
    def __init__(self, responses: list[ChatResponse]) -> None:
        self.config = type("Cfg", (), {"model": "fake-model"})()
        self._responses = responses
        self._idx = 0

    async def chat(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        resp = self._responses[self._idx]
        self._idx += 1
        return resp


@pytest.mark.asyncio
async def test_tool_planner_parallelizes_safe_calls_when_enabled() -> None:
    config = Config()
    config.model.enable_tool_planner = True
    config.tools.enabled = ["read_file", "list_files"]

    agent_config = AgentConfig(system_prompt="", tools=[], max_iterations=2)

    responses = [
        ChatResponse(
            id="resp-1",
            model="fake-model",
            content=None,
            tool_calls=[
                ToolCall(
                    id="call-1",
                    function=ToolCallFunction(name="read_file", arguments="{}"),
                ),
                ToolCall(
                    id="call-2",
                    function=ToolCallFunction(name="list_files", arguments="{}"),
                ),
            ],
            finish_reason="tool_calls",
            usage=Usage(),
        ),
        ChatResponse(
            id="resp-2",
            model="fake-model",
            content="done",
            tool_calls=None,
            finish_reason="stop",
            usage=Usage(),
        ),
    ]

    counter = ConcurrencyCounter()
    registry = ToolRegistry()
    registry.register(SafeTool("read_file", counter))
    registry.register(SafeTool("list_files", counter))

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
    assert counter.max_seen >= 2

