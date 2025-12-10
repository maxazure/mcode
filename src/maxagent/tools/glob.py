"""Glob tool for fast file pattern matching"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any, Optional

from .base import BaseTool, ToolParameter, ToolResult
from .file import SecurityChecker


class GlobTool(BaseTool):
    """Fast file pattern matching tool
    
    - Supports glob patterns like "**/*.py" or "src/**/*.ts"
    - Returns matching file paths sorted by modification time
    - Use this tool when you need to find files by name patterns
    """

    name = "glob"
    description = "Fast file pattern matching tool that works with any codebase size"
    parameters = [
        ToolParameter(
            name="pattern",
            type="string",
            description='The glob pattern to match files against (e.g., "**/*.py", "src/**/*.ts")',
        ),
        ToolParameter(
            name="path",
            type="string",
            description="The directory to search in (defaults to project root)",
            required=False,
            default=".",
        ),
        ToolParameter(
            name="max_results",
            type="integer",
            description="Maximum number of files to return (default: 100)",
            required=False,
            default=100,
        ),
        ToolParameter(
            name="include_hidden",
            type="boolean",
            description="Include hidden files and directories (default: false)",
            required=False,
            default=False,
        ),
    ]
    risk_level = "low"

    # Common patterns to exclude
    DEFAULT_EXCLUDE_PATTERNS = [
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "*.pyc",
        "*.pyo",
        ".DS_Store",
        "Thumbs.db",
        ".env",
        ".venv",
        "venv",
        "env",
        "dist",
        "build",
        "*.egg-info",
    ]

    def __init__(
        self,
        project_root: Path,
        security_checker: Optional[SecurityChecker] = None,
        exclude_patterns: Optional[list[str]] = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.security_checker = security_checker or SecurityChecker(project_root)
        self.exclude_patterns = exclude_patterns or self.DEFAULT_EXCLUDE_PATTERNS

    def _should_exclude(self, path: Path, include_hidden: bool) -> bool:
        """Check if path should be excluded"""
        name = path.name

        # Check hidden files
        if not include_hidden and name.startswith("."):
            return True

        # Check exclude patterns
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
            # Also check full path segments
            for part in path.parts:
                if fnmatch.fnmatch(part, pattern):
                    return True

        return False

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        max_results: int = 100,
        include_hidden: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Find files matching glob pattern"""
        try:
            search_path = self.project_root / path

            if not search_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path not found: {path}",
                )

            if not search_path.is_dir():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path is not a directory: {path}",
                )

            # Collect all matching files
            matching_files: list[tuple[Path, float]] = []

            for file_path in search_path.glob(pattern):
                if not file_path.is_file():
                    continue

                # Check security
                if not self.security_checker.is_safe_path(file_path):
                    continue

                # Check exclusions
                try:
                    rel_path = file_path.relative_to(search_path)
                except ValueError:
                    continue

                if self._should_exclude(rel_path, include_hidden):
                    continue

                # Get modification time
                try:
                    mtime = file_path.stat().st_mtime
                except OSError:
                    mtime = 0

                matching_files.append((file_path, mtime))

            # Sort by modification time (newest first)
            matching_files.sort(key=lambda x: x[1], reverse=True)

            # Limit results
            total_found = len(matching_files)
            matching_files = matching_files[:max_results]

            if not matching_files:
                return ToolResult(
                    success=True,
                    output=f"No files found matching pattern: {pattern}",
                    metadata={"total_found": 0, "results_shown": 0},
                )

            # Format output
            output_lines: list[str] = []
            for file_path, _ in matching_files:
                try:
                    rel_path = file_path.relative_to(self.project_root)
                    output_lines.append(str(rel_path))
                except ValueError:
                    output_lines.append(str(file_path))

            output = "\n".join(output_lines)

            if total_found > max_results:
                output += f"\n... and {total_found - max_results} more files"

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "total_found": total_found,
                    "results_shown": len(matching_files),
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )


class FindFilesTool(BaseTool):
    """Find files by name (simpler than glob)"""

    name = "find_files"
    description = "Find files by name pattern (case-insensitive)"
    parameters = [
        ToolParameter(
            name="name",
            type="string",
            description='File name or pattern to search for (e.g., "config.py", "*.json")',
        ),
        ToolParameter(
            name="path",
            type="string",
            description="The directory to search in (defaults to project root)",
            required=False,
            default=".",
        ),
        ToolParameter(
            name="max_results",
            type="integer",
            description="Maximum number of files to return (default: 50)",
            required=False,
            default=50,
        ),
    ]
    risk_level = "low"

    def __init__(
        self,
        project_root: Path,
        security_checker: Optional[SecurityChecker] = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.security_checker = security_checker or SecurityChecker(project_root)

    async def execute(
        self,
        name: str,
        path: str = ".",
        max_results: int = 50,
        **kwargs: Any,
    ) -> ToolResult:
        """Find files by name"""
        try:
            search_path = self.project_root / path

            if not search_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path not found: {path}",
                )

            matching_files: list[str] = []
            name_lower = name.lower()

            for root, dirs, files in os.walk(search_path):
                # Skip hidden and common excluded directories
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(".")
                    and d not in ("node_modules", "__pycache__", ".git", "venv", ".venv")
                ]

                for filename in files:
                    file_path = Path(root) / filename

                    # Check security
                    if not self.security_checker.is_safe_path(file_path):
                        continue

                    # Match pattern (case-insensitive)
                    if "*" in name or "?" in name:
                        if fnmatch.fnmatch(filename.lower(), name_lower):
                            rel_path = file_path.relative_to(self.project_root)
                            matching_files.append(str(rel_path))
                    else:
                        if name_lower in filename.lower():
                            rel_path = file_path.relative_to(self.project_root)
                            matching_files.append(str(rel_path))

                    if len(matching_files) >= max_results:
                        break

                if len(matching_files) >= max_results:
                    break

            if not matching_files:
                return ToolResult(
                    success=True,
                    output=f"No files found matching: {name}",
                    metadata={"total_found": 0},
                )

            output = "\n".join(matching_files)

            return ToolResult(
                success=True,
                output=output,
                metadata={"total_found": len(matching_files)},
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )
