"""Tool base class and result models"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolParameter:
    """Tool parameter definition"""

    name: str
    type: str  # "string" | "integer" | "boolean" | "array" | "object"
    description: str
    required: bool = True
    enum: Optional[list[str]] = None
    default: Optional[Any] = None
    # For array types: define the structure of array items
    items: Optional[dict[str, Any]] = None
    # For object types: define nested properties
    properties: Optional[dict[str, Any]] = None


@dataclass
class ToolResult:
    """Tool execution result"""

    success: bool
    output: str
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    """Base class for all tools"""

    name: str = ""
    description: str = ""
    parameters: list[ToolParameter] = []
    risk_level: str = "low"  # "low" | "medium" | "high"

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """
        Execute the tool with given arguments.

        Args:
            **kwargs: Tool-specific arguments

        Returns:
            ToolResult with success status and output/error
        """
        pass

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert to OpenAI tool schema format"""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            # For array types: add items schema
            if param.items:
                prop["items"] = param.items
            # For object types: add properties schema
            if param.properties:
                prop["properties"] = param.properties

            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
