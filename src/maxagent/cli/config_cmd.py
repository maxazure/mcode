"""Config command implementation"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from maxagent.config import (
    get_project_config_path,
    get_user_config_path,
    init_user_config,
    load_config,
)
from maxagent.utils.console import print_error, print_info, print_success

app = typer.Typer(help="Configuration management")
console = Console()


@app.command()
def init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
) -> None:
    """Initialize user configuration file"""
    config_path = get_user_config_path()

    if config_path.exists() and not force:
        print_info(f"Config already exists at: {config_path}")
        print_info("Use --force to overwrite")
        return

    # Create config
    created_path = init_user_config()
    print_success(f"Created config at: {created_path}")


@app.command()
def show(
    project: Optional[Path] = typer.Option(None, "--project", "-p", help="Project directory"),
) -> None:
    """Show current configuration"""
    try:
        config = load_config(project)

        # Create table
        table = Table(title="Current Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")

        # LiteLLM settings
        table.add_row("litellm.base_url", config.litellm.base_url)
        table.add_row("litellm.api_key", "***" if config.litellm.api_key else "(not set)")

        # Model settings
        table.add_row("model.default", config.model.default)
        table.add_row("model.temperature", str(config.model.temperature))
        table.add_row("model.max_tokens", str(config.model.max_tokens))

        # Tools
        table.add_row("tools.enabled", ", ".join(config.tools.enabled))
        table.add_row("tools.disabled", ", ".join(config.tools.disabled) or "(none)")

        # Security
        table.add_row("security.ignore_patterns", ", ".join(config.security.ignore_patterns[:3]) + "...")

        console.print(table)

    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command()
def path(
    project: Optional[Path] = typer.Option(None, "--project", "-p", help="Project directory"),
) -> None:
    """Show configuration file paths"""
    user_path = get_user_config_path()
    project_path = get_project_config_path(project)

    console.print(f"[bold]User config:[/bold] {user_path}")
    console.print(f"  Exists: {'[green]Yes[/green]' if user_path.exists() else '[red]No[/red]'}")

    console.print(f"\n[bold]Project config:[/bold] {project_path}")
    console.print(f"  Exists: {'[green]Yes[/green]' if project_path.exists() else '[red]No[/red]'}")


@app.command()
def edit_file(
    user: bool = typer.Option(False, "--user", "-u", help="Edit user config"),
    project: Optional[Path] = typer.Option(None, "--project", "-p", help="Project directory"),
) -> None:
    """Open configuration file in editor"""
    import os
    import subprocess

    if user:
        config_path = get_user_config_path()
        if not config_path.exists():
            print_info("User config doesn't exist. Creating...")
            init_user_config()
    else:
        config_path = get_project_config_path(project)
        if not config_path.exists():
            # Create minimal project config
            config_path.write_text(
                "# Project-specific MaxAgent configuration\n\n"
                "model:\n"
                "  # default: github_copilot/gpt-4\n"
                "  # temperature: 0.7\n",
                encoding="utf-8",
            )
            print_success(f"Created project config at: {config_path}")

    # Get editor from environment
    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "nano"))

    try:
        subprocess.run([editor, str(config_path)], check=True)
    except FileNotFoundError:
        print_error(f"Editor not found: {editor}")
        print_info(f"You can manually edit: {config_path}")
    except subprocess.CalledProcessError:
        print_error("Editor exited with error")


@app.command("cat")
def cat_config(
    user: bool = typer.Option(False, "--user", "-u", help="Show user config"),
    project: Optional[Path] = typer.Option(None, "--project", "-p", help="Project directory"),
) -> None:
    """Display configuration file content"""
    if user:
        config_path = get_user_config_path()
    else:
        config_path = get_project_config_path(project)

    if not config_path.exists():
        print_error(f"Config file not found: {config_path}")
        raise typer.Exit(1)

    content = config_path.read_text(encoding="utf-8")
    console.print(
        Panel(
            Syntax(content, "yaml", theme="monokai"),
            title=str(config_path),
            border_style="blue",
        )
    )


if __name__ == "__main__":
    app()
