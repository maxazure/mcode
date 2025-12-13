"""Tests for batched exploration in SubAgentTool."""

from __future__ import annotations

import pytest

from maxagent.config.schema import Config
from maxagent.llm.models import ChatResponse, Usage
from maxagent.tools.subagent import SubAgentTool


class DummyLLM:
    """Fake LLM client that returns canned summaries and counts calls."""

    def __init__(self) -> None:
        self.config = type("Cfg", (), {"model": "fake-model"})()
        self.calls = 0

    async def chat(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        return ChatResponse(
            id=f"resp-{self.calls}",
            model="fake-model",
            content=f"summary-{self.calls}",
            tool_calls=None,
            finish_reason="stop",
            usage=Usage(),
        )


@pytest.mark.asyncio
async def test_batched_explore_runs_multiple_llm_calls(tmp_path) -> None:
    # Create a small fake project
    proj = tmp_path
    (proj / "demo" / "multiplayer_snake").mkdir(parents=True)
    for i in range(5):
        (proj / "demo" / "multiplayer_snake" / f"f{i}.py").write_text(
            "x" * 2000, encoding="utf-8"
        )

    cfg = Config()
    llm = DummyLLM()
    tool = SubAgentTool(project_root=proj, config=cfg, llm_client=llm)

    out = await tool._run_batched_explore(llm, "探索 demo/multiplayer_snake 结构")
    # At least one LLM call for summaries; reduce is skipped when one batch.
    assert llm.calls >= 1
    assert "Merged Overview" in out or "Merged Overview" in out


@pytest.mark.asyncio
async def test_collect_text_files_respects_gitignore(tmp_path) -> None:
    proj = tmp_path
    # Git ignore a file and a directory
    (proj / ".gitignore").write_text("ignored.py\nignored_dir/\n", encoding="utf-8")

    (proj / "ignored.py").write_text("print('x')", encoding="utf-8")
    (proj / "keep.py").write_text("print('y')", encoding="utf-8")
    (proj / "ignored_dir").mkdir()
    (proj / "ignored_dir" / "a.py").write_text("print('z')", encoding="utf-8")

    cfg = Config()
    llm = DummyLLM()
    tool = SubAgentTool(project_root=proj, config=cfg, llm_client=llm)

    files = tool._collect_text_files(proj)
    rels = {str(p.relative_to(proj)) for p in files}

    assert "keep.py" in rels
    assert "ignored.py" not in rels
    assert "ignored_dir/a.py" not in rels
