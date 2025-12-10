"""MCP (Model Context Protocol) CLI commands"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from maxagent.mcp.config import (
    MCPServerConfig,
    add_mcp_server,
    get_mcp_config_path,
    list_mcp_servers,
    load_mcp_config,
    remove_mcp_server,
    save_mcp_config,
)
from maxagent.mcp.client import MCPClient, create_mcp_client

app = typer.Typer(
    help="MCP (Model Context Protocol) server management",
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()

# Global variable to store extra args from '--' separator
_claude_extra_args: list[str] = []


def preprocess_argv() -> None:
    """Preprocess sys.argv to extract arguments after '--'

    This is called before Typer parses arguments.
    Arguments after '--' are stored in _claude_extra_args and removed from sys.argv.
    """
    global _claude_extra_args
    if "--" in sys.argv:
        separator_idx = sys.argv.index("--")
        _claude_extra_args = sys.argv[separator_idx + 1 :]
        # Remove '--' and everything after from sys.argv
        sys.argv = sys.argv[:separator_idx]


def get_project_mcp_config_path() -> Path:
    """Get project-level MCP config path"""
    return Path.cwd() / ".maxagent" / "mcp_servers.json"


def parse_claude_style_args(args: list[str]) -> tuple[dict[str, str], str, list[str]]:
    """Parse Claude-style arguments after '--'

    Format: env KEY1=VALUE1 KEY2=VALUE2 command arg1 arg2 ...

    Returns:
        tuple of (env_vars, command, args)
    """
    env_vars: dict[str, str] = {}
    command: str = ""
    cmd_args: list[str] = []

    if not args:
        return env_vars, command, cmd_args

    i = 0
    # Check if first token is 'env'
    if args[0] == "env":
        i = 1
        # Parse environment variables (KEY=VALUE format)
        while i < len(args) and "=" in args[i]:
            key, value = args[i].split("=", 1)
            env_vars[key] = value
            i += 1

    # Remaining is command and its arguments
    if i < len(args):
        command = args[i]
        cmd_args = args[i + 1 :] if i + 1 < len(args) else []

    return env_vars, command, cmd_args


@app.command("add")
def add_server(
    name: str = typer.Argument(..., help="Server name/identifier"),
    url: Optional[str] = typer.Argument(None, help="Server URL (for HTTP transport)"),
    transport: str = typer.Option(
        "http",
        "--transport",
        "-t",
        help="Transport type: http, stdio",
    ),
    scope: str = typer.Option(
        "user",
        "--scope",
        "-s",
        help="Configuration scope: user (global) or project (local)",
    ),
    command: Optional[str] = typer.Option(
        None,
        "--command",
        "-c",
        help="Command to execute (for stdio transport)",
    ),
    args: Optional[list[str]] = typer.Option(
        None,
        "--arg",
        "-a",
        help="Command argument (can be used multiple times, for stdio transport)",
    ),
    header: Optional[list[str]] = typer.Option(
        None,
        "--header",
        help="HTTP header in 'Key: Value' format (can be used multiple times)",
    ),
    env: Optional[list[str]] = typer.Option(
        None,
        "--env",
        "-e",
        help="Environment variable 'KEY=VALUE' (can be used multiple times)",
    ),
    disabled: bool = typer.Option(
        False,
        "--disabled",
        help="Add server in disabled state",
    ),
) -> None:
    """
    Add a new MCP server.

    Examples:
        # HTTP transport
        llc mcp add web-reader https://example.com/mcp

        # With authentication header
        llc mcp add web-reader https://api.example.com/mcp --header "Authorization: Bearer token123"

        # Stdio transport (native style)
        llc mcp add searxng --command mcp-searxng --env "SEARXNG_URL=http://localhost:8888"

        # Stdio transport with arguments
        llc mcp add myserver --command python --arg "-m" --arg "my_mcp_server"

        # Claude-compatible style (with -- separator)
        llc mcp add searxng --scope user --transport stdio -- env SEARXNG_URL=http://localhost:8888 mcp-searxng

        # Claude-compatible with command arguments
        llc mcp add myserver --transport stdio -- env KEY=VALUE python -m my_mcp_server

        # Project-level configuration
        llc mcp add local-server --scope project --command ./local-mcp.sh
    """
    # Check for Claude-style arguments after '--'
    # These are pre-processed and stored in _claude_extra_args
    global _claude_extra_args
    claude_env_vars: dict[str, str] = {}
    claude_command: Optional[str] = None
    claude_args: list[str] = []

    if _claude_extra_args:
        claude_env_vars, claude_command, claude_args = parse_claude_style_args(_claude_extra_args)
        # Reset after use
        extra_args_copy = _claude_extra_args.copy()
        _claude_extra_args = []
        # If we got a command from Claude-style, use it
        if claude_command:
            command = claude_command
            args = claude_args if claude_args else args
            transport = "stdio"

    # Merge environment variables
    env_vars: dict[str, str] = {}

    # First, add Claude-style env vars
    if claude_env_vars:
        env_vars.update(claude_env_vars)

    # Then, add --env option values (can override)
    if env:
        for e in env:
            if "=" in e:
                key, value = e.split("=", 1)
                env_vars[key.strip()] = value.strip()
            else:
                console.print(f"[yellow]Warning: Invalid env format '{e}', expected 'KEY=VALUE'[/]")

    # Determine transport type
    if command:
        transport = "stdio"
    elif url and transport == "http":
        transport = "http"

    # Validate inputs
    if transport == "http" and not url:
        console.print("[red]Error: URL is required for HTTP transport[/]")
        raise typer.Exit(1)

    if transport == "stdio" and not command:
        console.print("[red]Error: --command is required for stdio transport[/]")
        console.print(
            "[dim]Tip: Use Claude-style syntax: llc mcp add <name> --transport stdio -- env KEY=VALUE command[/]"
        )
        raise typer.Exit(1)

    # Parse headers
    headers: dict[str, str] = {}
    if header:
        for h in header:
            if ":" in h:
                key, value = h.split(":", 1)
                headers[key.strip()] = value.strip()
            else:
                console.print(
                    f"[yellow]Warning: Invalid header format '{h}', expected 'Key: Value'[/]"
                )

    # Determine config path based on scope
    if scope == "project":
        config_path = get_project_mcp_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        # Load project config or create new
        if config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
            from maxagent.mcp.config import MCPConfig

            config = MCPConfig(**data)
        else:
            from maxagent.mcp.config import MCPConfig

            config = MCPConfig()
    else:
        config = load_mcp_config()
        config_path = get_mcp_config_path()

    server = MCPServerConfig(
        name=name,
        type=transport,
        url=url,
        headers=headers,
        env_vars={},  # Deprecated, use env instead
        command=command,
        args=args or [],
        env=env_vars,
        enabled=not disabled,
    )

    config.servers[name] = server

    # Save to appropriate location
    with open(config_path, "w") as f:
        json.dump(config.model_dump(), f, indent=2)

    console.print(f"[green]Added MCP server:[/] {name}")
    if transport == "http":
        console.print(f"  URL: {url}")
    else:
        console.print(f"  Command: {command}")
        if args:
            console.print(f"  Args: {' '.join(args)}")
    console.print(f"  Transport: {transport}")
    console.print(f"  Scope: {scope}")
    if headers:
        console.print(f"  Headers: {len(headers)} configured")
    if env_vars:
        console.print(f"  Env vars: {', '.join(env_vars.keys())}")
    console.print(f"  Status: {'Enabled' if not disabled else 'Disabled'}")
    console.print(f"  Config: {config_path}")


@app.command("remove")
def remove_server(
    name: str = typer.Argument(..., help="Server name to remove"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Remove without confirmation",
    ),
) -> None:
    """
    Remove an MCP server.

    Examples:
        llc mcp remove web-reader
        llc mcp remove web-reader --force
    """
    config = load_mcp_config()

    if name not in config.servers:
        console.print(f"[red]Server not found:[/] {name}")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"Remove MCP server '{name}'?")
        if not confirm:
            console.print("[dim]Cancelled[/]")
            raise typer.Exit(0)

    if remove_mcp_server(name):
        console.print(f"[green]Removed MCP server:[/] {name}")
    else:
        console.print(f"[red]Failed to remove server:[/] {name}")
        raise typer.Exit(1)


@app.command("list")
def list_servers(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed information",
    ),
    no_test: bool = typer.Option(
        False,
        "--no-test",
        help="Skip connection testing",
    ),
) -> None:
    """
    List all configured MCP servers and test their connection status.

    Examples:
        llc mcp list
        llc mcp list -v
        llc mcp list --no-test
    """
    servers = list_mcp_servers()

    if not servers:
        console.print("[dim]No MCP servers configured[/]")
        console.print("\nUse [bold]llc mcp add[/] to add a server")
        return

    # Test connections if not skipped
    connection_status: dict[str, tuple[bool, str, int]] = {}
    if not no_test:
        console.print("[dim]Testing server connections...[/]\n")
        connection_status = asyncio.run(_test_all_servers(servers))

    table = Table(title="MCP Servers")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("URL/Command", style="blue")
    table.add_column("Status", style="yellow")
    table.add_column("Connection", style="bold")

    if verbose:
        table.add_column("Details", style="dim")

    for name, server in servers.items():
        status = "[green]Enabled[/]" if server.enabled else "[red]Disabled[/]"

        # Show URL for HTTP, command for stdio
        if server.type == "stdio":
            url_or_cmd = server.command or "-"
            if server.args:
                url_or_cmd += f" {' '.join(server.args)}"
        else:
            url_or_cmd = server.url or "-"

        # Connection status
        if no_test:
            conn_status = "[dim]-[/]"
        elif not server.enabled:
            conn_status = "[dim]Skipped[/]"
        elif name in connection_status:
            ok, msg, tool_count = connection_status[name]
            if ok:
                conn_status = f"[green]OK[/] ({tool_count} tools)"
            else:
                conn_status = f"[red]Failed[/]"
        else:
            conn_status = "[yellow]Unknown[/]"

        row = [name, server.type, url_or_cmd, status, conn_status]

        if verbose:
            details = []
            if server.type == "http" and server.headers:
                details.append(f"Headers: {', '.join(server.headers.keys())}")
            if server.env:
                details.append(f"Env: {', '.join(server.env.keys())}")
            # Add error message if connection failed
            if name in connection_status:
                ok, msg, _ = connection_status[name]
                if not ok and msg:
                    details.append(f"Error: {msg}")
            row.append("; ".join(details) if details else "-")

        table.add_row(*row)

    console.print(table)


async def _test_all_servers(
    servers: dict[str, MCPServerConfig],
) -> dict[str, tuple[bool, str, int]]:
    """Test all enabled MCP servers concurrently.

    Returns:
        dict mapping server name to (success, error_message, tool_count)
    """
    results: dict[str, tuple[bool, str, int]] = {}

    async def test_one(name: str, server: MCPServerConfig) -> tuple[str, bool, str, int]:
        if not server.enabled:
            return name, False, "Disabled", 0
        try:
            client = create_mcp_client(server)
            async with client:
                await client.initialize()
                tools = await client.list_tools()
                return name, True, "", len(tools)
        except Exception as e:
            return name, False, str(e), 0

    # Run all tests concurrently
    tasks = [test_one(name, server) for name, server in servers.items() if server.enabled]
    if tasks:
        results_list = await asyncio.gather(*tasks)
        for name, ok, msg, tool_count in results_list:
            results[name] = (ok, msg, tool_count)

    return results


@app.command("enable")
def enable_server(
    name: str = typer.Argument(..., help="Server name to enable"),
) -> None:
    """
    Enable an MCP server.

    Examples:
        llc mcp enable web-reader
    """
    config = load_mcp_config()

    if name not in config.servers:
        console.print(f"[red]Server not found:[/] {name}")
        raise typer.Exit(1)

    config.servers[name].enabled = True
    save_mcp_config(config)
    console.print(f"[green]Enabled MCP server:[/] {name}")


@app.command("disable")
def disable_server(
    name: str = typer.Argument(..., help="Server name to disable"),
) -> None:
    """
    Disable an MCP server.

    Examples:
        llc mcp disable web-reader
    """
    config = load_mcp_config()

    if name not in config.servers:
        console.print(f"[red]Server not found:[/] {name}")
        raise typer.Exit(1)

    config.servers[name].enabled = False
    save_mcp_config(config)
    console.print(f"[yellow]Disabled MCP server:[/] {name}")


@app.command("test")
def test_server(
    name: str = typer.Argument(..., help="Server name to test"),
) -> None:
    """
    Test connection to an MCP server.

    Examples:
        llc mcp test web-reader
    """
    config = load_mcp_config()

    if name not in config.servers:
        console.print(f"[red]Server not found:[/] {name}")
        raise typer.Exit(1)

    server = config.servers[name]
    asyncio.run(_test_server(server))


async def _test_server(server: MCPServerConfig) -> None:
    """Test MCP server connection"""
    console.print(f"[bold]Testing MCP server:[/] {server.name}")
    if server.type == "stdio":
        console.print(f"  Command: {server.get_resolved_command()}")
        if server.args:
            console.print(f"  Args: {' '.join(server.args)}")
    else:
        console.print(f"  URL: {server.get_resolved_url()}")

    try:
        client = create_mcp_client(server)
        async with client:
            # Initialize
            with console.status("[bold green]Initializing..."):
                result = await client.initialize()
            console.print("[green]Initialization successful[/]")

            # List tools
            with console.status("[bold green]Listing tools..."):
                tools = await client.list_tools()

            if tools:
                console.print(f"\n[bold]Available tools ({len(tools)}):[/]")
                table = Table()
                table.add_column("Name", style="cyan")
                table.add_column("Description", style="dim")

                for tool in tools:
                    desc = tool.description
                    if len(desc) > 60:
                        desc = desc[:57] + "..."
                    table.add_row(tool.name, desc)

                console.print(table)
            else:
                console.print("[yellow]No tools available[/]")

    except Exception as e:
        console.print(f"[red]Connection failed:[/] {e}")
        raise typer.Exit(1)


@app.command("tools")
def list_tools(
    name: Optional[str] = typer.Argument(None, help="Server name (optional, shows all if omitted)"),
) -> None:
    """
    List tools from MCP servers.

    Examples:
        llc mcp tools                  # List all tools from all servers
        llc mcp tools web-reader       # List tools from specific server
    """
    asyncio.run(_list_tools(name))


async def _list_tools(server_name: Optional[str]) -> None:
    """List tools from MCP servers"""
    config = load_mcp_config()

    if server_name:
        if server_name not in config.servers:
            console.print(f"[red]Server not found:[/] {server_name}")
            raise typer.Exit(1)
        servers = {server_name: config.servers[server_name]}
    else:
        servers = {n: s for n, s in config.servers.items() if s.enabled}

    if not servers:
        console.print("[dim]No MCP servers configured or enabled[/]")
        return

    all_tools: list[tuple[str, str, str]] = []

    for name, server in servers.items():
        try:
            client = create_mcp_client(server)
            async with client:
                tools = await client.list_tools()
                for tool in tools:
                    all_tools.append((name, tool.name, tool.description))
        except Exception as e:
            console.print(f"[yellow]Failed to get tools from {name}:[/] {e}")

    if all_tools:
        table = Table(title="MCP Tools")
        table.add_column("Server", style="green")
        table.add_column("Tool", style="cyan")
        table.add_column("Description", style="dim")

        for server, tool_name, desc in all_tools:
            if len(desc) > 50:
                desc = desc[:47] + "..."
            table.add_row(server, tool_name, desc)

        console.print(table)
    else:
        console.print("[dim]No tools available[/]")


@app.command("config")
def show_config() -> None:
    """
    Show MCP configuration file path and content.

    Examples:
        llc mcp config
    """
    config_path = get_mcp_config_path()
    console.print(f"[bold]Config file:[/] {config_path}")

    if config_path.exists():
        with open(config_path) as f:
            content = f.read()
        console.print(Panel(content, title="Configuration", border_style="blue"))
    else:
        console.print("[dim]No configuration file exists yet[/]")


if __name__ == "__main__":
    app()
