"""Code search tools"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from .base import BaseTool, ToolParameter, ToolResult
from .file import SecurityChecker


class SearchCodeTool(BaseTool):
    """Search code using regex pattern"""

    name = "search_code"
    description = "Search for a pattern in files using regex"
    parameters = [
        ToolParameter(
            name="pattern",
            type="string",
            description="Regex pattern to search for",
        ),
        ToolParameter(
            name="path",
            type="string",
            description="Directory or file path to search in (default: project root)",
            required=False,
            default=".",
        ),
        ToolParameter(
            name="file_pattern",
            type="string",
            description="Glob pattern to filter files (e.g., '*.py', '*.ts')",
            required=False,
        ),
        ToolParameter(
            name="max_results",
            type="integer",
            description="Maximum number of matches to return (default: 50)",
            required=False,
            default=50,
        ),
        ToolParameter(
            name="context_lines",
            type="integer",
            description="Number of context lines before and after match (default: 2)",
            required=False,
            default=2,
        ),
    ]
    risk_level = "low"

    def __init__(
        self,
        project_root: Path,
        security_checker: Optional[SecurityChecker] = None,
        max_file_size: int = 1024 * 1024,  # 1MB
    ) -> None:
        self.project_root = project_root.resolve()
        self.security_checker = security_checker or SecurityChecker(project_root)
        self.max_file_size = max_file_size

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        file_pattern: Optional[str] = None,
        max_results: int = 50,
        context_lines: int = 2,
        **kwargs: Any,
    ) -> ToolResult:
        """Search for pattern in files"""
        try:
            # Compile regex
            try:
                regex = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid regex pattern: {e}",
                )

            search_path = self.project_root / path

            if not search_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path not found: {path}",
                )

            results: list[str] = []
            total_matches = 0
            files_searched = 0

            # Get files to search
            if search_path.is_file():
                files = [search_path]
            else:
                glob_pattern = file_pattern or "**/*"
                files = list(search_path.glob(glob_pattern))

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

                files_searched += 1
                lines = content.splitlines()

                for i, line in enumerate(lines):
                    if regex.search(line):
                        total_matches += 1

                        if len(results) < max_results:
                            # Get context
                            start = max(0, i - context_lines)
                            end = min(len(lines), i + context_lines + 1)
                            context = lines[start:end]

                            rel_path = file_path.relative_to(self.project_root)
                            result_block = f"=== {rel_path}:{i + 1} ===\n"
                            for j, ctx_line in enumerate(context, start=start + 1):
                                prefix = ">" if j == i + 1 else " "
                                result_block += f"{prefix} {j}: {ctx_line}\n"

                            results.append(result_block)

            if not results:
                output = f"No matches found for pattern: {pattern}"
            else:
                output = "\n".join(results)
                if total_matches > max_results:
                    output += f"\n... and {total_matches - max_results} more matches"

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "total_matches": total_matches,
                    "results_shown": len(results),
                    "files_searched": files_searched,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )
