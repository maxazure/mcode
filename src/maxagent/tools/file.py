"""File operation tools"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any, Optional

from .base import BaseTool, ToolParameter, ToolResult
from .edit import FileReadTracker


class SecurityChecker:
    """Security checker for file operations"""

    DEFAULT_IGNORE_PATTERNS = [
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "*.p12",
        "*.pfx",
        "**/secrets/**",
        "**/credentials/**",
        ".git/config",
        "**/.git/config",
        "**/node_modules/**",
        "**/__pycache__/**",
        "**/.venv/**",
        "**/venv/**",
    ]

    def __init__(
        self,
        project_root: Path,
        ignore_patterns: Optional[list[str]] = None,
        allow_outside_project: bool = False,
    ) -> None:
        self.project_root = project_root.resolve()
        self.ignore_patterns = ignore_patterns or self.DEFAULT_IGNORE_PATTERNS
        self.allow_outside_project = allow_outside_project

    def is_safe_path(self, path: Path) -> bool:
        """Check if a path is safe to access"""
        try:
            resolved = path.resolve()

            # If outside project is allowed, only check ignore patterns
            if self.allow_outside_project:
                # Still check against sensitive file patterns
                for pattern in self.ignore_patterns:
                    if fnmatch.fnmatch(resolved.name, pattern):
                        return False
                return True

            # Must be within project root
            try:
                resolved.relative_to(self.project_root)
            except ValueError:
                return False

            # Check against ignore patterns
            rel_path = str(resolved.relative_to(self.project_root))
            for pattern in self.ignore_patterns:
                if fnmatch.fnmatch(rel_path, pattern):
                    return False
                if fnmatch.fnmatch(resolved.name, pattern):
                    return False

            return True

        except Exception:
            return False


class ReadFileTool(BaseTool):
    """Read file contents"""

    name = "read_file"
    description = (
        "Read the contents of a file. "
        "Path should be relative to project root (e.g., 'src/app.py', 'README.md')."
    )
    parameters = [
        ToolParameter(
            name="path",
            type="string",
            description="Path to the file (relative to project root, or absolute if allowed)",
        ),
        ToolParameter(
            name="start_line",
            type="integer",
            description="Starting line number (1-based, optional)",
            required=False,
        ),
        ToolParameter(
            name="end_line",
            type="integer",
            description="Ending line number (inclusive, optional)",
            required=False,
        ),
    ]
    risk_level = "low"

    def __init__(
        self,
        project_root: Path,
        security_checker: Optional[SecurityChecker] = None,
        max_file_size: int = 1024 * 1024,  # 1MB
        allow_outside_project: bool = False,
    ) -> None:
        self.project_root = project_root.resolve()
        self.allow_outside_project = allow_outside_project
        self.security_checker = security_checker or SecurityChecker(
            project_root, allow_outside_project=allow_outside_project
        )
        self.max_file_size = max_file_size

    def _resolve_path(self, path: str) -> Path:
        """Resolve path, handling ~ and absolute paths if allowed"""
        if self.allow_outside_project:
            # Expand ~ to home directory
            expanded = os.path.expanduser(path)
            if os.path.isabs(expanded):
                return Path(expanded)
        return self.project_root / path

    async def execute(
        self,
        path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Read file contents"""
        try:
            file_path = self._resolve_path(path)

            # Security check
            if not self.security_checker.is_safe_path(file_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Access denied: {path}",
                )

            if not file_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File not found: {path}",
                )

            if not file_path.is_file():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Not a file: {path}",
                )

            # Check file size
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File too large: {file_size} bytes (max: {self.max_file_size})",
                )

            # Read file
            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Cannot read file as text: {path}",
                )

            # Apply line range if specified
            if start_line is not None or end_line is not None:
                lines = content.splitlines(keepends=True)
                start_idx = (start_line - 1) if start_line else 0
                end_idx = end_line if end_line else len(lines)
                content = "".join(lines[start_idx:end_idx])

            # Calculate relative path for metadata
            try:
                rel_path = str(file_path.relative_to(self.project_root))
            except ValueError:
                rel_path = str(file_path)

            # Mark file as read for FileTime tracking (read-before-edit pattern)
            FileReadTracker.mark_read(path)
            FileReadTracker.mark_read(str(file_path))
            FileReadTracker.mark_read(rel_path)

            return ToolResult(
                success=True,
                output=content,
                metadata={
                    "path": rel_path,
                    "size": len(content),
                    "lines": content.count("\n")
                    + (1 if content and not content.endswith("\n") else 0),
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )


class ListFilesTool(BaseTool):
    """List files matching a glob pattern"""

    name = "list_files"
    description = "List files matching a glob pattern"
    parameters = [
        ToolParameter(
            name="pattern",
            type="string",
            description="Glob pattern (e.g., 'src/**/*.py', '*.md')",
        ),
        ToolParameter(
            name="max_results",
            type="integer",
            description="Maximum number of results (default: 100)",
            required=False,
            default=100,
        ),
    ]
    risk_level = "low"

    def __init__(
        self,
        project_root: Path,
        security_checker: Optional[SecurityChecker] = None,
        allow_outside_project: bool = False,
    ) -> None:
        self.project_root = project_root.resolve()
        self.allow_outside_project = allow_outside_project
        self.security_checker = security_checker or SecurityChecker(
            project_root, allow_outside_project=allow_outside_project
        )

    async def execute(
        self,
        pattern: str,
        max_results: int = 100,
        **kwargs: Any,
    ) -> ToolResult:
        """List files matching pattern"""
        try:
            matches: list[str] = []

            # If pattern starts with ~ or /, use it as absolute
            if self.allow_outside_project and (pattern.startswith("~") or pattern.startswith("/")):
                search_path = Path(os.path.expanduser(pattern)).parent
                glob_pattern = Path(pattern).name
                if search_path.exists():
                    for path in search_path.glob(glob_pattern):
                        if path.is_file() and self.security_checker.is_safe_path(path):
                            matches.append(str(path))
                            if len(matches) >= max_results:
                                break
            else:
                for path in self.project_root.glob(pattern):
                    if path.is_file() and self.security_checker.is_safe_path(path):
                        rel_path = path.relative_to(self.project_root)
                        matches.append(str(rel_path))
                        if len(matches) >= max_results:
                            break

            # Sort for consistent output
            matches.sort()

            return ToolResult(
                success=True,
                output="\n".join(matches) if matches else "(no files found)",
                metadata={
                    "count": len(matches),
                    "pattern": pattern,
                    "truncated": len(matches) >= max_results,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )


class WriteFileTool(BaseTool):
    """Write content to a file - USE ONLY FOR NEW FILES"""

    name = "write_file"
    description = (
        "Create a NEW file with the given content. "
        "WARNING: This overwrites the entire file when overwrite=true. "
        "For existing files, either use the `edit` tool or explicitly set overwrite=true "
        "(after reading the file) to replace it. Path must be relative to project root by default."
    )
    parameters = [
        ToolParameter(
            name="path",
            type="string",
            description="Path to the file (relative to project root, or absolute if allowed)",
        ),
        ToolParameter(
            name="content",
            type="string",
            description="Content to write",
        ),
        ToolParameter(
            name="overwrite",
            type="boolean",
            description=(
                "Set to true to overwrite an existing file. "
                "Default is false to prevent accidental destruction."
            ),
            required=False,
        ),
    ]
    risk_level = "high"

    def __init__(
        self,
        project_root: Path,
        security_checker: Optional[SecurityChecker] = None,
        create_dirs: bool = True,
        allow_outside_project: bool = False,
    ) -> None:
        self.project_root = project_root.resolve()
        self.allow_outside_project = allow_outside_project
        self.security_checker = security_checker or SecurityChecker(
            project_root, allow_outside_project=allow_outside_project
        )
        self.create_dirs = create_dirs

    def _resolve_path(self, path: str) -> Path:
        """Resolve path, handling ~ and absolute paths if allowed"""
        if self.allow_outside_project:
            # Expand ~ to home directory
            expanded = os.path.expanduser(path)
            if os.path.isabs(expanded):
                return Path(expanded)
        return self.project_root / path

    async def execute(
        self,
        path: str,
        content: str,
        overwrite: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Write content to file"""
        try:
            # Check for paths that try to escape project root (only if not allowed)
            if not self.allow_outside_project:
                if path.startswith("~") or path.startswith("/"):
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Cannot write to absolute path or home directory: {path}. "
                        f"Use a path relative to the project root instead. "
                        f"Project root is: {self.project_root}. "
                        f"To write anywhere, use --dangerously-allow-outside-project flag.",
                    )

                # Check for path traversal attempts
                if ".." in path:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Path traversal not allowed: {path}. Use a path within the project.",
                    )

            file_path = self._resolve_path(path)

            # Block accidental overwrite of existing files unless explicitly allowed
            if file_path.exists() and not overwrite:
                return ToolResult(
                    success=False,
                    output="",
                    error=(
                        "Refusing to overwrite existing file. "
                        "Use overwrite=true and include the full file content, or use the edit tool."
                    ),
                )

            # If overwriting, require the caller to have read the file recently to avoid blind clobbering
            if file_path.exists() and overwrite:
                if not FileReadTracker.was_read_recently(path) and not FileReadTracker.was_read_recently(str(file_path)):
                    return ToolResult(
                        success=False,
                        output="",
                        error=(
                            "Overwrite requested but file was not read recently. "
                            "Read the file first to avoid losing content, or use the edit tool."
                        ),
                    )

            # Security check
            if not self.security_checker.is_safe_path(file_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Access denied: {path}. File matches a protected pattern.",
                )

            # Create directories if needed
            if self.create_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            file_path.write_text(content, encoding="utf-8")

            # Calculate display path
            try:
                display_path = str(file_path.relative_to(self.project_root))
            except ValueError:
                display_path = str(file_path)

            return ToolResult(
                success=True,
                output=f"Successfully wrote {len(content)} bytes to {display_path}",
                metadata={
                    "path": display_path,
                    "size": len(content),
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )
