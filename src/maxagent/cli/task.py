"""Task command - Execute complex multi-agent tasks"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich.syntax import Syntax

from maxagent.config import load_config
from maxagent.core import Orchestrator, OrchestratorConfig, create_orchestrator
from maxagent.utils.console import console
from maxagent.utils.diff import apply_patch, create_backup

app = typer.Typer(
    help="Execute complex multi-agent tasks",
    context_settings={"help_option_names": ["-h", "--help"]},
)


@app.callback(invoke_without_command=True)
def task(
    ctx: typer.Context,
    description: Optional[str] = typer.Argument(
        None,
        help="Task description",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        "-a",
        help="Automatically apply all changes",
    ),
    skip_tests: bool = typer.Option(
        False,
        "--skip-tests",
        "-s",
        help="Skip test generation",
    ),
    skip_architect: bool = typer.Option(
        False,
        "--skip-architect",
        help="Skip architecture analysis phase",
    ),
    backup: bool = typer.Option(
        True,
        "--backup/--no-backup",
        help="Create backups before applying changes",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed output from each agent",
    ),
    pipe: bool = typer.Option(
        False,
        "--pipe",
        "-p",
        help="Pipe mode: output JSONL for programmatic use",
    ),
    yolo: bool = typer.Option(
        False,
        "--yolo",
        help="YOLO mode: allow reading/writing files anywhere on the system",
    ),
    max_iterations: Optional[int] = typer.Option(
        None,
        "--max-iterations",
        "-i",
        help="Maximum tool call iterations (default: from config)",
    ),
):
    """
    Execute a complex task using multi-agent collaboration.

    This command coordinates multiple AI agents to complete complex tasks:

    1. **Architect Agent**: Analyzes requirements and creates implementation plan
    2. **Coder Agent**: Generates code based on the plan
    3. **Tester Agent**: Creates tests for the changes (optional)

    Examples:

        # Basic task
        mcode task "Add a /health endpoint to the API"

        # Auto-apply changes
        mcode task "Refactor user authentication" --apply

        # Skip tests
        mcode task "Add logging to database module" --skip-tests

        # Quick task (skip analysis)
        mcode task "Fix typo in README" --skip-architect

        # Pipe mode for programmatic use
        mcode task "Add error handling" -p | jq

        # YOLO mode for unrestricted file access
        mcode task "Update ~/config/settings.json" --yolo

        # Limit tool iterations
        mcode task "Complex refactoring" --max-iterations 50
    """
    if description is None:
        if pipe:
            error_output = {"type": "error", "message": "Task description is required"}
            print(json.dumps(error_output, ensure_ascii=False))
        else:
            console.print("[yellow]Please provide a task description[/yellow]")
            console.print('\nUsage: mcode task "your task description"')
            console.print('\nExample: mcode task "Add a new API endpoint for user profile"')
        raise typer.Exit(0)

    # Get global options from context
    global_opts = ctx.obj or {}
    effective_yolo = yolo or global_opts.get("yolo", False)
    effective_max_iterations = max_iterations or global_opts.get("max_iterations")

    asyncio.run(
        _execute_task(
            description=description,
            apply=apply,
            skip_tests=skip_tests,
            skip_architect=skip_architect,
            backup=backup,
            verbose=verbose,
            pipe=pipe,
            yolo=effective_yolo,
            max_iterations=effective_max_iterations,
        )
    )


async def _execute_task(
    description: str,
    apply: bool,
    skip_tests: bool,
    skip_architect: bool,
    backup: bool,
    verbose: bool,
    pipe: bool = False,
    yolo: bool = False,
    max_iterations: Optional[int] = None,
) -> None:
    """Execute the task with multi-agent collaboration"""

    # Load config
    config = load_config()

    # Show YOLO mode warning
    if yolo and not pipe:
        console.print(
            "[bold yellow]Warning: YOLO mode enabled - file access restrictions disabled[/bold yellow]"
        )
        console.print()

    # Create orchestrator with config
    orchestrator_config = OrchestratorConfig(
        enable_architect=not skip_architect,
        enable_tester=not skip_tests,
    )

    orchestrator = create_orchestrator(
        config=config,
        orchestrator_config=orchestrator_config,
        allow_outside_project=yolo,
        max_iterations=max_iterations,
    )

    # Track current phase for progress display
    current_phase = {"agent": "", "status": ""}

    def progress_callback(agent_name: str, status: str) -> None:
        current_phase["agent"] = agent_name
        current_phase["status"] = status
        if pipe:
            progress_output = {"type": "progress", "agent": agent_name, "status": status}
            print(json.dumps(progress_output, ensure_ascii=False), flush=True)

    orchestrator.set_progress_callback(progress_callback)

    try:
        if pipe:
            # Pipe mode: no progress display
            result = await orchestrator.execute_task(description)
            _output_task_jsonl(result)
        else:
            # Normal mode: with progress display
            # Execute task with progress display
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                task_id = progress.add_task("Initializing...", total=None)

                # Create a wrapper to update progress
                original_callback = progress_callback

                def update_progress(agent_name: str, status: str) -> None:
                    original_callback(agent_name, status)
                    progress.update(task_id, description=f"[bold cyan]{agent_name}[/]: {status}")

                orchestrator.set_progress_callback(update_progress)

                result = await orchestrator.execute_task(description)

            # Display results
            console.print()

            # Show summary (architecture analysis)
            if result.summary:
                console.print(
                    Panel(
                        Markdown(result.summary),
                        title="[bold blue]Architecture Analysis[/]",
                        border_style="blue",
                    )
                )
                console.print()

            # Show verbose agent outputs
            if verbose:
                for agent_name, output in result.agent_outputs.items():
                    if agent_name != "architect" or not result.summary:  # Don't duplicate
                        console.print(
                            Panel(
                                Markdown(output),
                                title=f"[bold]{agent_name.title()} Output[/]",
                                border_style="dim",
                            )
                        )
                        console.print()

            # Show patches
            if result.patches:
                console.print(f"[bold green]Generated {len(result.patches)} code change(s):[/]\n")

                for i, patch in enumerate(result.patches, 1):
                    # Try to extract filename from patch
                    filename = "Unknown file"
                    for line in patch.split("\n"):
                        if line.startswith("+++ "):
                            filename = line[4:].strip()
                            if filename.startswith("b/"):
                                filename = filename[2:]
                            break

                    console.print(
                        Panel(
                            Syntax(patch, "diff", theme="monokai", line_numbers=True),
                            title=f"[bold]Change {i}: {filename}[/]",
                            border_style="green",
                        )
                    )
                    console.print()
            else:
                console.print("[yellow]No code changes generated[/]")

            # Show tests
            if result.tests:
                console.print(f"[bold blue]Generated {len(result.tests)} test(s):[/]\n")

                for i, test in enumerate(result.tests, 1):
                    console.print(
                        Panel(
                            Syntax(test, "python", theme="monokai", line_numbers=True),
                            title=f"[bold]Test {i}[/]",
                            border_style="blue",
                        )
                    )
                    console.print()

            # Apply patches if requested
            if result.patches:
                should_apply = apply or Confirm.ask(
                    "\n[bold]Apply these changes?[/]",
                    default=False,
                )

                if should_apply:
                    applied_count = 0
                    failed_count = 0

                    for patch in result.patches:
                        # Extract file path from patch
                        file_path = None
                        for line in patch.split("\n"):
                            if line.startswith("+++ "):
                                file_path = line[4:].strip()
                                if file_path.startswith("b/"):
                                    file_path = file_path[2:]
                                break

                        if not file_path:
                            console.print("[yellow]Could not determine file path from patch[/]")
                            failed_count += 1
                            continue

                        target_path = Path(file_path)

                        # Create backup if requested
                        if backup and target_path.exists():
                            backup_path = create_backup(target_path)
                            console.print(f"[dim]Backup created: {backup_path}[/]")

                        # Apply patch
                        success = apply_patch(patch, target_path)

                        if success:
                            console.print(f"[green]Applied changes to {file_path}[/]")
                            applied_count += 1
                        else:
                            console.print(f"[red]Failed to apply changes to {file_path}[/]")
                            failed_count += 1

                    console.print()
                    if applied_count > 0:
                        console.print(f"[green]Successfully applied {applied_count} change(s)[/]")
                    if failed_count > 0:
                        console.print(f"[yellow]Failed to apply {failed_count} change(s)[/]")
                else:
                    console.print("[dim]Changes not applied[/]")

            # Save tests if generated
            if result.tests:
                save_tests = Confirm.ask(
                    "\n[bold]Save generated tests?[/]",
                    default=False,
                )

                if save_tests:
                    # Try to determine test directory
                    test_dirs = ["tests", "test", "spec"]
                    test_dir = None

                    for d in test_dirs:
                        if Path(d).exists():
                            test_dir = Path(d)
                            break

                    if test_dir is None:
                        test_dir = Path("tests")
                        test_dir.mkdir(exist_ok=True)
                        console.print(f"[dim]Created test directory: {test_dir}[/]")

                    for i, test in enumerate(result.tests, 1):
                        test_file = test_dir / f"test_generated_{i}.py"
                        test_file.write_text(test)
                        console.print(f"[green]Saved test to {test_file}[/]")

    except Exception as e:
        if pipe:
            error_output = {"type": "error", "message": str(e)}
            print(json.dumps(error_output, ensure_ascii=False))
        else:
            console.print(f"[red]Error executing task: {e}[/]")
        raise typer.Exit(1)

    finally:
        await orchestrator.close()


def _output_task_jsonl(result) -> None:
    """Output task result in JSONL format"""
    output = {
        "type": "task_result",
        "summary": result.summary,
        "patches": result.patches,
        "tests": result.tests,
        "agent_outputs": result.agent_outputs,
    }
    print(json.dumps(output, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    app()
