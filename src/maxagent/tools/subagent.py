"""SubAgent tool for spawning specialized agents during conversation"""

from __future__ import annotations

import asyncio
from typing import Any, Optional, TYPE_CHECKING

from .base import BaseTool, ToolParameter, ToolResult

if TYPE_CHECKING:
    from pathlib import Path
    from maxagent.config import Config
    from maxagent.llm import LLMClient
    from maxagent.tools import ToolRegistry


class SubAgentTool(BaseTool):
    """Launch specialized sub-agents for complex, multi-step tasks

    This tool allows the main agent to delegate tasks to specialized agents:
    - explore: Fast agent for codebase exploration and searches
    - architect: Agent for analyzing requirements and designing solutions
    - coder: Agent for generating and modifying code
    - tester: Agent for generating and analyzing tests
    - general: General-purpose agent for research and multi-step tasks

    Use this when:
    - A task requires specialized expertise
    - You need to perform parallel independent searches
    - The task is complex and would benefit from focused analysis
    """

    name = "subagent"
    description = """Launch a specialized sub-agent to handle complex tasks autonomously.

Available agent types:
- explore: Fast agent for codebase exploration (finding files, searching code, answering questions about the codebase)
- architect: Analyzes requirements and creates implementation plans
- coder: Generates and modifies code based on specifications
- tester: Creates tests and analyzes test results
- general: General-purpose agent for research and multi-step tasks

The sub-agent will execute the task and return a single result. Use this for:
- Complex multi-step tasks that require focused attention
- Codebase exploration and research
- Code generation or modification tasks
- Test generation tasks

The sub-agent has access to the same tools as the main agent."""

    parameters = [
        ToolParameter(
            name="agent_type",
            type="string",
            description="Type of specialized agent to use",
            enum=["explore", "architect", "coder", "tester", "general"],
        ),
        ToolParameter(
            name="task",
            type="string",
            description="Detailed task description for the sub-agent to perform",
        ),
        ToolParameter(
            name="context",
            type="string",
            description="Additional context or background information for the task",
            required=False,
            default="",
        ),
    ]
    risk_level = "medium"

    def __init__(
        self,
        project_root: "Path",
        config: "Config",
        llm_client: Optional["LLMClient"] = None,
        tool_registry: Optional["ToolRegistry"] = None,
        max_iterations: int = 50,
    ) -> None:
        """Initialize the SubAgent tool

        Args:
            project_root: Project root directory
            config: Application configuration
            llm_client: Optional LLM client to share
            tool_registry: Optional tool registry to share
            max_iterations: Max iterations for sub-agent (default 50)
        """
        self.project_root = project_root
        self.config = config
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute a task using a specialized sub-agent

        Args:
            agent_type: Type of agent (explore, architect, coder, tester, general)
            task: Task description
            context: Additional context

        Returns:
            ToolResult with the sub-agent's response
        """
        agent_type = kwargs.get("agent_type", "general")
        task = kwargs.get("task", "")
        context = kwargs.get("context", "")

        if not task:
            return ToolResult(
                success=False,
                output="",
                error="Task description is required",
            )

        try:
            # Import here to avoid circular imports
            from maxagent.core.agent import Agent, AgentConfig, create_agent
            from maxagent.llm import LLMClient, create_llm_client
            from maxagent.tools import create_default_registry

            # Build the full task with context
            full_task = task
            if context:
                full_task = f"""## Context
{context}

## Task
{task}"""

            # Create LLM client if not provided
            llm_client = self.llm_client
            if llm_client is None:
                llm_client = create_llm_client(self.config)

            # Create tool registry if not provided
            tool_registry = self.tool_registry
            if tool_registry is None:
                tool_registry = create_default_registry(self.project_root)

            # Create the appropriate agent based on type
            if agent_type == "explore":
                # Explorer agent - optimized for fast codebase searches
                agent_config = AgentConfig(
                    name="explore",
                    system_prompt=self._get_explore_prompt(),
                    tools=["read_file", "list_files", "search_code", "grep", "glob"],
                    max_iterations=self.max_iterations,
                    temperature=0.3,
                )
                agent = Agent(
                    config=self.config,
                    agent_config=agent_config,
                    llm_client=llm_client,
                    tool_registry=tool_registry,
                )

            elif agent_type == "architect":
                agent_config = AgentConfig(
                    name="architect",
                    system_prompt=self._get_architect_prompt(),
                    tools=["read_file", "list_files", "search_code", "grep", "glob"],
                    max_iterations=self.max_iterations,
                    temperature=0.3,
                )
                agent = Agent(
                    config=self.config,
                    agent_config=agent_config,
                    llm_client=llm_client,
                    tool_registry=tool_registry,
                )

            elif agent_type == "coder":
                agent_config = AgentConfig(
                    name="coder",
                    system_prompt=self._get_coder_prompt(),
                    tools=["read_file", "list_files", "search_code", "write_file", "grep", "glob"],
                    max_iterations=self.max_iterations,
                    temperature=0.2,
                )
                agent = Agent(
                    config=self.config,
                    agent_config=agent_config,
                    llm_client=llm_client,
                    tool_registry=tool_registry,
                )

            elif agent_type == "tester":
                agent_config = AgentConfig(
                    name="tester",
                    system_prompt=self._get_tester_prompt(),
                    tools=["read_file", "list_files", "search_code", "run_command", "grep", "glob"],
                    max_iterations=self.max_iterations,
                    temperature=0.2,
                )
                agent = Agent(
                    config=self.config,
                    agent_config=agent_config,
                    llm_client=llm_client,
                    tool_registry=tool_registry,
                )

            else:  # general
                agent_config = AgentConfig(
                    name="general",
                    system_prompt=self._get_general_prompt(),
                    tools=[],  # Empty means all tools
                    max_iterations=self.max_iterations,
                    temperature=0.5,
                )
                agent = Agent(
                    config=self.config,
                    agent_config=agent_config,
                    llm_client=llm_client,
                    tool_registry=tool_registry,
                )

            # Execute the task
            result = await agent.run(full_task)

            return ToolResult(
                success=True,
                output=result,
                metadata={
                    "agent_type": agent_type,
                    "task": task[:100] + "..." if len(task) > 100 else task,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"SubAgent execution failed: {str(e)}",
                metadata={"agent_type": agent_type},
            )

    def _get_explore_prompt(self) -> str:
        """Get specialized prompt for exploration agent"""
        return """You are an Exploration Agent specialized in quickly finding information in codebases.

Your strengths:
- Fast file pattern matching using glob patterns
- Efficient code searching using grep/ripgrep
- Understanding codebase structure
- Locating specific functions, classes, or patterns

Instructions:
1. Use glob to find files by name patterns (e.g., "**/*.py", "src/**/*.ts")
2. Use grep to search for code patterns (e.g., function names, imports)
3. Use read_file to examine specific files when needed
4. Provide concise, focused answers

Be thorough but efficient. Return only the relevant information requested."""

    def _get_architect_prompt(self) -> str:
        """Get specialized prompt for architect agent"""
        return """You are a Senior Software Architect Agent.

Your responsibilities:
1. Analyze requirements and understand what needs to be done
2. Explore the codebase to understand the project structure
3. Identify relevant files and modules
4. Create detailed implementation plans
5. Identify potential risks and suggest mitigations

Use the available tools to:
- Read existing code to understand patterns
- Search for related functionality
- List files to understand project structure

Output Format:
- Requirements Understanding
- Files Involved
- Implementation Steps
- Potential Risks
- Testing Strategy

Be thorough but concise. Use tools to gather information before making recommendations."""

    def _get_coder_prompt(self) -> str:
        """Get specialized prompt for coder agent"""
        return """You are an Expert Software Engineer Agent.

Your responsibilities:
1. Write high-quality, clean, maintainable code
2. Follow project coding conventions and patterns
3. Generate code changes in unified diff format when modifying existing files
4. Handle edge cases and error scenarios

Guidelines:
1. Read the relevant files FIRST before making changes
2. Understand existing code structure and style
3. Make minimal, focused changes
4. Add helpful comments for complex logic
5. Follow project conventions

Output code changes as unified diff patches when modifying existing files:
```diff
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -10,6 +10,8 @@
 existing line
+new line
 existing line
```"""

    def _get_tester_prompt(self) -> str:
        """Get specialized prompt for tester agent"""
        return """You are an Expert Test Engineer Agent.

Your responsibilities:
1. Generate comprehensive test cases
2. Cover normal paths, edge cases, and error scenarios
3. Follow project testing conventions
4. Use the project's testing framework

Guidelines:
1. Read existing tests FIRST to understand conventions
2. Match the testing framework and style used in the project
3. Create focused, single-purpose tests
4. Include docstrings explaining what each test verifies
5. Test both success and failure scenarios

Generate tests as complete, runnable code that can be directly added to test files."""

    def _get_general_prompt(self) -> str:
        """Get specialized prompt for general agent"""
        return """You are a General-Purpose Research Agent.

Your responsibilities:
1. Research and gather information
2. Analyze complex problems
3. Execute multi-step tasks autonomously
4. Provide comprehensive answers

You have access to all available tools. Use them efficiently to:
- Search and explore the codebase
- Read and analyze files
- Execute commands when needed
- Fetch web content for research

Be thorough and systematic in your approach. Return a comprehensive result when done."""


class TaskTool(BaseTool):
    """Alias for SubAgent tool with task-oriented interface

    This provides a simpler interface focused on launching autonomous tasks.
    """

    name = "task"
    description = """Launch an autonomous agent to handle a complex task.

This tool spawns a specialized agent that will:
1. Analyze the task requirements
2. Use available tools to gather information
3. Execute the necessary steps
4. Return a comprehensive result

Best used for:
- Multi-step research tasks
- Code exploration and analysis
- Complex file operations
- Tasks requiring multiple tool calls

The agent works autonomously and returns when complete."""

    parameters = [
        ToolParameter(
            name="description",
            type="string",
            description="Short (3-5 words) description of the task",
        ),
        ToolParameter(
            name="prompt",
            type="string",
            description="Detailed task instructions for the agent",
        ),
        ToolParameter(
            name="agent_type",
            type="string",
            description="Type of agent: explore (fast searches), general (research), coder (code changes)",
            required=False,
            default="general",
            enum=["explore", "general", "coder", "architect", "tester"],
        ),
    ]
    risk_level = "medium"

    def __init__(
        self,
        project_root: "Path",
        config: "Config",
        llm_client: Optional["LLMClient"] = None,
        tool_registry: Optional["ToolRegistry"] = None,
        max_iterations: int = 50,
    ) -> None:
        self.subagent = SubAgentTool(
            project_root=project_root,
            config=config,
            llm_client=llm_client,
            tool_registry=tool_registry,
            max_iterations=max_iterations,
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute an autonomous task

        Args:
            description: Short task description
            prompt: Detailed task instructions
            agent_type: Type of agent to use

        Returns:
            ToolResult with the task output
        """
        description = kwargs.get("description", "")
        prompt = kwargs.get("prompt", "")
        agent_type = kwargs.get("agent_type", "general")

        return await self.subagent.execute(
            agent_type=agent_type,
            task=prompt,
            context=f"Task: {description}",
        )
