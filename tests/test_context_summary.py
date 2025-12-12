"""Tests for LLM-based context summarization and memory store."""

from __future__ import annotations

import json

import pytest

from maxagent.llm.models import ChatResponse, Message
from maxagent.utils.context import ContextManager
from maxagent.utils.context_summary import MemoryCard, MemoryStore, get_project_memory_path


class FakeSummaryLLM:
    """Fake LLM returning a fixed JSON summary."""

    def __init__(self, content: str) -> None:
        self.config = type("Cfg", (), {"model": "fake-model"})()
        self._content = content

    async def chat(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return ChatResponse(id="resp", model="fake-model", content=self._content)


@pytest.mark.asyncio
async def test_compress_messages_with_summary_persists_memory(project_root) -> None:
    fake_json = json.dumps(
        {
            "summary": "用户的主要目标是测试上下文汇总。",
            "memories": [
                {"content": "用户需要自动上下文汇总功能。", "type": "goal", "tags": ["context"]}
            ],
        },
        ensure_ascii=False,
    )
    llm = FakeSummaryLLM(fake_json)

    cm = ContextManager(
        model="gpt-4",
        retained_ratio=0.3,
        min_messages_to_keep=2,
        summary_max_tokens=200,
    )

    huge = "x" * 40000
    messages = [
        Message(role="system", content="System prompt"),
        Message(role="user", content="Old message"),
        Message(role="assistant", content=huge),
        Message(role="user", content="Recent question"),
        Message(role="assistant", content="Recent answer"),
    ]

    compressed = await cm.compress_messages_with_summary(
        messages, llm_client=llm, project_root=project_root
    )

    # Summary message inserted
    summary_msgs = [m for m in compressed if m.name == "context_summary"]
    assert len(summary_msgs) == 1
    assert "Context Summary" in (summary_msgs[0].content or "")

    # Memory persisted
    store = MemoryStore(get_project_memory_path(project_root))
    cards = store.load()
    assert any("自动上下文汇总" in c.content for c in cards)


def test_memory_store_search(project_root) -> None:
    path = get_project_memory_path(project_root)
    store = MemoryStore(path)
    store.save(
        [
            MemoryCard(
                content="选择 GPU 需要看显存。",
                type="decision",
                tags=["GPU", "显存"],
                created_at="2024-01-01T00:00:00",
            ),
            MemoryCard(
                content="项目需要支持自动上下文汇总。",
                type="goal",
                tags=["context", "summary"],
                created_at="2024-01-02T00:00:00",
            ),
        ]
    )

    results = store.search("上下文 汇总", top_k=2)
    assert results
    assert any("上下文汇总" in r.content for r in results)
