"""LLM client module"""

from .client import LLMClient, LLMConfig
from .copilot_client import CopilotLLMClient, CopilotLLMConfig, create_copilot_client
from .models import ChatResponse, Message, StreamDelta, ToolCall, ToolCallFunction, Usage

__all__ = [
    "LLMClient",
    "LLMConfig",
    "CopilotLLMClient",
    "CopilotLLMConfig",
    "create_copilot_client",
    "Message",
    "ChatResponse",
    "StreamDelta",
    "ToolCall",
    "ToolCallFunction",
    "Usage",
]


# Thinking model mapping for different providers
THINKING_MODELS = {
    # GLM thinking models
    "glm-z1-flash": {
        "provider": "glm",
        "format": "tags",  # Uses <think>...</think> tags
    },
    "glm-z1-air": {
        "provider": "glm",
        "format": "tags",
    },
    "glm-4.6": {
        "provider": "glm",
        "format": "tags",  # GLM-4.6 also supports thinking with <think> tags
    },
    # DeepSeek thinking models
    "deepseek-reasoner": {
        "provider": "deepseek",
        "format": "field",  # Uses reasoning_content field
    },
    "deepseek-r1": {
        "provider": "deepseek",
        "format": "field",
    },
}


def is_thinking_model(model: str) -> bool:
    """Check if a model is a thinking/reasoning model"""
    return model in THINKING_MODELS


def get_thinking_format(model: str) -> str:
    """Get the thinking format for a model ('tags' or 'field')"""
    if model in THINKING_MODELS:
        return THINKING_MODELS[model]["format"]
    return "none"
