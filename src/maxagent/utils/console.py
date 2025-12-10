"""Console utilities for rich output"""

from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.theme import Theme

# Custom theme
THEME = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "red bold",
        "success": "green",
        "dim": "dim",
        "user": "blue bold",
        "assistant": "green bold",
    }
)

# Global console instance
console = Console(theme=THEME)


def print_message(role: str, content: str, use_panel: bool = True) -> None:
    """Print a chat message"""
    if role == "user":
        title = "[user]You[/user]"
        border_style = "blue"
    elif role == "assistant":
        title = "[assistant]Assistant[/assistant]"
        border_style = "green"
    else:
        title = role.capitalize()
        border_style = "white"

    if use_panel:
        console.print(
            Panel(
                Markdown(content),
                title=title,
                title_align="left",
                border_style=border_style,
            )
        )
    else:
        console.print(f"[{border_style}]{title}:[/{border_style}]")
        console.print(Markdown(content))
        console.print()


def print_code(code: str, language: str = "python", title: Optional[str] = None) -> None:
    """Print syntax-highlighted code"""
    syntax = Syntax(code, language, theme="monokai", line_numbers=True)
    if title:
        console.print(Panel(syntax, title=title))
    else:
        console.print(syntax)


def print_diff(diff: str, title: Optional[str] = None) -> None:
    """Print a diff with syntax highlighting"""
    syntax = Syntax(diff, "diff", theme="monokai")
    if title:
        console.print(Panel(syntax, title=title, border_style="yellow"))
    else:
        console.print(syntax)


def print_info(message: str) -> None:
    """Print info message"""
    console.print(f"[info]{message}[/info]")


def print_warning(message: str) -> None:
    """Print warning message"""
    console.print(f"[warning]Warning: {message}[/warning]")


def print_error(message: str) -> None:
    """Print error message"""
    console.print(f"[error]Error: {message}[/error]")


def print_success(message: str) -> None:
    """Print success message"""
    console.print(f"[success]{message}[/success]")


def print_dim(message: str) -> None:
    """Print dimmed message"""
    console.print(f"[dim]{message}[/dim]")
