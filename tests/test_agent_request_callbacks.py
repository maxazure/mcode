"""Tests for per-request and per-tool callbacks."""

from __future__ import annotations

import json

import pytest

from maxagent.config.schema import Config
from maxagent.core.agent import Agent, AgentConfig
from maxagent.llm.models import ChatResponse, ToolCall, ToolCallFunction, Usage
from maxagent.tools.base import BaseTool, ToolResult
from maxagent.tools.registry import ToolRegistry
from maxagent.utils.context import ContextManager
from maxagent.utils.tokens import TokenTracker


class DummyTool(BaseTool):
    name = "dummy"
    description = "dummy tool"
    parameters = []

    async def execute(self, **kwargs):  # type: ignore[no-untyped-def]
        return ToolResult(success=True, output="ok")


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
async def test_tool_and_request_callbacks_include_request_id_and_elapsed(monkeypatch) -> None:
    import maxagent.core.agent as agent_module

    # Deterministic perf_counter for two iterations
    times = iter([0.0, 1.2, 2.0, 2.5])
    monkeypatch.setattr(agent_module.time, "perf_counter", lambda: next(times))

    config = Config()
    config.tools.enabled = ["dummy"]

    agent_config = AgentConfig(system_prompt="", tools=[], max_iterations=2)

    tool_calls = [
        ToolCall(id="call-1", function=ToolCallFunction(name="dummy", arguments="{}")),
        ToolCall(id="call-2", function=ToolCallFunction(name="dummy", arguments="{}")),
    ]

    responses = [
        ChatResponse(
            id="resp-1",
            model="fake-model",
            content=None,
            tool_calls=tool_calls,
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

    registry = ToolRegistry()
    registry.register(DummyTool())

    tool_requests: list[int] = []
    request_stats: list[tuple[int, dict]] = []

    def on_tool_call(name: str, args: str, result: ToolResult, request_id: int) -> None:
        tool_requests.append(request_id)

    def on_request_end(request_id: int, stats: dict) -> None:
        request_stats.append((request_id, stats))

    agent = Agent(
        config=config,
        agent_config=agent_config,
        llm_client=QueueLLM(responses),  # type: ignore[arg-type]
        tool_registry=registry,
        on_tool_call=on_tool_call,
        on_request_end=on_request_end,
        token_tracker=TokenTracker(),
        context_manager=ContextManager(model="fake-model"),
        auto_compress=False,
    )

    out = await agent.run("hi")
    assert out == "done"

    assert tool_requests == [1, 1]
    assert [rid for rid, _ in request_stats] == [1, 2]
    assert request_stats[0][1]["elapsed_s"] == 1.2
    assert request_stats[1][1]["elapsed_s"] == 0.5


@pytest.mark.asyncio
async def test_on_tool_call_backwards_compatible_three_args(monkeypatch) -> None:
    import maxagent.core.agent as agent_module

    times = iter([0.0, 0.1])
    monkeypatch.setattr(agent_module.time, "perf_counter", lambda: next(times))

    config = Config()
    config.tools.enabled = ["dummy"]
    agent_config = AgentConfig(system_prompt="", tools=[], max_iterations=1)

    responses = [
        ChatResponse(
            id="resp-1",
            model="fake-model",
            content=None,
            tool_calls=[
                ToolCall(id="call-1", function=ToolCallFunction(name="dummy", arguments="{}"))
            ],
            finish_reason="tool_calls",
            usage=Usage(),
        )
    ]

    registry = ToolRegistry()
    registry.register(DummyTool())

    seen: list[str] = []

    def old_style_callback(name: str, args: str, result: ToolResult) -> None:
        seen.append(name)

    agent = Agent(
        config=config,
        agent_config=agent_config,
        llm_client=QueueLLM(responses),  # type: ignore[arg-type]
        tool_registry=registry,
        on_tool_call=old_style_callback,
        token_tracker=TokenTracker(),
        context_manager=ContextManager(model="fake-model"),
        auto_compress=False,
    )

    await agent.run("hi")
    assert seen == ["dummy"]

