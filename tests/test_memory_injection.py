"""Tests for automatic memory injection into prompts."""

from __future__ import annotations

import pytest

from maxagent.config.schema import Config
from maxagent.core.agent import Agent, AgentConfig
from maxagent.llm.models import ChatResponse, Message, Usage
from maxagent.tools.registry import ToolRegistry
from maxagent.utils.context import ContextManager
from maxagent.utils.context_summary import MemoryCard, MemoryStore, get_project_memory_path
from maxagent.utils.tokens import TokenTracker


class RecordingLLM:
    """Fake LLM that records the last messages payload."""

    def __init__(self) -> None:
        self.config = type("Cfg", (), {"model": "fake-model"})()
        self.last_messages: list[Message] = []

    async def chat(self, messages, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.last_messages = messages
        return ChatResponse(
            id="resp",
            model="fake-model",
            content="ok",
            usage=Usage(),
        )


@pytest.mark.asyncio
async def test_auto_memory_injection_inserts_before_user(project_root) -> None:
    # Prepare memory store
    store = MemoryStore(get_project_memory_path(project_root))
    store.save(
        [
            MemoryCard(
                content="之前决定使用 gpt-4o 作为默认模型。",
                type="decision",
                tags=["model", "decision"],
            )
        ]
    )

    llm = RecordingLLM()
    config = Config()
    agent_config = AgentConfig(system_prompt="You are test agent", tools=[], max_iterations=1)
    cm = ContextManager(model="fake-model")
    cm.set_project_root(project_root)
    cm.enable_memory_injection = True
    cm.memory_top_k = 3

    agent = Agent(
        config=config,
        agent_config=agent_config,
        llm_client=llm,  # type: ignore[arg-type]
        tool_registry=ToolRegistry(),
        token_tracker=TokenTracker(),
        context_manager=cm,
        auto_compress=False,
    )

    await agent.run("默认模型是什么？")

    roles = [m.role for m in llm.last_messages]
    # Expect: system, memory_context, user
    assert roles[0] == "system"
    assert roles[1] == "assistant"
    assert llm.last_messages[1].name == "memory_context"
    assert roles[2] == "user"
    assert "Relevant Memories" in (llm.last_messages[1].content or "")
