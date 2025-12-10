"""Tool registry for managing and executing tools"""

from __future__ import annotations

import json
from typing import Any, Optional

from .base import BaseTool, ToolResult


class ToolRegistry:
    """Registry for managing tools"""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool"""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Unregister a tool by name"""
        if name in self._tools:
            del self._tools[name]

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name"""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names"""
        return list(self._tools.keys())

    def get_all_tools(self) -> list[BaseTool]:
        """Get all registered tools"""
        return list(self._tools.values())

    def get_openai_schemas(self, tool_names: Optional[list[str]] = None) -> list[dict[str, Any]]:
        """
        Get OpenAI tool schemas for specified tools or all tools.

        Args:
            tool_names: Optional list of tool names to include. If None, includes all.

        Returns:
            List of OpenAI-format tool schemas
        """
        tools = self._tools.values()
        if tool_names:
            tools = [t for t in tools if t.name in tool_names]

        return [tool.to_openai_schema() for tool in tools]

    async def execute(self, name: str, arguments: str | dict[str, Any]) -> ToolResult:
        """
        Execute a tool by name with given arguments.

        Args:
            name: Tool name
            arguments: JSON string or dict of arguments

        Returns:
            ToolResult with execution outcome
        """
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown tool: {name}",
            )

        try:
            # Parse arguments if string
            if isinstance(arguments, str):
                kwargs = json.loads(arguments)
            else:
                kwargs = arguments

            return await tool.execute(**kwargs)

        except json.JSONDecodeError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid arguments JSON: {e}",
            )
        except TypeError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid arguments: {e}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Tool execution failed: {e}",
            )

    def __contains__(self, name: str) -> bool:
        """Check if a tool is registered"""
        return name in self._tools

    def __len__(self) -> int:
        """Return number of registered tools"""
        return len(self._tools)
