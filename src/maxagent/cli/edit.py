"""Edit command implementation"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax

from maxagent.config import load_config
from maxagent.core import AgentConfig, Agent
from maxagent.llm import create_llm_client
from maxagent.tools import ToolResult, create_default_registry
from maxagent.utils.console import print_dim, print_error, print_info, print_success
from maxagent.utils.diff import apply_patch, extract_patches_from_text

# Use Typer with invoke_without_command to handle direct arguments
app = typer.Typer(
    help="Edit files with AI assistance",
    invoke_without_command=True,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()

EDIT_SYSTEM_PROMPT = """You are a code editor assistant. Your task is to modify files based on user instructions.

When making changes:
1. First use read_file to get the current content of the file
2. Analyze the current code structure
3. Generate a unified diff patch for the changes
4. Format the patch in a code block with ```diff

Output format for patches:
```diff
--- a/path/to/file
+++ b/path/to/file
@@ -line,count +line,count @@
 context line
-removed line
+added line
 context line
```

Be precise with line numbers and include enough context (2-3 lines) for accurate patch application.
Always explain what changes you're making before showing the patch."""


def _tool_callback(name: str, args: str, result: ToolResult) -> None:
    """Callback to display tool usage"""
    status = "[green]OK[/green]" if result.success else "[red]FAILED[/red]"
    console.print(f"[dim]Tool: {name} {status}[/dim]")


def _tool_callback_jsonl(name: str, args: str, result: ToolResult) -> None:
    """Callback to output tool usage in JSONL format"""
    output = {
        "type": "tool_call",
        "tool": name,
        "arguments": args,
        "success": result.success,
        "output": result.output,
        "error": result.error,
    }
    print(json.dumps(output, ensure_ascii=False), flush=True)


@app.callback()
def edit(
    ctx: typer.Context,
    file: Path = typer.Argument(..., help="File to edit"),
    instruction: str = typer.Argument(..., help="Edit instruction"),
    apply: bool = typer.Option(False, "--apply", "-a", help="Apply changes without confirmation"),
    no_backup: bool = typer.Option(False, "--no-backup", help="Don't create backup"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override model"),
    project: Optional[Path] = typer.Option(None, "--project", help="Project directory"),
    pipe: bool = typer.Option(
        False, "--pipe", "-p", help="Pipe mode: output JSONL for programmatic use"
    ),
    yolo: bool = typer.Option(
        False, "--yolo", help="YOLO mode: allow reading/writing files anywhere on the system"
    ),
    max_iterations: Optional[int] = typer.Option(
        None, "--max-iterations", "-i", help="Maximum tool call iterations (default: from config)"
    ),
) -> None:
    """
    Edit a file with AI assistance.

    Examples:
        mcode edit src/app.py "Add error handling"
        mcode edit README.md "Fix typos and improve grammar" --apply
        mcode edit src/app.py "Add logging" -p | jq  # Pipe mode with JSONL output
        mcode edit ~/some/file.py "Add docstrings" --yolo  # YOLO mode for unrestricted access
        mcode edit src/app.py "Refactor" --max-iterations 50  # Limit tool iterations
    """
    # Get global options from context
    global_opts = ctx.obj or {}
    effective_model = model or global_opts.get("model")
    effective_project = project or global_opts.get("project")
    effective_yolo = yolo or global_opts.get("yolo", False)
    effective_max_iterations = max_iterations or global_opts.get("max_iterations")

    asyncio.run(
        _edit_file(
            file,
            instruction,
            apply,
            no_backup,
            effective_model,
            effective_project,
            pipe,
            effective_yolo,
            effective_max_iterations,
        )
    )


async def _edit_file(
    file: Path,
    instruction: str,
    apply_directly: bool,
    no_backup: bool,
    model: Optional[str],
    project: Optional[Path],
    pipe: bool = False,
    yolo: bool = False,
    max_iterations: Optional[int] = None,
) -> None:
    """Handle file editing"""
    try:
        project_root = project or Path.cwd()
        file_path = project_root / file if not file.is_absolute() else file

        # Check if file exists
        if not file_path.exists():
            if pipe:
                error_output = {"type": "error", "message": f"File not found: {file}"}
                print(json.dumps(error_output, ensure_ascii=False))
            else:
                print_error(f"File not found: {file}")
            raise typer.Exit(1)

        config = load_config(project_root)

        if model:
            config.model.default = model

        # Create LLM client
        llm_client = create_llm_client(config)

        # Show YOLO mode warning
        if yolo and not pipe:
            print_info("[YOLO mode] File access restrictions disabled")

        # Create tool registry with YOLO mode support
        tool_registry = create_default_registry(project_root, allow_outside_project=yolo)

        # Choose callback based on mode
        tool_callback = _tool_callback_jsonl if pipe else _tool_callback

        # Determine max_iterations: CLI arg > config > default
        effective_max_iterations = max_iterations or config.model.max_iterations

        # Create agent with edit-specific prompt
        agent_config = AgentConfig(
            name="editor",
            system_prompt=EDIT_SYSTEM_PROMPT,
            tools=["read_file", "list_files", "search_code"],
            max_iterations=effective_max_iterations,
        )

        agent = Agent(
            config=config,
            agent_config=agent_config,
            llm_client=llm_client,
            tool_registry=tool_registry,
            on_tool_call=tool_callback,
        )

        # Build the task
        rel_path = (
            file_path.relative_to(project_root) if file_path.is_relative_to(project_root) else file
        )
        task = f"""Edit the file `{rel_path}` with the following instruction:

{instruction}

First read the file to understand its current content, then provide a unified diff patch for the required changes."""

        # Run agent
        if pipe:
            response = await agent.run(task)
        else:
            with console.status("[bold green]Analyzing and generating changes...[/bold green]"):
                response = await agent.run(task)

        if not isinstance(response, str):
            # Handle streaming response
            content = ""
            async for chunk in response:
                content += chunk
            response = content

        # Extract patches from response
        patches = extract_patches_from_text(response)

        if pipe:
            # Output in JSONL format
            _output_edit_jsonl(response, patches, file_path, agent)
        else:
            # Display response
            console.print(
                Panel(
                    Markdown(response),
                    title="[bold green]Proposed Changes[/bold green]",
                    border_style="green",
                )
            )

            if not patches:
                print_info("No patches found in the response")
                return

            # Display patches
            console.print(f"\n[bold]Found {len(patches)} patch(es):[/bold]")

            for i, (patch_file, patch_content) in enumerate(patches):
                console.print(
                    Panel(
                        Syntax(patch_content, "diff", theme="monokai"),
                        title=f"[bold yellow]Patch {i + 1}: {patch_file}[/bold yellow]",
                        border_style="yellow",
                    )
                )

            # Confirm and apply
            if apply_directly or Confirm.ask("\nApply these changes?"):
                for patch_file, patch_content in patches:
                    target_path = project_root / patch_file

                    # Ensure parent directories exist
                    target_path.parent.mkdir(parents=True, exist_ok=True)

                    # Apply patch
                    success = apply_patch(
                        patch_content,
                        target_path,
                        create_backup_file=not no_backup,
                    )

                    if success:
                        print_success(f"Applied patch to {patch_file}")
                    else:
                        print_error(f"Failed to apply patch to {patch_file}")
            else:
                print_dim("Changes not applied")

        # Cleanup
        await llm_client.close()

    except Exception as e:
        if pipe:
            error_output = {"type": "error", "message": str(e)}
            print(json.dumps(error_output, ensure_ascii=False))
        else:
            print_error(str(e))
        raise typer.Exit(1)


def _output_edit_jsonl(response: str, patches: list, file_path: Path, agent: Agent) -> None:
    """Output edit response in JSONL format"""
    usage = agent.get_last_usage()

    output = {
        "type": "edit_response",
        "file": str(file_path),
        "response": response,
        "patches": [
            {"file": patch_file, "content": patch_content} for patch_file, patch_content in patches
        ],
        "model": agent.llm.config.model,
    }

    if usage:
        output["usage"] = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        }
        cost = agent.token_tracker._calculate_cost(usage, agent.llm.config.model)
        output["cost_usd"] = cost

    print(json.dumps(output, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    app()
