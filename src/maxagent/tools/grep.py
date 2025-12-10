"""Grep tool for fast content search using regex"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from .base import BaseTool, ToolParameter, ToolResult
from .file import SecurityChecker


class GrepTool(BaseTool):
    """Fast content search using regex (similar to ripgrep)
    
    - Searches file contents using regular expressions
    - Supports full regex syntax (eg. "log.*Error", "function\\s+\\w+")
    - Filter files by pattern with the include parameter
    - Returns file paths with matches sorted by modification time
    """

    name = "grep"
    description = "Fast content search tool that searches file contents using regular expressions"
    parameters = [
        ToolParameter(
            name="pattern",
            type="string",
            description="The regex pattern to search for in file contents",
        ),
        ToolParameter(
            name="path",
            type="string",
            description="The directory to search in (defaults to project root)",
            required=False,
            default=".",
        ),
        ToolParameter(
            name="include",
            type="string",
            description='File pattern to include in the search (e.g. "*.py", "*.{ts,tsx}")',
            required=False,
        ),
        ToolParameter(
            name="max_results",
            type="integer",
            description="Maximum number of file matches to return (default: 50)",
            required=False,
            default=50,
        ),
        ToolParameter(
            name="context_lines",
            type="integer",
            description="Number of context lines before and after match (default: 0)",
            required=False,
            default=0,
        ),
    ]
    risk_level = "low"

    def __init__(
        self,
        project_root: Path,
        security_checker: Optional[SecurityChecker] = None,
        max_file_size: int = 1024 * 1024,  # 1MB
        use_ripgrep: bool = True,
    ) -> None:
        self.project_root = project_root.resolve()
        self.security_checker = security_checker or SecurityChecker(project_root)
        self.max_file_size = max_file_size
        self.use_ripgrep = use_ripgrep and self._check_ripgrep()

    def _check_ripgrep(self) -> bool:
        """Check if ripgrep is available"""
        try:
            result = subprocess.run(
                ["rg", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        include: Optional[str] = None,
        max_results: int = 50,
        context_lines: int = 0,
        **kwargs: Any,
    ) -> ToolResult:
        """Search for pattern in files using grep/ripgrep"""
        try:
            search_path = self.project_root / path

            if not search_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path not found: {path}",
                )

            # Use ripgrep if available (much faster)
            if self.use_ripgrep:
                return await self._search_with_ripgrep(
                    pattern, search_path, include, max_results, context_lines
                )
            else:
                return await self._search_with_python(
                    pattern, search_path, include, max_results, context_lines
                )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )

    async def _search_with_ripgrep(
        self,
        pattern: str,
        search_path: Path,
        include: Optional[str],
        max_results: int,
        context_lines: int,
    ) -> ToolResult:
        """Search using ripgrep (rg)"""
        cmd = ["rg", "--color=never", "--line-number"]

        # Add context lines
        if context_lines > 0:
            cmd.extend(["-C", str(context_lines)])

        # Add file pattern filter
        if include:
            cmd.extend(["--glob", include])

        # Add max results
        cmd.extend(["--max-count", str(max_results)])

        # Add pattern and path
        cmd.append(pattern)
        cmd.append(str(search_path))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.project_root,
            )

            if result.returncode == 0:
                output = result.stdout.strip()
                if not output:
                    output = f"No matches found for pattern: {pattern}"

                # Filter out security-sensitive paths
                lines = output.split("\n")
                filtered_lines = []
                for line in lines:
                    # Extract file path from rg output (format: path:line:content)
                    if ":" in line:
                        file_part = line.split(":")[0]
                        file_path = self.project_root / file_part
                        if self.security_checker.is_safe_path(file_path):
                            filtered_lines.append(line)
                    else:
                        filtered_lines.append(line)

                output = "\n".join(filtered_lines)

                return ToolResult(
                    success=True,
                    output=output,
                    metadata={"tool": "ripgrep"},
                )
            elif result.returncode == 1:
                # No matches
                return ToolResult(
                    success=True,
                    output=f"No matches found for pattern: {pattern}",
                    metadata={"tool": "ripgrep", "total_matches": 0},
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"ripgrep error: {result.stderr}",
                )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error="Search timed out after 60 seconds",
            )

    async def _search_with_python(
        self,
        pattern: str,
        search_path: Path,
        include: Optional[str],
        max_results: int,
        context_lines: int,
    ) -> ToolResult:
        """Search using Python regex (fallback)"""
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid regex pattern: {e}",
            )

        results: list[str] = []
        total_matches = 0
        files_with_matches = 0

        # Get files to search
        if search_path.is_file():
            files = [search_path]
        else:
            glob_pattern = include or "**/*"
            files = sorted(
                search_path.glob(glob_pattern),
                key=lambda f: f.stat().st_mtime if f.exists() else 0,
                reverse=True,
            )

        for file_path in files:
            if not file_path.is_file():
                continue

            if not self.security_checker.is_safe_path(file_path):
                continue

            # Skip large files
            if file_path.stat().st_size > self.max_file_size:
                continue

            # Skip binary files
            try:
                content = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue

            lines = content.splitlines()
            file_matches: list[str] = []

            for i, line in enumerate(lines):
                if regex.search(line):
                    total_matches += 1

                    if len(results) < max_results:
                        rel_path = file_path.relative_to(self.project_root)

                        if context_lines > 0:
                            start = max(0, i - context_lines)
                            end = min(len(lines), i + context_lines + 1)
                            context = lines[start:end]
                            result_block = f"{rel_path}:{i + 1}:\n"
                            for j, ctx_line in enumerate(context, start=start + 1):
                                prefix = ">" if j == i + 1 else " "
                                result_block += f"{prefix} {j}: {ctx_line}\n"
                            file_matches.append(result_block)
                        else:
                            file_matches.append(f"{rel_path}:{i + 1}:{line}")

            if file_matches:
                files_with_matches += 1
                results.extend(file_matches)

            if len(results) >= max_results:
                break

        if not results:
            output = f"No matches found for pattern: {pattern}"
        else:
            output = "\n".join(results[:max_results])
            if total_matches > max_results:
                output += f"\n... and {total_matches - max_results} more matches"

        return ToolResult(
            success=True,
            output=output,
            metadata={
                "tool": "python",
                "total_matches": total_matches,
                "files_with_matches": files_with_matches,
            },
        )
