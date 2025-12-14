"""CLI main entry point"""

import typer
from typing import Optional
from pathlib import Path

# Enable -h as alias for --help
app = typer.Typer(
    name="mcode",
    help="MaxAgent - AI Code Assistant CLI based on LiteLLM",
    add_completion=True,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

# Import and register subcommands
from maxagent.cli import chat, edit, config_cmd, task, test_cmd, auth_cmd, mcp_cmd, models_cmd

app.add_typer(chat.app, name="chat")
app.add_typer(edit.app, name="edit")
app.add_typer(config_cmd.app, name="config")
app.add_typer(task.app, name="task")
app.add_typer(test_cmd.app, name="test")
app.add_typer(auth_cmd.app, name="auth")
app.add_typer(mcp_cmd.app, name="mcp")
app.add_typer(models_cmd.app, name="models")


@app.callback()
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override default model"),
    max_iterations: Optional[int] = typer.Option(
        None, "--max-iterations", "-i", help="Maximum tool call iterations (default: 100)"
    ),
    project: Optional[Path] = typer.Option(
        None, "--project", "-P", help="Project directory (default: current directory)"
    ),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to configuration file"
    ),
    yolo: bool = typer.Option(
        False, "--yolo", help="YOLO mode: allow reading/writing files anywhere on the system"
    ),
    debug_context: bool = typer.Option(
        False, "--debug-context", help="Show context token usage before each API call"
    ),
) -> None:
    """MaxAgent - AI Code Assistant CLI"""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["model"] = model
    ctx.obj["max_iterations"] = max_iterations
    ctx.obj["project"] = project
    ctx.obj["config"] = config
    ctx.obj["yolo"] = yolo
    ctx.obj["debug_context"] = debug_context


@app.command()
def version() -> None:
    """Show version information"""
    from maxagent import __version__
    from rich.console import Console

    console = Console()
    console.print(f"[bold green]MaxAgent[/bold green] version {__version__}")


def cli() -> None:
    """CLI entry point"""
    # Ensure config directory exists on first run
    from maxagent.config.loader import ensure_config_dir

    ensure_config_dir()

    # Preprocess argv for MCP Claude-style arguments
    mcp_cmd.preprocess_argv()
    app()


if __name__ == "__main__":
    cli()
