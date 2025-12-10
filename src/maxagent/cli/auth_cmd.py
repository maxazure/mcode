"""Authentication CLI commands"""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(help="Authentication commands")
console = Console()


@app.command("copilot")
def auth_copilot(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force re-authentication even if already authenticated",
    ),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Don't automatically open browser",
    ),
) -> None:
    """Authenticate with GitHub Copilot

    Uses OAuth Device Flow to authenticate with GitHub and obtain
    a Copilot API token. The token is stored locally for future use.
    """
    from maxagent.auth.github_copilot import GitHubCopilotAuth

    auth = GitHubCopilotAuth(auto_open_browser=not no_browser)

    # Check if already authenticated
    if not force and auth.has_valid_token:
        console.print(
            Panel(
                "[green]Already authenticated with GitHub Copilot![/green]\n\n"
                f"Token location: {auth.token_file}\n\n"
                "Use [bold]--force[/bold] to re-authenticate.",
                title="Authentication Status",
            )
        )
        return

    async def do_auth() -> None:
        """Run the authentication flow"""

        def callback(status: str, data: dict) -> None:
            if status == "device_code":
                console.print("\n[bold blue]GitHub Copilot Authentication[/bold blue]\n")
            elif status == "waiting_for_user":
                console.print(
                    Panel(
                        f"[bold]1.[/bold] Open: [link={data['verification_uri']}]{data['verification_uri']}[/link]\n"
                        f"[bold]2.[/bold] Enter code: [bold green]{data['user_code']}[/bold green]",
                        title="Authorization Required",
                    )
                )
                if not no_browser:
                    console.print("[dim]Browser should open automatically...[/dim]\n")
            elif status == "github_token_received":
                console.print("[green]✓[/green] GitHub authorization successful")
            elif status == "copilot_token_received":
                console.print("[green]✓[/green] Copilot token obtained")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Waiting for authorization...", total=None)

            try:
                await auth.authenticate(callback)
                progress.update(task, description="Authentication complete!")
            except TimeoutError:
                progress.stop()
                console.print("\n[red]✗ Authentication timed out[/red]")
                console.print("Please try again and complete the authorization within 5 minutes.")
                raise typer.Exit(1)
            except PermissionError:
                progress.stop()
                console.print("\n[red]✗ Authorization denied[/red]")
                console.print(
                    "You denied the authorization request. Please try again if this was a mistake."
                )
                raise typer.Exit(1)
            except Exception as e:
                progress.stop()
                console.print(f"\n[red]✗ Authentication failed: {e}[/red]")
                raise typer.Exit(1)

        console.print(
            Panel(
                f"[green]Authentication successful![/green]\n\n"
                f"Token saved to: {auth.token_file}\n\n"
                "You can now use GitHub Copilot models:\n"
                "  [bold]llc chat --provider copilot[/bold]",
                title="Success",
            )
        )

    asyncio.run(do_auth())


@app.command("status")
def auth_status() -> None:
    """Check authentication status for all providers"""
    from maxagent.auth.github_copilot import GitHubCopilotAuth
    from rich.table import Table

    table = Table(title="Authentication Status")
    table.add_column("Provider", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details")

    # Check GitHub Copilot
    copilot_auth = GitHubCopilotAuth()
    if copilot_auth.has_valid_token:
        token = copilot_auth.load_token()
        if token:
            import datetime

            expires_at = datetime.datetime.fromtimestamp(token.expires_at)
            table.add_row(
                "GitHub Copilot",
                "[green]✓ Authenticated[/green]",
                f"Expires: {expires_at.strftime('%Y-%m-%d %H:%M:%S')}",
            )
        else:
            table.add_row(
                "GitHub Copilot",
                "[green]✓ Authenticated[/green]",
                "",
            )
    elif copilot_auth.is_authenticated:
        table.add_row(
            "GitHub Copilot",
            "[yellow]⚠ Token expired[/yellow]",
            "Run 'llc auth copilot' to refresh",
        )
    else:
        table.add_row(
            "GitHub Copilot",
            "[red]✗ Not authenticated[/red]",
            "Run 'llc auth copilot' to authenticate",
        )

    console.print(table)


@app.command("logout")
def auth_logout(
    provider: str = typer.Argument(
        ...,
        help="Provider to logout from (copilot)",
    ),
) -> None:
    """Logout from a provider (remove stored credentials)"""
    if provider.lower() == "copilot":
        from maxagent.auth.github_copilot import GitHubCopilotAuth

        auth = GitHubCopilotAuth()
        if auth.is_authenticated:
            auth.clear_token()
            console.print("[green]✓[/green] Logged out from GitHub Copilot")
        else:
            console.print("[yellow]Not authenticated with GitHub Copilot[/yellow]")
    else:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        console.print("Supported providers: copilot")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
