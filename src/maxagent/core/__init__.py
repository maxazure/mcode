"""Core module - Agent and Orchestrator"""

from .agent import Agent, AgentConfig, create_agent
from .orchestrator import Orchestrator, OrchestratorConfig, TaskResult, create_orchestrator
from .instructions import (
    InstructionsLoader,
    InstructionSource,
    load_instructions,
    find_instruction_file,
)
from .thinking_strategy import (
    ThinkingStrategy,
    ThinkingSelector,
    create_thinking_selector,
    get_default_thinking_model,
)
from .prompts import (
    SystemPromptBuilder,
    build_default_system_prompt,
    build_architect_prompt,
    build_coder_prompt,
    build_tester_prompt,
    build_environment_context,
    build_tool_descriptions,
    IDENTITY_PROMPT,
    TONE_AND_STYLE,
    TOOL_USAGE_POLICY,
    CODE_QUALITY,
    TASK_MANAGEMENT,
    RESPONSE_FORMAT,
    GIT_OPERATIONS,
)

__all__ = [
    "Agent",
    "AgentConfig",
    "create_agent",
    "Orchestrator",
    "OrchestratorConfig",
    "TaskResult",
    "create_orchestrator",
    # Instructions
    "InstructionsLoader",
    "InstructionSource",
    "load_instructions",
    "find_instruction_file",
    # Thinking strategy
    "ThinkingStrategy",
    "ThinkingSelector",
    "create_thinking_selector",
    "get_default_thinking_model",
    # Prompts
    "SystemPromptBuilder",
    "build_default_system_prompt",
    "build_architect_prompt",
    "build_coder_prompt",
    "build_tester_prompt",
    "build_environment_context",
    "build_tool_descriptions",
    "IDENTITY_PROMPT",
    "TONE_AND_STYLE",
    "TOOL_USAGE_POLICY",
    "CODE_QUALITY",
    "TASK_MANAGEMENT",
    "RESPONSE_FORMAT",
    "GIT_OPERATIONS",
]
