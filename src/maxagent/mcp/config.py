"""MCP configuration management"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server"""

    name: str = Field(..., description="Server name/identifier")
    type: str = Field(
        default="http",
        description="Transport type: http, stdio",
    )
    # HTTP transport fields
    url: Optional[str] = Field(default=None, description="Server URL (for HTTP transport)")
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="HTTP headers (e.g., Authorization)",
    )
    # Stdio transport fields
    command: Optional[str] = Field(
        default=None, description="Command to execute (for stdio transport)"
    )
    args: list[str] = Field(
        default_factory=list,
        description="Command arguments (for stdio transport)",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables for the subprocess (for stdio transport)",
    )
    # Common fields
    enabled: bool = Field(default=True, description="Whether the server is enabled")
    # For environment variable substitution
    env_vars: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables for header/url substitution",
    )

    def get_resolved_headers(self) -> dict[str, str]:
        """Get headers with environment variable substitution"""
        import re

        resolved = {}
        pattern = r"\$\{(\w+)\}"

        for key, value in self.headers.items():
            # Support ${VAR} substitution anywhere in the value
            result = value
            for match in re.finditer(pattern, value):
                env_var = match.group(1)
                env_value = os.environ.get(env_var, "")
                result = result.replace(f"${{{env_var}}}", env_value)

            # Also support simple $VAR at the start
            if result.startswith("$") and not result.startswith("${"):
                env_var = result[1:].split()[0]  # Get first word after $
                result = os.environ.get(env_var, "")

            resolved[key] = result
        return resolved

    def get_resolved_url(self) -> Optional[str]:
        """Get URL with environment variable substitution"""
        if self.url is None:
            return None
        url = self.url
        # Support ${VAR} substitution in URL
        import re

        pattern = r"\$\{(\w+)\}"
        for match in re.finditer(pattern, url):
            env_var = match.group(1)
            value = os.environ.get(env_var, "")
            url = url.replace(f"${{{env_var}}}", value)
        return url

    def get_resolved_env(self) -> dict[str, str]:
        """Get environment variables with substitution for stdio transport"""
        import re

        resolved = dict(os.environ)  # Start with current environment
        pattern = r"\$\{(\w+)\}"

        for key, value in self.env.items():
            result = value
            for match in re.finditer(pattern, value):
                env_var = match.group(1)
                env_value = os.environ.get(env_var, "")
                result = result.replace(f"${{{env_var}}}", env_value)
            resolved[key] = result

        return resolved

    def get_resolved_command(self) -> Optional[str]:
        """Get command with environment variable substitution"""
        if self.command is None:
            return None
        import re

        command = self.command
        pattern = r"\$\{(\w+)\}"
        for match in re.finditer(pattern, command):
            env_var = match.group(1)
            value = os.environ.get(env_var, "")
            command = command.replace(f"${{{env_var}}}", value)
        return command


class MCPConfig(BaseModel):
    """MCP configuration containing all servers"""

    servers: dict[str, MCPServerConfig] = Field(
        default_factory=dict,
        description="Map of server name to configuration",
    )


def get_mcp_config_path() -> Path:
    """Get the MCP configuration file path"""
    config_dir = Path.home() / ".llc"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "mcp_servers.json"


def load_mcp_config() -> MCPConfig:
    """Load MCP configuration from file

    Returns:
        MCPConfig: The loaded configuration
    """
    config_path = get_mcp_config_path()
    if not config_path.exists():
        return MCPConfig()

    try:
        with open(config_path, "r") as f:
            data = json.load(f)
        return MCPConfig(**data)
    except Exception:
        return MCPConfig()


def save_mcp_config(config: MCPConfig) -> None:
    """Save MCP configuration to file

    Args:
        config: The configuration to save
    """
    config_path = get_mcp_config_path()
    with open(config_path, "w") as f:
        json.dump(config.model_dump(), f, indent=2)


def add_mcp_server(
    name: str,
    url: Optional[str] = None,
    transport_type: str = "http",
    headers: Optional[dict[str, str]] = None,
    env_vars: Optional[dict[str, str]] = None,
    command: Optional[str] = None,
    args: Optional[list[str]] = None,
    env: Optional[dict[str, str]] = None,
) -> MCPServerConfig:
    """Add a new MCP server to configuration

    Args:
        name: Server name/identifier
        url: Server URL (for HTTP transport)
        transport_type: Transport type (http, stdio)
        headers: HTTP headers (for HTTP transport)
        env_vars: Environment variables for substitution
        command: Command to execute (for stdio transport)
        args: Command arguments (for stdio transport)
        env: Environment variables for subprocess (for stdio transport)

    Returns:
        The created server configuration
    """
    config = load_mcp_config()

    server = MCPServerConfig(
        name=name,
        type=transport_type,
        url=url,
        headers=headers or {},
        env_vars=env_vars or {},
        command=command,
        args=args or [],
        env=env or {},
    )

    config.servers[name] = server
    save_mcp_config(config)
    return server


def remove_mcp_server(name: str) -> bool:
    """Remove an MCP server from configuration

    Args:
        name: Server name to remove

    Returns:
        True if server was removed, False if not found
    """
    config = load_mcp_config()
    if name in config.servers:
        del config.servers[name]
        save_mcp_config(config)
        return True
    return False


def list_mcp_servers() -> dict[str, MCPServerConfig]:
    """List all configured MCP servers

    Returns:
        Dictionary of server name to configuration
    """
    config = load_mcp_config()
    return config.servers
