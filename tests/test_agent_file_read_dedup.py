"""Tests for agent-side de-duplication/compaction of repeated read_file outputs."""

from __future__ import annotations

from pathlib import Path

import pytest

from maxagent.config.schema import Config
from maxagent.core.agent import Agent, AgentConfig
from maxagent.llm.models import ChatResponse, ToolCall, ToolCallFunction, Usage
from maxagent.tools import create_default_registry
from maxagent.utils.context import ContextManager
from maxagent.utils.tokens import TokenTracker


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
async def test_agent_compacts_superseded_read_file_after_edit(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello world\n", encoding="utf-8")

    config = Config()
    config.tools.enabled = ["read_file", "edit"]

    agent_config = AgentConfig(system_prompt="", tools=[], max_iterations=5)

    responses = [
        ChatResponse(
            id="resp-1",
            model="fake-model",
            content=None,
            tool_calls=[
                ToolCall(
                    id="call-1",
                    function=ToolCallFunction(name="read_file", arguments='{"path":"a.txt"}'),
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
                        name="edit",
                        arguments='{"file_path":"a.txt","old_string":"hello","new_string":"hi"}',
                    ),
                )
            ],
            finish_reason="tool_calls",
            usage=Usage(),
        ),
        ChatResponse(
            id="resp-3",
            model="fake-model",
            content=None,
            tool_calls=[
                ToolCall(
                    id="call-3",
                    function=ToolCallFunction(name="read_file", arguments='{"path":"a.txt"}'),
                )
            ],
            finish_reason="tool_calls",
            usage=Usage(),
        ),
        ChatResponse(
            id="resp-4",
            model="fake-model",
            content="done",
            tool_calls=None,
            finish_reason="stop",
            usage=Usage(),
        ),
    ]

    registry = create_default_registry(tmp_path)

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

    read_msgs = [m for m in agent.messages if m.role == "tool" and m.name == "read_file"]
    assert len(read_msgs) == 2

    # Only the latest read_file should keep full content.
    assert sum(1 for m in read_msgs if m.content == "hi world\n") == 1
    assert all(m.content != "hello world\n" for m in read_msgs if m.content)
    assert any(m.content and m.content.startswith("(superseded)") for m in read_msgs)

