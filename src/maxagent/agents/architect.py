"""Architect Agent - Requirements analysis and planning"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from maxagent.config import Config
from maxagent.core.agent import Agent, AgentConfig, create_agent
from maxagent.core.prompts import build_architect_prompt
from maxagent.core.instructions import load_instructions
from maxagent.llm import LLMClient
from maxagent.tools import ToolRegistry


# Legacy prompt kept for backward compatibility
ARCHITECT_SYSTEM_PROMPT = """You are a senior software architect. Your role is to:

1. **Analyze Requirements**
   - Understand what the user wants to achieve
   - Identify implicit requirements and edge cases
   - Clarify ambiguities

2. **Explore the Codebase**
   - Use available tools to understand the project structure
   - Identify relevant files and modules
   - Understand existing patterns and conventions

3. **Create Implementation Plans**
   - Break down tasks into manageable steps
   - Identify dependencies between components
   - Consider backward compatibility

4. **Identify Risks**
   - Point out potential issues or conflicts
   - Suggest mitigation strategies
   - Consider performance implications

## Available Tools
- `read_file`: Read file contents
- `list_files`: List files matching a pattern
- `search_code`: Search for code patterns

## Output Format
Always structure your analysis with clear sections:
- Requirements Understanding
- Files Involved
- Implementation Steps
- Potential Risks
- Testing Strategy

Be thorough but concise. Use the tools to gather information before making recommendations.
"""


class ArchitectAgent(Agent):
    """
    Specialized agent for architecture analysis and planning.

    This agent focuses on:
    - Understanding project structure
    - Analyzing requirements
    - Creating implementation plans
    - Identifying risks
    """

    # Tools allowed for architect (read-only operations)
    ALLOWED_TOOLS = ["read_file", "list_files", "search_code", "grep", "glob"]

    def __init__(
        self,
        config: Config,
        agent_config: AgentConfig,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        **kwargs,
    ) -> None:
        super().__init__(
            config=config,
            agent_config=agent_config,
            llm_client=llm_client,
            tool_registry=tool_registry,
            **kwargs,
        )


def create_architect_agent(
    config: Config,
    project_root: Optional[Path] = None,
    llm_client: Optional[LLMClient] = None,
    tool_registry: Optional[ToolRegistry] = None,
    use_new_prompts: bool = True,
) -> ArchitectAgent:
    """Factory function to create an ArchitectAgent

    Args:
        config: Application configuration
        project_root: Project root directory
        llm_client: Optional pre-created LLM client
        tool_registry: Optional pre-created tool registry
        use_new_prompts: Use the new structured prompt system (default True)
    """
    from maxagent.llm import LLMConfig
    from maxagent.tools import create_default_registry

    if llm_client is None:
        llm_config = LLMConfig(
            base_url=config.litellm.base_url,
            api_key=config.litellm.api_key,
            model=config.model.default,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens,
        )
        llm_client = LLMClient(llm_config)

    if tool_registry is None:
        root = project_root or Path.cwd()
        tool_registry = create_default_registry(root)

    root = project_root or Path.cwd()

    # Build system prompt
    if use_new_prompts:
        project_instructions = load_instructions(config.instructions, root)
        system_prompt = build_architect_prompt(
            working_directory=root,
            project_instructions=project_instructions,
        )
    else:
        system_prompt = config.agents.architect.system_prompt or ARCHITECT_SYSTEM_PROMPT

    # Create agent with the system prompt
    agent_config = AgentConfig(
        name="architect",
        system_prompt=system_prompt,
        tools=ArchitectAgent.ALLOWED_TOOLS,
        max_iterations=15,
        temperature=0.3,
    )

    return ArchitectAgent(
        config=config,
        agent_config=agent_config,
        llm_client=llm_client,
        tool_registry=tool_registry,
    )
