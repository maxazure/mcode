"""MCP Tool wrapper and registry for integration with MaxAgent tool system"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from maxagent.mcp.client import (
    MCPClient,
    MCPClientBase,
    MCPToolDefinition,
    MCPToolResult,
    create_mcp_client,
)
from maxagent.mcp.config import MCPServerConfig, load_mcp_config
from maxagent.tools.base import BaseTool, ToolParameter, ToolResult


class MCPTool(BaseTool):
    """Wrapper for MCP tool to work with MaxAgent's tool system"""

    def __init__(
        self,
        mcp_tool: MCPToolDefinition,
        client: MCPClientBase,
    ):
        """Initialize MCP tool wrapper

        Args:
            mcp_tool: MCP tool definition
            client: MCP client for calling the tool
        """
        self.mcp_tool = mcp_tool
        self.client = client

        # Convert MCP schema to MaxAgent parameters
        self.parameters = self._convert_schema_to_parameters(mcp_tool.input_schema)

        # Set tool name and description
        self.name = f"mcp_{mcp_tool.server_name}_{mcp_tool.name}"
        self.description = f"[MCP:{mcp_tool.server_name}] {mcp_tool.description}"

        # Store original MCP tool name for calling
        self._mcp_tool_name = mcp_tool.name
        self._mcp_tool_name = mcp_tool.name

    def _convert_schema_to_parameters(self, schema: dict[str, Any]) -> list[ToolParameter]:
        """Convert JSON Schema to ToolParameter list"""
        parameters = []

        properties = schema.get("properties", {})
        required = schema.get("required", [])

        for name, prop in properties.items():
            param = ToolParameter(
                name=name,
                type=prop.get("type", "string"),
                description=prop.get("description", ""),
                required=name in required,
            )
            parameters.append(param)

        return parameters

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the MCP tool

        Args:
            **kwargs: Tool arguments

        Returns:
            ToolResult with the tool output
        """
        try:
            result = await self.client.call_tool(self._mcp_tool_name, kwargs)

            if result.is_error:
                return ToolResult(
                    success=False,
                    output="",
                    error=result.get_text(),
                )

            return ToolResult(
                success=True,
                output=result.get_text(),
                error=None,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )


@dataclass
class MCPToolRegistry:
    """Registry for MCP tools from all configured servers"""

    _clients: dict[str, MCPClientBase] = field(default_factory=dict)
    _tools: dict[str, MCPTool] = field(default_factory=dict)
    _initialized: bool = False

    async def initialize(self) -> None:
        """Initialize all MCP servers and load their tools"""
        if self._initialized:
            return

        config = load_mcp_config()

        for name, server_config in config.servers.items():
            if not server_config.enabled:
                continue

            try:
                client = create_mcp_client(server_config)
                await client.initialize()

                tools = await client.list_tools()
                self._clients[name] = client

                for tool_def in tools:
                    mcp_tool = MCPTool(tool_def, client)
                    self._tools[mcp_tool.name] = mcp_tool

            except Exception as e:
                # Log error but continue with other servers
                print(f"Failed to initialize MCP server {name}: {e}")

        self._initialized = True

    async def close(self) -> None:
        """Close all MCP clients"""
        for client in self._clients.values():
            try:
                await client.close()
            except Exception:
                pass

        self._clients.clear()
        self._tools.clear()
        self._initialized = False

    def get_tools(self) -> list[MCPTool]:
        """Get all registered MCP tools

        Returns:
            List of MCP tool wrappers
        """
        return list(self._tools.values())

    def get_tool(self, name: str) -> Optional[MCPTool]:
        """Get a specific MCP tool by name

        Args:
            name: Tool name

        Returns:
            MCPTool or None if not found
        """
        return self._tools.get(name)

    def get_openai_schemas(self) -> list[dict[str, Any]]:
        """Get OpenAI function schemas for all MCP tools

        Returns:
            List of OpenAI function schemas
        """
        return [tool.to_openai_schema() for tool in self._tools.values()]

    async def __aenter__(self) -> "MCPToolRegistry":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


# Global registry instance
_global_registry: Optional[MCPToolRegistry] = None


async def get_mcp_registry() -> MCPToolRegistry:
    """Get the global MCP tool registry

    Returns:
        Initialized MCPToolRegistry
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = MCPToolRegistry()
        await _global_registry.initialize()
    return _global_registry


async def reset_mcp_registry() -> None:
    """Reset the global MCP tool registry"""
    global _global_registry
    if _global_registry:
        await _global_registry.close()
    _global_registry = None
