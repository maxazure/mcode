"""Tools module"""

from .base import BaseTool, ToolParameter, ToolResult
from .command import RunCommandTool
from .edit import EditTool
from .file import ListFilesTool, ReadFileTool, SecurityChecker, WriteFileTool
from .git import GitBranchTool, GitDiffTool, GitLogTool, GitStatusTool
from .glob import FindFilesTool, GlobTool
from .grep import GrepTool
from .registry import ToolRegistry
from .search import SearchCodeTool
from .webfetch import WebFetchTool
from .subagent import SubAgentTool, TaskTool
from .todo import TodoWriteTool, TodoReadTool, TodoClearTool, get_todo_list, reset_todo_list
from .memory import MemorySearchTool

__all__ = [
    "BaseTool",
    "ToolParameter",
    "ToolResult",
    "ToolRegistry",
    "ReadFileTool",
    "ListFilesTool",
    "WriteFileTool",
    "EditTool",  # New edit tool
    "SearchCodeTool",
    "SecurityChecker",
    "RunCommandTool",
    "GitStatusTool",
    "GitDiffTool",
    "GitLogTool",
    "GitBranchTool",
    # New tools
    "GrepTool",
    "GlobTool",
    "FindFilesTool",
    "WebFetchTool",
    # SubAgent tools
    "SubAgentTool",
    "TaskTool",
    # Todo tools
    "TodoWriteTool",
    "TodoReadTool",
    "TodoClearTool",
    "get_todo_list",
    "reset_todo_list",
    # Memory tool
    "MemorySearchTool",
    # Factory functions
    "create_default_registry",
    "create_registry_with_mcp",
    "create_registry_with_subagent",
    "create_full_registry",
]


def create_default_registry(
    project_root: "Path",  # noqa: F821
    allow_outside_project: bool = False,
) -> ToolRegistry:
    """Create a tool registry with default tools

    Args:
        project_root: Project root directory
        allow_outside_project: If True, allow file operations outside project directory

    Returns:
        ToolRegistry with default tools registered
    """
    from pathlib import Path

    if isinstance(project_root, str):
        project_root = Path(project_root)

    registry = ToolRegistry()
    security_checker = SecurityChecker(project_root, allow_outside_project=allow_outside_project)

    # Register file tools
    registry.register(
        ReadFileTool(project_root, security_checker, allow_outside_project=allow_outside_project)
    )
    registry.register(
        ListFilesTool(project_root, security_checker, allow_outside_project=allow_outside_project)
    )
    registry.register(
        WriteFileTool(project_root, security_checker, allow_outside_project=allow_outside_project)
    )
    # Register edit tool (preferred for modifying existing files)
    registry.register(EditTool(project_root, allow_outside_project=allow_outside_project))

    # Register search tools
    registry.register(SearchCodeTool(project_root, security_checker))
    registry.register(GrepTool(project_root, security_checker))
    registry.register(GlobTool(project_root, security_checker))
    registry.register(FindFilesTool(project_root, security_checker))

    # Register command tool (auto-approve whitelisted commands)
    cmd_tool = RunCommandTool(project_root, require_confirmation=True)
    # Auto-approve whitelisted commands by setting callback that returns True
    cmd_tool.set_confirm_callback(lambda cmd: True)
    registry.register(cmd_tool)

    # Register git tools
    registry.register(GitStatusTool(project_root))
    registry.register(GitDiffTool(project_root))
    registry.register(GitLogTool(project_root))
    registry.register(GitBranchTool(project_root))

    # Register web tools
    registry.register(WebFetchTool())

    # Register todo tools
    registry.register(TodoWriteTool())
    registry.register(TodoReadTool())
    registry.register(TodoClearTool())

    # Register memory search tool
    registry.register(MemorySearchTool(project_root))

    return registry


def create_registry_with_subagent(
    project_root: "Path",  # noqa: F821
    config: "Config",  # noqa: F821
    llm_client: "LLMClient" = None,  # noqa: F821
    allow_outside_project: bool = False,
    enable_subagent: bool = True,
    max_subagent_iterations: int = 50,
) -> ToolRegistry:
    """Create a tool registry with default tools and SubAgent tools

    Args:
        project_root: Project root directory
        config: Application configuration
        llm_client: Optional LLM client to share with SubAgents
        allow_outside_project: If True, allow file operations outside project directory
        enable_subagent: If True, register SubAgent and Task tools
        max_subagent_iterations: Max iterations for sub-agents

    Returns:
        ToolRegistry with SubAgent tools registered
    """
    from pathlib import Path

    if isinstance(project_root, str):
        project_root = Path(project_root)

    # Start with default tools
    registry = create_default_registry(project_root, allow_outside_project=allow_outside_project)

    # Register SubAgent tools if enabled
    if enable_subagent:
        # Note: We don't pass tool_registry to avoid circular reference
        # SubAgents will create their own registry
        registry.register(
            SubAgentTool(
                project_root=project_root,
                config=config,
                llm_client=llm_client,
                tool_registry=None,  # SubAgents get their own registry
                max_iterations=max_subagent_iterations,
            )
        )
        registry.register(
            TaskTool(
                project_root=project_root,
                config=config,
                llm_client=llm_client,
                tool_registry=None,
                max_iterations=max_subagent_iterations,
            )
        )

    return registry


async def create_registry_with_mcp(
    project_root: "Path",  # noqa: F821
    load_mcp: bool = True,
    allow_outside_project: bool = False,
) -> ToolRegistry:
    """Create a tool registry with default tools and MCP tools

    Args:
        project_root: Project root directory
        load_mcp: Whether to load MCP tools (default: True)
        allow_outside_project: If True, allow file operations outside project directory (YOLO mode)

    Returns:
        ToolRegistry with both native and MCP tools registered
    """
    from pathlib import Path

    if isinstance(project_root, str):
        project_root = Path(project_root)

    # Start with default tools
    registry = create_default_registry(project_root, allow_outside_project=allow_outside_project)

    # Load MCP tools if enabled
    if load_mcp:
        try:
            from maxagent.mcp.tools import get_mcp_registry

            mcp_registry = await get_mcp_registry()
            mcp_tools = mcp_registry.get_tools()

            for tool in mcp_tools:
                registry.register(tool)

        except Exception as e:
            # Log warning but don't fail - MCP is optional
            import sys

            print(f"Warning: Failed to load MCP tools: {e}", file=sys.stderr)

    return registry


async def create_full_registry(
    project_root: "Path",  # noqa: F821
    config: "Config" = None,  # noqa: F821
    llm_client: "LLMClient" = None,  # noqa: F821
    allow_outside_project: bool = False,
    load_mcp: bool = True,
    enable_subagent: bool = True,
    max_subagent_iterations: int = 50,
) -> ToolRegistry:
    """Create a full tool registry with all tools including MCP and SubAgent

    Args:
        project_root: Project root directory
        config: Application configuration (required for SubAgent)
        llm_client: Optional LLM client to share
        allow_outside_project: If True, allow file operations outside project directory
        load_mcp: Whether to load MCP tools
        enable_subagent: Whether to enable SubAgent tools
        max_subagent_iterations: Max iterations for sub-agents

    Returns:
        ToolRegistry with all tools registered
    """
    from pathlib import Path

    if isinstance(project_root, str):
        project_root = Path(project_root)

    # Start with default tools
    registry = create_default_registry(project_root, allow_outside_project=allow_outside_project)

    # Register SubAgent tools if enabled and config is provided
    if enable_subagent and config is not None:
        registry.register(
            SubAgentTool(
                project_root=project_root,
                config=config,
                llm_client=llm_client,
                tool_registry=None,
                max_iterations=max_subagent_iterations,
            )
        )
        registry.register(
            TaskTool(
                project_root=project_root,
                config=config,
                llm_client=llm_client,
                tool_registry=None,
                max_iterations=max_subagent_iterations,
            )
        )

    # Load MCP tools if enabled
    if load_mcp:
        try:
            from maxagent.mcp.tools import get_mcp_registry

            mcp_registry = await get_mcp_registry()
            mcp_tools = mcp_registry.get_tools()

            for tool in mcp_tools:
                registry.register(tool)

        except Exception as e:
            # Log warning but don't fail - MCP is optional
            import sys

            print(f"Warning: Failed to load MCP tools: {e}", file=sys.stderr)

    return registry
