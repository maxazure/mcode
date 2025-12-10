"""CLI main entry point"""

import typer
from typing import Optional

# Enable -h as alias for --help
app = typer.Typer(
    name="llc",
    help="MaxAgent - AI Code Assistant CLI based on LiteLLM",
    add_completion=True,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

# Import and register subcommands
from maxagent.cli import chat, edit, config_cmd, task, test_cmd, auth_cmd, mcp_cmd

app.add_typer(chat.app, name="chat")
app.add_typer(edit.app, name="edit")
app.add_typer(config_cmd.app, name="config")
app.add_typer(task.app, name="task")
app.add_typer(test_cmd.app, name="test")
app.add_typer(auth_cmd.app, name="auth")
app.add_typer(mcp_cmd.app, name="mcp")


@app.callback()
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override default model"),
) -> None:
    """MaxAgent - AI Code Assistant CLI"""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["model"] = model


@app.command()
def version() -> None:
    """Show version information"""
    from maxagent import __version__
    from rich.console import Console

    console = Console()
    console.print(f"[bold green]MaxAgent[/bold green] version {__version__}")


def cli() -> None:
    """CLI entry point"""
    # Preprocess argv for MCP Claude-style arguments
    mcp_cmd.preprocess_argv()
    app()


if __name__ == "__main__":
    cli()
