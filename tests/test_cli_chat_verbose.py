"""Tests for mcode chat verbose formatting helpers."""

from __future__ import annotations

import json


def test_summarize_tool_args_read_file_path() -> None:
    from maxagent.cli import chat as chat_module

    args = json.dumps({"path": "demo/README.md"})
    assert chat_module._summarize_tool_args("read_file", args) == "path=demo/README.md"


def test_summarize_tool_args_todowrite_titles() -> None:
    from maxagent.cli import chat as chat_module

    args = json.dumps(
        {
            "todos": [
                {"id": "1", "content": "First", "status": "pending", "priority": "low"},
                {"id": "2", "content": "Second", "status": "pending", "priority": "low"},
            ]
        }
    )
    summary = chat_module._summarize_tool_args("todowrite", args)
    assert "todos=2" in summary
    assert "First" in summary and "Second" in summary


def test_tool_callback_todowrite_prints_status_per_line() -> None:
    from rich.console import Console

    from maxagent.cli import chat as chat_module
    from maxagent.tools import ToolResult

    original_console = chat_module.console
    recording_console = Console(record=True, width=200)
    chat_module.console = recording_console
    try:
        callback = chat_module._make_tool_callback()
        args = json.dumps(
            {
                "todos": [
                    {"id": "1", "content": "First", "status": "pending", "priority": "low"},
                    {"id": "2", "content": "Second", "status": "in_progress", "priority": "high"},
                ]
            }
        )
        callback("todowrite", args, ToolResult(success=True, output=""), request_id=6)

        output = recording_console.export_text()
        assert "Tool(req 6): todowrite todos=2" in output
        assert "pending [1] First" in output
        assert "in_progress [2] Second" in output
    finally:
        chat_module.console = original_console
