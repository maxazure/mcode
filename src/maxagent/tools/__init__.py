"""Tools module"""

from .base import BaseTool, ToolParameter, ToolResult
from .command import RunCommandTool
from .file import ListFilesTool, ReadFileTool, SecurityChecker, WriteFileTool
from .git import GitBranchTool, GitDiffTool, GitLogTool, GitStatusTool
from .glob import FindFilesTool, GlobTool
from .grep import GrepTool
from .registry import ToolRegistry
from .search import SearchCodeTool
from .webfetch import WebFetchTool

__all__ = [
    "BaseTool",
    "ToolParameter",
    "ToolResult",
    "ToolRegistry",
    "ReadFileTool",
    "ListFilesTool",
    "WriteFileTool",
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
    # Factory functions
    "create_default_registry",
    "create_registry_with_mcp",
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

    return registry


async def create_registry_with_mcp(
    project_root: "Path",  # noqa: F821
    load_mcp: bool = True,
) -> ToolRegistry:
    """Create a tool registry with default tools and MCP tools

    Args:
        project_root: Project root directory
        load_mcp: Whether to load MCP tools (default: True)

    Returns:
        ToolRegistry with both native and MCP tools registered
    """
    from pathlib import Path

    if isinstance(project_root, str):
        project_root = Path(project_root)

    # Start with default tools
    registry = create_default_registry(project_root)

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
