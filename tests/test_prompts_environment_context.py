"""Tests for environment context prompt construction."""

from __future__ import annotations

from maxagent.core.prompts import build_environment_context


def test_environment_context_includes_dir_listing(tmp_path) -> None:
    (tmp_path / "a.py").write_text("print('a')", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / ".hidden").write_text("secret", encoding="utf-8")
    (tmp_path / "dir").mkdir()

    ctx = build_environment_context(
        working_directory=tmp_path,
        include_time=False,
        include_dir_listing=True,
        max_dir_entries=10,
    )

    assert "Directory listing" in ctx
    assert "- a.py" in ctx
    assert "- b.txt" in ctx
    assert "- dir/" in ctx
    assert ".hidden" not in ctx

