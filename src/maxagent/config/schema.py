"""Configuration schema using Pydantic"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class APIProvider(str, Enum):
    """Supported API providers"""

    LITELLM = "litellm"  # LiteLLM proxy
    OPENAI = "openai"  # OpenAI API
    GLM = "glm"  # Zhipu GLM API
    GITHUB_COPILOT = "github_copilot"  # GitHub Copilot
    CUSTOM = "custom"  # Custom OpenAI-compatible API


# Provider default configurations
PROVIDER_DEFAULTS = {
    APIProvider.LITELLM: {
        "base_url": "http://localhost:4000",
        "model": "github_copilot/gpt-4",
    },
    APIProvider.OPENAI: {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4",
    },
    APIProvider.GLM: {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4.6",
    },
    APIProvider.GITHUB_COPILOT: {
        "base_url": "https://api.githubcopilot.com",
        "model": "gpt-4o",
    },
    APIProvider.CUSTOM: {
        "base_url": "",
        "model": "",
    },
}


class LiteLLMConfig(BaseModel):
    """LLM API connection configuration (supports OpenAI-compatible APIs)"""

    provider: APIProvider = Field(
        default=APIProvider.LITELLM,
        description="API provider type",
    )
    base_url: str = Field(
        default="http://localhost:4000",
        description="API base URL",
    )
    api_key: str = Field(
        default="",
        description="API key for authentication",
    )


class ModelConfig(BaseModel):
    """Model configuration"""

    default: str = Field(
        default="glm-4.6",
        description="Default model to use",
    )
    thinking_model: str = Field(
        default="glm-4.6",
        description="Model for deep thinking tasks (固定为 glm-4.6)",
    )
    thinking_strategy: str = Field(
        default="auto",
        description="Thinking strategy: auto (decide by complexity), enabled (always), disabled (never)",
    )
    show_thinking: bool = Field(
        default=True,
        description="Show thinking process in output",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature",
    )
    max_tokens: int = Field(
        default=4096,
        gt=0,
        description="Maximum tokens in response",
    )
    max_iterations: int = Field(
        default=100,
        gt=0,
        le=1000,
        description="Maximum tool call iterations per request",
    )
    # Available models for quick switching
    available_models: list[str] = Field(
        default_factory=lambda: [
            "glm-4.6",
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4.1",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-3.5-turbo",
            "deepseek-chat",
            "deepseek-reasoner",
            # GitHub Copilot models
            "claude-3.5-sonnet",
            "claude-3.7-sonnet",
            "claude-3.7-sonnet-thought",
            "o1",
            "o1-mini",
            "o3-mini",
        ],
        description="List of available models for quick switching",
    )


class ToolsConfig(BaseModel):
    """Tools configuration"""

    enabled: list[str] = Field(
        default_factory=lambda: [
            "read_file",
            "list_files",
            "search_code",
            "write_file",
            "edit",  # Preferred for modifying existing files
            "run_command",
            "grep",
            "glob",
            "git_status",
            "git_diff",
            "git_log",
            "git_branch",
            "webfetch",
            # Long-term memory search
            "search_memory",
            # Todo tools for task management
            "todowrite",
            "todoread",
            "todoclear",
        ],
        description="List of enabled tools",
    )
    disabled: list[str] = Field(
        default_factory=list,
        description="List of disabled tools",
    )


class SecurityConfig(BaseModel):
    """Security configuration"""

    ignore_patterns: list[str] = Field(
        default_factory=lambda: [
            ".env",
            ".env.*",
            "*.pem",
            "*.key",
            "*.p12",
            "**/secrets/**",
        ],
        description="File patterns to ignore for security",
    )
    require_confirmation: list[str] = Field(
        default_factory=lambda: [
            "write_file",
            "run_command",
        ],
        description="Tools that require user confirmation",
    )


class InstructionsConfig(BaseModel):
    """Instructions/Rules configuration (like AGENTS.md or CLAUDE.md)"""

    filename: str = Field(
        default="MAXAGENT.md",
        description="Primary instruction file name",
    )
    alternative_names: list[str] = Field(
        default_factory=lambda: [
            "AGENTS.md",
            "CLAUDE.md",
            ".maxagent.md",
        ],
        description="Alternative instruction file names to search",
    )
    global_file: str = Field(
        default="~/.config/maxagent/MAXAGENT.md",
        description="Global instruction file path",
    )
    additional_files: list[str] = Field(
        default_factory=list,
        description="Additional instruction files to include (supports glob)",
    )
    auto_discover: bool = Field(
        default=True,
        description="Auto-discover instruction files in parent directories",
    )


class AgentPromptConfig(BaseModel):
    """Agent prompt configuration"""

    system_prompt: str = Field(
        default="",
        description="System prompt for the agent",
    )


class AgentsConfig(BaseModel):
    """All agents configuration"""

    default: AgentPromptConfig = Field(
        default_factory=lambda: AgentPromptConfig(
            system_prompt="""You are MaxAgent, an AI code assistant. You help developers with:
- Understanding and explaining code
- Writing and modifying code
- Debugging and fixing issues
- Answering programming questions

You have access to tools that can read files, list files, and search code.
Use these tools to understand the codebase before providing assistance.
Always provide clear, concise, and accurate responses."""
        ),
        description="Default agent configuration",
    )

    architect: AgentPromptConfig = Field(
        default_factory=lambda: AgentPromptConfig(
            system_prompt="""You are an Architect Agent. Your responsibilities:
1. Analyze user requirements
2. Understand project structure
3. Design implementation plans
4. Identify potential risks

Use available tools to understand the project, then provide detailed analysis and recommendations."""
        ),
        description="Architect agent configuration",
    )

    coder: AgentPromptConfig = Field(
        default_factory=lambda: AgentPromptConfig(
            system_prompt="""You are a Coder Agent. Your responsibilities:
1. Generate high-quality code based on requirements
2. Create unified diff patches for modifications
3. Follow project coding conventions
4. Add necessary comments

Ensure code is clean, maintainable, and follows best practices."""
        ),
        description="Coder agent configuration",
    )

    tester: AgentPromptConfig = Field(
        default_factory=lambda: AgentPromptConfig(
            system_prompt="""You are a Tester Agent. Your responsibilities:
1. Generate tests for code changes
2. Analyze test results
3. Provide fix suggestions

Create comprehensive test cases covering normal and edge cases."""
        ),
        description="Tester agent configuration",
    )


class Config(BaseModel):
    """Main application configuration"""

    litellm: LiteLLMConfig = Field(
        default_factory=LiteLLMConfig,
        description="LiteLLM configuration",
    )
    model: ModelConfig = Field(
        default_factory=ModelConfig,
        description="Model configuration",
    )
    tools: ToolsConfig = Field(
        default_factory=ToolsConfig,
        description="Tools configuration",
    )
    security: SecurityConfig = Field(
        default_factory=SecurityConfig,
        description="Security configuration",
    )
    instructions: InstructionsConfig = Field(
        default_factory=InstructionsConfig,
        description="Instructions/Rules configuration",
    )
    agents: AgentsConfig = Field(
        default_factory=AgentsConfig,
        description="Agents configuration",
    )

    class Config:
        """Pydantic config"""

        extra = "ignore"  # Ignore unknown fields
