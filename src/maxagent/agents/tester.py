"""Tester Agent - Test generation and analysis"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from maxagent.config import Config
from maxagent.core.agent import Agent, AgentConfig
from maxagent.core.prompts import build_tester_prompt
from maxagent.core.instructions import load_instructions
from maxagent.llm import LLMClient
from maxagent.tools import ToolRegistry


# Legacy prompt kept for backward compatibility
TESTER_SYSTEM_PROMPT = """You are an expert software test engineer. Your role is to:

1. **Generate Comprehensive Tests**
   - Write unit tests for individual functions/methods
   - Write integration tests for component interactions
   - Cover edge cases and boundary conditions

2. **Detect Testing Framework**
   - Identify the project's testing framework (pytest, unittest, jest, etc.)
   - Follow existing test patterns and conventions
   - Use appropriate assertions and fixtures

3. **Ensure Test Quality**
   - Tests should be independent and repeatable
   - Tests should be fast and focused
   - Tests should have clear assertions
   - Tests should have descriptive names

## Available Tools
- `read_file`: Read existing tests and code
- `list_files`: Find test files and source files
- `search_code`: Search for test patterns and fixtures
- `run_command`: Run tests (when available)

## Test Format
Generate tests as complete, runnable code:

```python
import pytest
from module import function_to_test

class TestFunctionName:
    def test_normal_case(self):
        '''Test normal/happy path'''
        result = function_to_test(valid_input)
        assert result == expected_output
    
    def test_edge_case(self):
        '''Test boundary condition'''
        result = function_to_test(edge_input)
        assert result == expected_edge_output
    
    def test_error_handling(self):
        '''Test error scenarios'''
        with pytest.raises(ExpectedException):
            function_to_test(invalid_input)
```

## Guidelines
1. Read existing tests FIRST to understand conventions
2. Match the testing framework and style
3. Create focused, single-purpose tests
4. Include docstrings explaining what each test verifies
5. Use fixtures for common setup when appropriate
6. Test both success and failure scenarios
"""


class TesterAgent(Agent):
    """
    Specialized agent for test generation and analysis.

    This agent focuses on:
    - Analyzing code to identify test scenarios
    - Generating comprehensive test suites
    - Following project testing conventions
    - Creating both unit and integration tests
    """

    # Tools allowed for tester
    ALLOWED_TOOLS = ["read_file", "list_files", "search_code", "run_command", "grep", "glob"]

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


def create_tester_agent(
    config: Config,
    project_root: Optional[Path] = None,
    llm_client: Optional[LLMClient] = None,
    tool_registry: Optional[ToolRegistry] = None,
    use_new_prompts: bool = True,
) -> TesterAgent:
    """Factory function to create a TesterAgent

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
        system_prompt = build_tester_prompt(
            working_directory=root,
            project_instructions=project_instructions,
        )
    else:
        system_prompt = config.agents.tester.system_prompt or TESTER_SYSTEM_PROMPT

    # Create agent with the system prompt
    agent_config = AgentConfig(
        name="tester",
        system_prompt=system_prompt,
        tools=TesterAgent.ALLOWED_TOOLS,
        max_iterations=15,
        temperature=0.2,
    )

    return TesterAgent(
        config=config,
        agent_config=agent_config,
        llm_client=llm_client,
        tool_registry=tool_registry,
    )
