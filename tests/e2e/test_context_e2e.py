"""End-to-end tests for context summarization + automatic memory injection.

These tests simulate a multi-turn Agent conversation with:
1) Existing long-term memories.
2) Automatic injection into prompt.
3) Context overflow triggering LLM summarization.
4) New memories persisted and injected on next turn.
"""

from __future__ import annotations

import json

import pytest

from maxagent.config.schema import Config
from maxagent.core.agent import Agent, AgentConfig
from maxagent.llm.models import ChatResponse, Message, Usage
from maxagent.tools.registry import ToolRegistry
from maxagent.utils.context import ContextManager
from maxagent.utils.context_summary import MemoryCard, MemoryStore, get_project_memory_path
from maxagent.utils.tokens import TokenTracker


class RoutingLLM:
    """Fake LLM that routes between normal chat and summarizer calls."""

    def __init__(self) -> None:
        self.config = type("Cfg", (), {"model": "gpt-4"})()
        self.calls: list[list[Message]] = []

    async def chat(self, messages, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(messages)
        sys_msg = messages[0].content if messages else ""
        if sys_msg and "上下文汇总整理器" in sys_msg:
            payload = {
                "summary": "已确认：需要自动注入记忆并做滚动摘要。",
                "memories": [
                    {
                        "content": "系统已启用自动记忆注入。",
                        "type": "decision",
                        "tags": ["memory", "injection"],
                    }
                ],
            }
            return ChatResponse(
                id="sum",
                model="gpt-4",
                content=json.dumps(payload, ensure_ascii=False),
                usage=Usage(),
            )

        return ChatResponse(id="resp", model="gpt-4", content="ok", usage=Usage())


@pytest.mark.asyncio
async def test_end_to_end_summary_then_inject(project_root) -> None:
    # Seed memory store with one existing card.
    store = MemoryStore(get_project_memory_path(project_root))
    store.save(
        [
            MemoryCard(
                content="之前讨论过需要控制上下文长度。",
                type="fact",
                tags=["context"],
            )
        ]
    )

    llm = RoutingLLM()
    config = Config()
    config.tools.enabled = []

    agent_config = AgentConfig(system_prompt="You are test agent", tools=[], max_iterations=1)
    cm = ContextManager(
        model="gpt-4",
        compression_threshold=0.4,  # trigger easily
        retained_ratio=0.3,
        min_messages_to_keep=2,
        summary_max_tokens=200,
    )
    cm.set_project_root(project_root)

    agent = Agent(
        config=config,
        agent_config=agent_config,
        llm_client=llm,  # type: ignore[arg-type]
        tool_registry=ToolRegistry(),
        token_tracker=TokenTracker(),
        context_manager=cm,
        auto_compress=True,
    )

    # First turn: should inject existing memory.
    await agent.chat("我们之前说过什么关于上下文？")
    first_call = llm.calls[-1]
    assert any(m.name == "memory_context" for m in first_call)

    # Inflate history to force compression on next turn.
    agent.messages.append(Message(role="assistant", content="x" * 40000))

    # Second turn triggers summarization then injection.
    await agent.chat("自动记忆注入现在是什么决策？")

    # There should be at least one summarizer call.
    assert any(
        msgs and msgs[0].role == "system" and "上下文汇总整理器" in (msgs[0].content or "")
        for msgs in llm.calls
    )

    last_call = llm.calls[-1]
    # After summarization, summary and memory context are present.
    assert any(m.name == "context_summary" for m in last_call)
    assert any(m.name == "memory_context" for m in last_call)

    # New memory card persisted.
    cards = store.load()
    assert any("自动记忆注入" in c.content for c in cards)
