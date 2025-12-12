"""Coder Agent - Code generation and modification"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from maxagent.config import Config
from maxagent.core.agent import Agent, AgentConfig
from maxagent.core.prompts import build_coder_prompt
from maxagent.core.instructions import load_instructions
from maxagent.llm import LLMClient
from maxagent.tools import ToolRegistry


# Legacy prompt kept for backward compatibility
CODER_SYSTEM_PROMPT = """You are an expert software engineer. Your role is to:

1. **Write High-Quality Code**
   - Follow best practices and design patterns
   - Write clean, readable, and maintainable code
   - Include appropriate comments and documentation

2. **Generate Patches**
   - Output changes in unified diff format
   - Make minimal, focused changes
   - Preserve existing code style and conventions

3. **Handle Edge Cases**
   - Consider error handling
   - Validate inputs appropriately
   - Handle boundary conditions

## Available Tools
- `read_file`: Read file contents to understand existing code
- `list_files`: Find relevant files in the project
- `search_code`: Search for patterns, imports, or references
- `write_file`: Write or overwrite files (use with caution)

## Diff Format
Always output code changes as unified diff patches:

```diff
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -10,6 +10,8 @@
 existing line
 another existing line
+new line to add
+another new line
 more existing code
```

## Guidelines
1. Read the relevant files FIRST before making changes
2. Understand the existing code structure and style
3. Make minimal changes to achieve the goal
4. Preserve imports, formatting, and conventions
5. Add helpful comments for complex logic
6. Consider backward compatibility
"""


class CoderAgent(Agent):
    """
    Specialized agent for code generation and modification.

    This agent focuses on:
    - Reading and understanding existing code
    - Generating new code following best practices
    - Creating patches in unified diff format
    - Maintaining code style consistency
    """

    # Tools allowed for coder (includes write operations)
    ALLOWED_TOOLS = ["read_file", "list_files", "search_code", "write_file", "grep", "glob"]

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


def create_coder_agent(
    config: Config,
    project_root: Optional[Path] = None,
    llm_client: Optional[LLMClient] = None,
    tool_registry: Optional[ToolRegistry] = None,
    use_new_prompts: bool = True,
) -> CoderAgent:
    """Factory function to create a CoderAgent

    Args:
        config: Application configuration
        project_root: Project root directory
        llm_client: Optional pre-created LLM client
        tool_registry: Optional pre-created tool registry
        use_new_prompts: Use the new structured prompt system (default True)
    """
    from maxagent.tools import create_default_registry

    if llm_client is None:
        from maxagent.llm import create_llm_client

        llm_client = create_llm_client(config)

    if tool_registry is None:
        root = project_root or Path.cwd()
        tool_registry = create_default_registry(root)

    root = project_root or Path.cwd()

    # Build system prompt
    if use_new_prompts:
        project_instructions = load_instructions(config.instructions, root)
        system_prompt = build_coder_prompt(
            working_directory=root,
            project_instructions=project_instructions,
        )
    else:
        system_prompt = config.agents.coder.system_prompt or CODER_SYSTEM_PROMPT

    # Create agent with the system prompt
    agent_config = AgentConfig(
        name="coder",
        system_prompt=system_prompt,
        tools=CoderAgent.ALLOWED_TOOLS,
        max_iterations=20,
        temperature=0.2,
    )

    return CoderAgent(
        config=config,
        agent_config=agent_config,
        llm_client=llm_client,
        tool_registry=tool_registry,
    )
