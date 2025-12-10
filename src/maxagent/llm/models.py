"""LLM data models"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolCallFunction:
    """Tool call function details"""

    name: str
    arguments: str  # JSON string


@dataclass
class ToolCall:
    """Tool call from LLM response"""

    id: str
    type: str = "function"
    function: ToolCallFunction = field(default_factory=lambda: ToolCallFunction("", ""))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolCall":
        """Create from dictionary"""
        func_data = data.get("function", {})
        return cls(
            id=data.get("id", ""),
            type=data.get("type", "function"),
            function=ToolCallFunction(
                name=func_data.get("name", ""),
                arguments=func_data.get("arguments", "{}"),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "type": self.type,
            "function": {
                "name": self.function.name,
                "arguments": self.function.arguments,
            },
        }


@dataclass
class Message:
    """Chat message"""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API request"""
        result: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            result["content"] = self.content
        if self.tool_calls:
            result["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.name:
            result["name"] = self.name
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        """Create from dictionary"""
        tool_calls = None
        if tc_data := data.get("tool_calls"):
            tool_calls = [ToolCall.from_dict(tc) for tc in tc_data]

        return cls(
            role=data.get("role", "user"),
            content=data.get("content"),
            tool_calls=tool_calls,
            tool_call_id=data.get("tool_call_id"),
            name=data.get("name"),
        )


@dataclass
class Usage:
    """Token usage information"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Usage":
        """Create from dictionary"""
        return cls(
            prompt_tokens=data.get("prompt_tokens", 0),
            completion_tokens=data.get("completion_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
        )


@dataclass
class ChatResponse:
    """Chat completion response"""

    id: str
    model: str
    content: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None
    finish_reason: str = "stop"
    usage: Usage = field(default_factory=Usage)
    # Thinking content fields
    thinking_content: Optional[str] = None  # GLM <think>...</think> content
    reasoning_content: Optional[str] = None  # DeepSeek reasoning_content field

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "ChatResponse":
        """Create from API response"""
        import json as json_module

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        tool_calls = None
        content = message.get("content")

        # Handle GLM thinking model bug: tool_calls embedded in content as JSON
        # This happens when GLM z1 model returns tool_calls as a JSON string in content
        if content and isinstance(content, str) and content.startswith('{"index":'):
            try:
                embedded_data = json_module.loads(content)
                delta = embedded_data.get("delta", {})
                if delta.get("tool_calls"):
                    tc_data = delta.get("tool_calls", [])
                    tool_calls = [ToolCall.from_dict(tc) for tc in tc_data]
                    content = delta.get("content")  # Usually None when tool_calls present
            except (json_module.JSONDecodeError, KeyError):
                pass  # Not the embedded format, keep original content

        # Normal tool_calls handling
        if not tool_calls:
            if tc_data := message.get("tool_calls"):
                tool_calls = [ToolCall.from_dict(tc) for tc in tc_data]

        usage_data = data.get("usage", {})

        # Extract DeepSeek reasoning_content if present
        reasoning_content = message.get("reasoning_content")

        return cls(
            id=data.get("id", ""),
            model=data.get("model", ""),
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=Usage.from_dict(usage_data),
            reasoning_content=reasoning_content,
        )


@dataclass
class StreamDelta:
    """Streaming response delta"""

    content: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None
    finish_reason: Optional[str] = None
    # DeepSeek reasoning_content for streaming
    reasoning_content: Optional[str] = None
