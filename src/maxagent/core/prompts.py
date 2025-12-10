"""System prompts for MaxAgent

This module provides structured system prompts for the code agent,
following best practices from Claude Code, OpenCode, and Aider.

Design principles:
1. Markdown for human-readable headers (# ## ###)
2. XML tags for structured content (<example>, <env>, <instructions>)
3. Clear hierarchical structure (Identity -> Instructions -> Tools -> Context)
4. Dynamic context injection (time, working directory, platform)
"""

from __future__ import annotations

import os
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..tools.registry import ToolRegistry


# =============================================================================
# Core Identity Prompt
# =============================================================================

IDENTITY_PROMPT = """You are MaxAgent, an expert AI coding assistant for the command line.

You help developers with:
- Understanding, explaining, and navigating codebases
- Writing high-quality, maintainable code
- Debugging issues and fixing bugs
- Refactoring and improving existing code
- Answering programming questions with accuracy"""


# =============================================================================
# Tone and Style Guidelines
# =============================================================================

TONE_AND_STYLE = """# Tone and Style

- Your output will be displayed on a command line interface with monospace font
- Keep responses concise and focused - avoid unnecessary verbosity
- Use Github-flavored Markdown for formatting (code blocks, lists, headers)
- Do NOT use emojis unless the user explicitly requests them
- Communicate directly - avoid excessive pleasantries or filler phrases

# Professional Objectivity

- Prioritize technical accuracy over validating user beliefs
- Provide direct, objective technical information
- Respectfully disagree when the user's approach has issues
- When uncertain, investigate rather than confirming assumptions"""


# =============================================================================
# Tool Usage Guidelines
# =============================================================================

TOOL_USAGE_POLICY = """# Tool Usage Policy

## General Principles
- Use specialized tools instead of bash commands when possible:
  - Use `read_file` instead of `cat`, `head`, `tail`
  - Use `list_files` instead of `ls`
  - Use `grep` tool instead of `grep` command
  - Use `glob` tool instead of `find` command
- NEVER use bash `echo` or similar commands to communicate - write responses directly
- Reserve bash/command tools exclusively for actual system operations

## File Operations
- Always READ a file before attempting to edit it
- Prefer editing existing files over creating new ones
- NEVER proactively create documentation files unless explicitly requested
- When referencing code, include file path and line number: `src/app.py:42`

## Path Restrictions (IMPORTANT)
- All file paths must be RELATIVE to the project root (current working directory)
- You CANNOT write files outside the project directory
- Do NOT use absolute paths like `/Users/...` or `~/...`
- Do NOT use `..` to traverse outside the project
- If user asks to create files outside the project, inform them of this limitation
- Example valid paths: `src/app.py`, `tests/test_main.py`, `README.md`
- Example INVALID paths: `~/myfile.py`, `/tmp/file.txt`, `../other/file.py`

## Search Operations
- For exploring unfamiliar codebases, use tools systematically:
  1. First use `list_files` to understand project structure
  2. Use `glob` to find files by pattern (e.g., "**/*.py")
  3. Use `grep` to search for specific code patterns
  4. Use `read_file` to examine relevant files

## Command Execution
- Avoid running destructive commands without user confirmation
- For long-running commands, consider timeout implications
- When running tests or builds, handle potential failures gracefully"""


# =============================================================================
# Code Quality Guidelines
# =============================================================================

CODE_QUALITY = """# Code Quality Guidelines

## When Writing Code
- Follow best practices and established design patterns
- Match the existing code style and conventions of the project
- Write clean, readable, and maintainable code
- Include meaningful comments for complex logic
- Handle errors appropriately
- Consider edge cases and boundary conditions

## When Generating Patches
- Output changes in unified diff format when appropriate
- Make minimal, focused changes
- Preserve existing imports, formatting, and conventions
- Avoid unnecessary modifications

## Code Review Mindset
- Think about potential issues before implementing
- Consider security implications
- Evaluate performance characteristics
- Check for backward compatibility"""


# =============================================================================
# Task Management
# =============================================================================

TASK_MANAGEMENT = """# Task Management

For complex multi-step tasks:
1. Break down the task into manageable steps
2. Work through each step methodically
3. Verify each step before moving on
4. If a step fails, analyze and adjust approach

When exploring code or requirements:
- Gather context first before making recommendations
- Read relevant files to understand existing patterns
- Consider dependencies and impacts of changes

## Handling Ambiguity
- If the request is unclear, ask clarifying questions
- If multiple approaches are possible, explain trade-offs
- When in doubt about destructive operations, confirm with user"""


# =============================================================================
# Git Operations Guidelines
# =============================================================================

GIT_OPERATIONS = """# Git Operations

## Committing Changes
When asked to create a git commit:
1. First run `git status` to see what files are changed
2. Run `git diff` to see the actual changes
3. Review recent commits with `git log --oneline -5` to match commit style
4. Create a clear, concise commit message focusing on "why" not "what"

## Commit Message Format
- Use imperative mood: "Add feature" not "Added feature"
- Keep first line under 72 characters
- Types: feat, fix, docs, refactor, test, chore, style, perf
- Example: `feat: add user authentication endpoint`

## Pull Requests
When creating a PR:
1. Understand all changes since branching from main
2. Write a summary focusing on the purpose, not just listing changes
3. Include testing notes if applicable"""


# =============================================================================
# Response Format Guidelines
# =============================================================================

RESPONSE_FORMAT = """# Response Format

## Code References
When referencing specific code, include file path and line number:
```
The function is defined at src/utils/helper.py:156
```

## Code Blocks
Always specify the language for syntax highlighting:
```python
def example():
    return "hello"
```

## Diff Output
Use unified diff format for code changes:
```diff
--- a/src/file.py
+++ b/src/file.py
@@ -10,3 +10,4 @@
 existing line
+new line
```"""


# =============================================================================
# Environment Context Builder
# =============================================================================


def build_environment_context(
    working_directory: Optional[Path] = None,
    include_time: bool = True,
    include_git_status: bool = True,
) -> str:
    """Build the environment context block.

    Args:
        working_directory: Current working directory (defaults to cwd)
        include_time: Whether to include current date/time
        include_git_status: Whether to check git repository status

    Returns:
        Formatted environment context string
    """
    cwd = working_directory or Path.cwd()

    # Check if directory is a git repo
    is_git_repo = (cwd / ".git").exists()

    # Get platform info
    os_platform = platform.system().lower()
    if os_platform == "darwin":
        os_platform = "darwin (macOS)"

    lines = [
        "<env>",
        f"  Working directory: {cwd}",
        f"  Is directory a git repo: {'yes' if is_git_repo else 'no'}",
        f"  Platform: {os_platform}",
    ]

    if include_time:
        now = datetime.now()
        lines.append(f"  Today's date: {now.strftime('%a %b %d %Y')}")

    lines.append("</env>")

    return "\n".join(lines)


# =============================================================================
# Tool Description Builder
# =============================================================================


def build_tool_descriptions(
    registry: ToolRegistry,
    tool_names: Optional[list[str]] = None,
) -> str:
    """Build tool descriptions section.

    Args:
        registry: Tool registry containing available tools
        tool_names: Optional list of tools to include (None = all)

    Returns:
        Formatted tool descriptions
    """
    if tool_names:
        tools = [t for name in tool_names if (t := registry.get(name)) is not None]
    else:
        tools = registry.get_all_tools()

    if not tools:
        return ""

    lines = ["# Available Tools\n"]

    for tool in tools:
        lines.append(f"## {tool.name}")
        lines.append(f"{tool.description}")

        # Add parameter info from ToolParameter list
        if tool.parameters:
            lines.append("\nParameters:")
            for param in tool.parameters:
                req_marker = " (required)" if param.required else " (optional)"
                lines.append(f"- `{param.name}`{req_marker}: {param.description}")

        lines.append("")  # Empty line between tools

    return "\n".join(lines)


# =============================================================================
# System Prompt Builder
# =============================================================================


class SystemPromptBuilder:
    """Builder class for constructing system prompts.

    Follows the structure:
    1. Identity - Who the agent is
    2. Tone/Style - How to communicate
    3. Core Instructions - What rules to follow
    4. Tool Policy - How to use tools
    5. Environment Context - Current runtime info
    6. Project Instructions - User/project specific rules
    """

    def __init__(self) -> None:
        self._sections: list[str] = []

    def add_identity(self, identity: str = IDENTITY_PROMPT) -> "SystemPromptBuilder":
        """Add identity section."""
        self._sections.append(identity)
        return self

    def add_tone_and_style(self, tone: str = TONE_AND_STYLE) -> "SystemPromptBuilder":
        """Add tone and style guidelines."""
        self._sections.append(tone)
        return self

    def add_tool_usage_policy(self, policy: str = TOOL_USAGE_POLICY) -> "SystemPromptBuilder":
        """Add tool usage policy."""
        self._sections.append(policy)
        return self

    def add_code_quality(self, quality: str = CODE_QUALITY) -> "SystemPromptBuilder":
        """Add code quality guidelines."""
        self._sections.append(quality)
        return self

    def add_task_management(self, management: str = TASK_MANAGEMENT) -> "SystemPromptBuilder":
        """Add task management guidelines."""
        self._sections.append(management)
        return self

    def add_response_format(self, format_guide: str = RESPONSE_FORMAT) -> "SystemPromptBuilder":
        """Add response format guidelines."""
        self._sections.append(format_guide)
        return self

    def add_git_operations(self, git_ops: str = GIT_OPERATIONS) -> "SystemPromptBuilder":
        """Add git operations guidelines."""
        self._sections.append(git_ops)
        return self

    def add_environment_context(
        self,
        working_directory: Optional[Path] = None,
        include_time: bool = True,
    ) -> "SystemPromptBuilder":
        """Add environment context."""
        context = build_environment_context(
            working_directory=working_directory,
            include_time=include_time,
        )
        self._sections.append(context)
        return self

    def add_tool_descriptions(
        self,
        registry: ToolRegistry,
        tool_names: Optional[list[str]] = None,
    ) -> "SystemPromptBuilder":
        """Add tool descriptions."""
        descriptions = build_tool_descriptions(registry, tool_names)
        if descriptions:
            self._sections.append(descriptions)
        return self

    def add_project_instructions(self, instructions: str) -> "SystemPromptBuilder":
        """Add project-specific instructions from MAXAGENT.md etc."""
        if instructions and instructions.strip():
            self._sections.append(instructions)
        return self

    def add_custom_section(self, content: str) -> "SystemPromptBuilder":
        """Add a custom section."""
        if content and content.strip():
            self._sections.append(content)
        return self

    def build(self) -> str:
        """Build the complete system prompt."""
        return "\n\n".join(self._sections)


# =============================================================================
# Convenience Functions
# =============================================================================


def build_default_system_prompt(
    working_directory: Optional[Path] = None,
    project_instructions: Optional[str] = None,
    tool_registry: Optional[ToolRegistry] = None,
    include_tool_descriptions: bool = False,
    include_git_operations: bool = True,
) -> str:
    """Build a complete default system prompt.

    Args:
        working_directory: Current working directory
        project_instructions: Optional project-specific instructions
        tool_registry: Optional tool registry for tool descriptions
        include_tool_descriptions: Whether to include detailed tool descriptions
        include_git_operations: Whether to include git operations guidelines

    Returns:
        Complete system prompt string
    """
    builder = SystemPromptBuilder()

    # Add core sections
    builder.add_identity()
    builder.add_tone_and_style()
    builder.add_tool_usage_policy()
    builder.add_code_quality()
    builder.add_task_management()
    builder.add_response_format()

    # Add git operations if needed
    if include_git_operations:
        builder.add_git_operations()

    # Add tool descriptions if requested
    if include_tool_descriptions and tool_registry:
        builder.add_tool_descriptions(tool_registry)

    # Add environment context
    builder.add_environment_context(working_directory)

    # Add project instructions if provided
    if project_instructions:
        builder.add_project_instructions(project_instructions)

    return builder.build()


def build_architect_prompt(
    working_directory: Optional[Path] = None,
    project_instructions: Optional[str] = None,
) -> str:
    """Build system prompt for architect agent.

    The architect agent specializes in:
    - Analyzing requirements and understanding user intent
    - Exploring and understanding codebase structure
    - Creating implementation plans and task breakdowns
    - Identifying risks and dependencies
    """
    architect_identity = """You are an expert software architect agent.

Your role is to:
1. **Analyze Requirements** - Understand what the user wants to achieve, identify implicit requirements
2. **Explore Codebase** - Use tools to understand project structure, existing patterns, and conventions
3. **Create Implementation Plans** - Break down tasks, identify file changes needed, order of operations
4. **Identify Risks** - Point out potential issues, conflicts, or considerations

You have access to read-only tools: read_file, list_files, search_code, grep, glob.
You should NOT modify any files - only analyze and plan."""

    architect_instructions = """# Architect Agent Guidelines

## Analysis Process
1. First understand the full scope of the request
2. Explore relevant parts of the codebase
3. Identify all files that need modification
4. Consider dependencies and order of changes
5. Note any potential risks or breaking changes

## Output Format
Structure your analysis with clear sections:
- **Requirements Understanding**: What needs to be done
- **Files Involved**: Which files need changes
- **Implementation Steps**: Ordered list of changes
- **Risks/Considerations**: Potential issues to watch for
- **Testing Strategy**: How to verify the changes work

Be thorough but concise. Use tools to gather information before making recommendations."""

    builder = SystemPromptBuilder()
    builder.add_identity(architect_identity)
    builder.add_tone_and_style()
    builder.add_custom_section(architect_instructions)
    builder.add_environment_context(working_directory)

    if project_instructions:
        builder.add_project_instructions(project_instructions)

    return builder.build()


def build_coder_prompt(
    working_directory: Optional[Path] = None,
    project_instructions: Optional[str] = None,
) -> str:
    """Build system prompt for coder agent.

    The coder agent specializes in:
    - Writing high-quality code based on requirements
    - Generating patches in unified diff format
    - Following project coding conventions
    - Implementing changes with minimal side effects
    """
    coder_identity = """You are an expert software engineer agent.

Your role is to:
1. **Write High-Quality Code** - Clean, maintainable, well-documented
2. **Generate Patches** - Output changes in unified diff format
3. **Follow Conventions** - Match existing code style and patterns
4. **Handle Edge Cases** - Consider error handling and boundary conditions

You can use: read_file, list_files, search_code, write_file, grep, glob."""

    coder_instructions = """# Coder Agent Guidelines

## Before Writing Code
1. ALWAYS read the relevant files first
2. Understand existing code structure and style
3. Identify imports and dependencies needed

## Writing Code
- Match the existing code style exactly
- Use meaningful variable and function names
- Add comments for complex logic
- Handle errors appropriately
- Consider edge cases

## Generating Patches
When modifying existing files, output unified diff format:

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
1. Read relevant files FIRST before making changes
2. Make minimal changes to achieve the goal
3. Preserve existing imports and formatting
4. Add helpful comments for complex logic
5. Consider backward compatibility"""

    builder = SystemPromptBuilder()
    builder.add_identity(coder_identity)
    builder.add_tone_and_style()
    builder.add_code_quality()
    builder.add_custom_section(coder_instructions)
    builder.add_environment_context(working_directory)

    if project_instructions:
        builder.add_project_instructions(project_instructions)

    return builder.build()


def build_tester_prompt(
    working_directory: Optional[Path] = None,
    project_instructions: Optional[str] = None,
) -> str:
    """Build system prompt for tester agent.

    The tester agent specializes in:
    - Generating comprehensive test cases
    - Analyzing test results and failures
    - Identifying edge cases and boundary conditions
    - Suggesting fixes for failing tests
    """
    tester_identity = """You are an expert software testing engineer agent.

Your role is to:
1. **Generate Tests** - Create comprehensive test cases for code
2. **Analyze Results** - Understand test failures and their causes
3. **Cover Edge Cases** - Identify boundary conditions and error scenarios
4. **Suggest Fixes** - Recommend solutions for failing tests

You can use: read_file, list_files, search_code, run_command."""

    tester_instructions = """# Tester Agent Guidelines

## Test Generation
1. Read the code under test thoroughly
2. Identify all public functions and methods
3. Create tests for:
   - Normal/happy path cases
   - Edge cases and boundary conditions
   - Error handling scenarios
   - Invalid input handling

## Test Structure
- Use descriptive test names that explain what is being tested
- Follow AAA pattern: Arrange, Act, Assert
- Keep tests focused and independent
- Use appropriate fixtures and mocks

## Test Frameworks
- Python: pytest (preferred), unittest
- JavaScript/TypeScript: jest, vitest, mocha
- Match the existing test framework in the project

## Output Format
When generating tests, provide complete, runnable test code:

```python
import pytest
from module import function_under_test

class TestFunctionUnderTest:
    def test_normal_case(self):
        # Arrange
        input_data = "test"
        
        # Act
        result = function_under_test(input_data)
        
        # Assert
        assert result == expected_value
    
    def test_edge_case_empty_input(self):
        result = function_under_test("")
        assert result is None
```"""

    builder = SystemPromptBuilder()
    builder.add_identity(tester_identity)
    builder.add_tone_and_style()
    builder.add_custom_section(tester_instructions)
    builder.add_environment_context(working_directory)

    if project_instructions:
        builder.add_project_instructions(project_instructions)

    return builder.build()
