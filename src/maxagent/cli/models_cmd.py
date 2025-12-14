"""Models CLI commands - List available models from providers"""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

app = typer.Typer(help="List and manage available models")
console = Console()

# Copilot models endpoint
COPILOT_MODELS_URL = "https://api.githubcopilot.com/models"


async def fetch_copilot_models() -> list[dict]:
    """Fetch available models from GitHub Copilot API

    Returns:
        List of model dictionaries with model info
    """
    import httpx
    from maxagent.auth.github_copilot import GitHubCopilotAuth

    auth = GitHubCopilotAuth()

    # Ensure we have a valid token
    try:
        await auth.ensure_valid_token()
    except ValueError as e:
        raise ValueError(str(e))

    headers = auth.get_api_headers(include_initiator=False)

    async with httpx.AsyncClient() as client:
        response = await client.get(
            COPILOT_MODELS_URL,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

        # The API returns {"data": [...]} or just a list
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        elif isinstance(data, list):
            return data
        else:
            return []


@app.callback(invoke_without_command=True)
def models_default(
    ctx: typer.Context,
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        "-p",
        help="Filter by provider (copilot, glm, openai)",
    ),
) -> None:
    """List available models from configured providers"""
    if ctx.invoked_subcommand is None:
        # Default behavior: list copilot models
        list_models(provider=provider or "copilot")


@app.command("list")
def list_models(
    provider: str = typer.Option(
        "copilot",
        "--provider",
        "-p",
        help="Provider to list models from (copilot, glm, openai, all)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed model information",
    ),
) -> None:
    """List available models from a provider

    Examples:
        mcode models list                    # List Copilot models
        mcode models list -p copilot         # List Copilot models
        mcode models list -p all             # List all configured models
        mcode models list -v                 # Show verbose output
    """
    if provider.lower() == "copilot":
        _list_copilot_models(verbose)
    elif provider.lower() == "all":
        _list_all_models(verbose)
    else:
        console.print(f"[yellow]Provider '{provider}' model listing not implemented yet.[/yellow]")
        console.print("Supported: copilot, all")


def _list_copilot_models(verbose: bool = False) -> None:
    """List GitHub Copilot available models"""
    from maxagent.auth.github_copilot import GitHubCopilotAuth

    auth = GitHubCopilotAuth()

    # Check authentication first
    if not auth.is_authenticated:
        console.print(
            Panel(
                "[red]Not authenticated with GitHub Copilot[/red]\n\n"
                "Run [bold]mcode auth copilot[/bold] to authenticate first.",
                title="Authentication Required",
            )
        )
        raise typer.Exit(1)

    console.print("[dim]Fetching models from GitHub Copilot...[/dim]\n")

    async def fetch() -> list[dict]:
        return await fetch_copilot_models()

    try:
        models = asyncio.run(fetch())
    except Exception as e:
        console.print(f"[red]Failed to fetch models: {e}[/red]")
        raise typer.Exit(1)

    if not models:
        console.print("[yellow]No models returned from API[/yellow]")
        return

    # Create table
    table = Table(title="GitHub Copilot Available Models")
    table.add_column("Model ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="green")
    table.add_column("Vendor", style="yellow")
    table.add_column("Version", style="dim")

    if verbose:
        table.add_column("Family", style="dim")
        table.add_column("Preview", style="dim")

    # Sort models by vendor then name
    sorted_models = sorted(models, key=lambda m: (m.get("vendor", ""), m.get("name", "")))

    for model in sorted_models:
        model_id = model.get("id", model.get("name", "unknown"))
        name = model.get("name", model_id)
        vendor = model.get("vendor", "-")
        version = model.get("version", "-")

        if verbose:
            family = model.get("family", "-")
            is_preview = "Yes" if model.get("preview", False) else "No"
            table.add_row(model_id, name, vendor, version, family, is_preview)
        else:
            table.add_row(model_id, name, vendor, version)

    console.print(table)
    console.print(f"\n[dim]Total: {len(models)} models[/dim]")

    # Show usage hint
    console.print('\n[dim]Usage: mcode chat --model <model_id> "your question"[/dim]')


def _list_all_models(verbose: bool = False) -> None:
    """List all configured models from config file"""
    from maxagent.config.loader import load_config

    config = load_config()

    table = Table(title="Configured Models")
    table.add_column("Provider", style="yellow")
    table.add_column("Model", style="cyan")
    table.add_column("Max Tokens", style="green", justify="right")
    table.add_column("Context Length", style="dim", justify="right")

    model_count = 0

    if config.model and config.model.models:
        for key, model_config in config.model.models.items():
            # Parse provider/model format
            if "/" in key:
                provider, model_name = key.split("/", 1)
            else:
                provider = "-"
                model_name = key

            max_tokens = str(model_config.max_tokens) if model_config.max_tokens else "-"
            context_length = (
                str(model_config.context_length) if model_config.context_length else "-"
            )

            table.add_row(provider, model_name, max_tokens, context_length)
            model_count += 1

    if model_count == 0:
        console.print("[yellow]No models configured in ~/.mcode/config.yaml[/yellow]")
        return

    console.print(table)
    console.print(f"\n[dim]Total: {model_count} configured models[/dim]")

    # Show default model
    if config.model and config.model.default:
        console.print(f"\n[dim]Default model: {config.model.default}[/dim]")


if __name__ == "__main__":
    app()
