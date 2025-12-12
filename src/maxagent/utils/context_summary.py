"""LLM-powered context summarization and long-term memory storage.

This module implements the "上下文汇总工具" spec:
- When conversation history grows too large, older messages are summarized into a
  compact, structured context summary.
- Key facts/decisions/todos are stored as searchable "memory cards" on disk.

The summarizer is intentionally lightweight: classification/importance scoring
is delegated to the LLM, while we provide robust prompting, parsing and
persistence.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from .context import estimate_tokens, _truncate_text

if TYPE_CHECKING:
    from maxagent.llm.client import LLMClient
    from maxagent.llm.models import Message, ChatResponse


SUMMARY_MESSAGE_NAME = "context_summary"
SUMMARY_HEADER = "## Context Summary"


def get_project_memory_path(project_root: Path) -> Path:
    """Return the project-level memory storage path."""
    return project_root / ".maxagent" / "memory.json"


@dataclass
class MemoryCard:
    """A single long-term memory card."""

    content: str
    type: str = "fact"
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    source: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "type": self.type,
            "tags": self.tags,
            "created_at": self.created_at,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryCard":
        return cls(
            content=data.get("content", ""),
            type=data.get("type", "fact"),
            tags=list(data.get("tags", [])),
            created_at=data.get("created_at", datetime.now().isoformat()),
            source=data.get("source"),
        )


class MemoryStore:
    """Disk-backed store for memory cards."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[MemoryCard]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("items", [])
            return [MemoryCard.from_dict(x) for x in items if isinstance(x, dict)]
        except Exception:
            return []

    def save(self, cards: list[MemoryCard]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [c.to_dict() for c in cards]
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def append(self, new_cards: list[MemoryCard]) -> int:
        """Append new cards, skipping duplicates by content."""
        if not new_cards:
            return 0
        cards = self.load()
        existing = {c.content.strip() for c in cards if c.content}
        added = 0
        for c in new_cards:
            key = c.content.strip()
            if key and key not in existing:
                cards.append(c)
                existing.add(key)
                added += 1
        if added:
            self.save(cards)
        return added

    def search(self, query: str, top_k: int = 5) -> list[MemoryCard]:
        """Simple keyword-based search over cards."""
        query = query.strip().lower()
        if not query:
            return []

        # Extract meaningful terms (ASCII words or CJK sequences)
        raw_terms = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", query)
        q_terms: list[str] = []
        for term in raw_terms:
            if re.fullmatch(r"[\u4e00-\u9fff]+", term) and len(term) > 2:
                # For Chinese terms, add 2-4 char ngrams for better recall
                for n in (2, 3, 4):
                    if len(term) < n:
                        continue
                    for i in range(0, len(term) - n + 1):
                        q_terms.append(term[i : i + n])
            else:
                q_terms.append(term)

        if not q_terms:
            q_terms = [t for t in re.split(r"\s+", query) if t]

        def score(card: MemoryCard) -> int:
            text = (card.content + " " + " ".join(card.tags)).lower()
            s = 0
            for t in q_terms:
                if t in text:
                    s += 3
            return s

        scored = [(score(c), c) for c in self.load()]
        scored = [x for x in scored if x[0] > 0]
        scored.sort(key=lambda x: (x[0], x[1].created_at), reverse=True)
        return [c for _, c in scored[: max(1, top_k)]]


@dataclass
class SummaryResult:
    summary_text: str
    memories: list[MemoryCard] = field(default_factory=list)


class ContextSummarizer:
    """Summarize a list of messages into structured context + memory cards."""

    def __init__(
        self,
        llm_client: "LLMClient",
        model: Optional[str] = None,
        max_output_tokens: int = 1200,
        max_input_tokens: int = 60000,
        chunk_tokens: int = 12000,
    ) -> None:
        self.llm = llm_client
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.max_input_tokens = max_input_tokens
        self.chunk_tokens = chunk_tokens

    def _format_messages(self, messages: list["Message"]) -> str:
        lines: list[str] = []
        for i, m in enumerate(messages, start=1):
            content = m.content or ""
            # Avoid sending extremely long single messages
            content, _ = _truncate_text(content, 2000)
            lines.append(f"[{i}][{m.role}] {content}".strip())
        return "\n".join(lines)

    def _build_system_prompt(self) -> str:
        return (
            "你是“上下文汇总整理器”。给你一段对话历史（含 user/assistant/tool 角色）以及可选旧摘要，"
            "请输出一个 JSON 对象：\n"
            "{\n"
            '  "summary": "markdown 文本，包含：当前目标/需求、背景、关键信息/事实、约束、决策、TODO、重要代码或命令",\n'
            '  "memories": [\n'
            '    {"content": "可检索的关键结论/事实/配置", "type": "goal|decision|constraint|todo|code|fact", "tags": ["主题关键词"]}\n'
            "  ]\n"
            "}\n"
            "要求：\n"
            "- summary 去重、去寒暄，保持足够让 Agent 继续工作的信息密度。\n"
            "- memories 只保留未来可能需要回忆/检索的条目，每条一句话。\n"
            "- 只输出有效 JSON，不要输出其它文字。"
        )

    async def _summarize_text(
        self, text: str, previous_summary: Optional[str] = None
    ) -> SummaryResult:
        from maxagent.llm.models import Message

        user_payload = ""
        if previous_summary:
            user_payload += f"旧摘要：\n{previous_summary}\n\n"
        user_payload += f"对话历史：\n{text}"

        resp = await self.llm.chat(
            messages=[
                Message(role="system", content=self._build_system_prompt()),
                Message(role="user", content=user_payload),
            ],
            tools=None,
            stream=False,
            model=self.model,
            max_tokens=self.max_output_tokens,
            temperature=0.2,
        )

        assert not isinstance(resp, str)
        content = (resp.content or "").strip()
        data = self._extract_json(content)
        if not isinstance(data, dict):
            # Fallback: treat whole response as summary
            summary_text, _ = _truncate_text(content, self.max_output_tokens)
            return SummaryResult(summary_text=summary_text, memories=[])

        summary_text = str(data.get("summary", "")).strip()
        if not summary_text:
            summary_text = content
        summary_text, _ = _truncate_text(summary_text, self.max_output_tokens)

        memories_raw = data.get("memories", [])
        memories: list[MemoryCard] = []
        if isinstance(memories_raw, list):
            for m in memories_raw:
                if not isinstance(m, dict):
                    continue
                c = str(m.get("content", "")).strip()
                if not c:
                    continue
                memories.append(
                    MemoryCard(
                        content=c,
                        type=str(m.get("type", "fact")),
                        tags=[str(t) for t in m.get("tags", []) if t],
                    )
                )

        return SummaryResult(summary_text=summary_text, memories=memories)

    def _extract_json(self, text: str) -> Optional[dict[str, Any]]:
        try:
            return json.loads(text)
        except Exception:
            pass
        # Try to locate a JSON object in the text
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return None
        return None

    def _split_by_tokens(self, messages: list["Message"]) -> list[list["Message"]]:
        """Split messages into chunks by estimated tokens."""
        chunks: list[list["Message"]] = []
        current: list["Message"] = []
        current_tokens = 0
        for m in messages:
            t = estimate_tokens(m.content or "")
            if current and current_tokens + t > self.chunk_tokens:
                chunks.append(current)
                current = [m]
                current_tokens = t
            else:
                current.append(m)
                current_tokens += t
        if current:
            chunks.append(current)
        return chunks

    async def summarize(
        self,
        messages: list["Message"],
        previous_summary: Optional[str] = None,
    ) -> SummaryResult:
        """Summarize messages, chunking when input is too large."""
        if not messages:
            return SummaryResult(summary_text=previous_summary or "", memories=[])

        formatted = self._format_messages(messages)
        if estimate_tokens(formatted) <= self.max_input_tokens:
            return await self._summarize_text(formatted, previous_summary)

        # Hierarchical chunk summarization
        chunk_summaries: list[str] = []
        for chunk in self._split_by_tokens(messages):
            text = self._format_messages(chunk)
            res = await self._summarize_text(text, previous_summary=None)
            chunk_summaries.append(res.summary_text)

        merged_text = "\n\n".join(
            f"Chunk {i+1} summary:\n{cs}" for i, cs in enumerate(chunk_summaries)
        )
        return await self._summarize_text(merged_text, previous_summary)
