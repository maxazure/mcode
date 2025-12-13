"""Command execution tool with safety controls"""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from typing import Callable, Optional

from .base import BaseTool, ToolParameter, ToolResult


# Default whitelist of safe commands
DEFAULT_WHITELIST = [
    # Build and test commands
    "npm",
    "pnpm",
    "yarn",
    "npx",
    "python",
    "python3",
    "pip",
    "pip3",
    "pytest",
    "unittest",
    "mypy",
    "ruff",
    "black",
    "isort",
    "cargo",
    "rustc",
    "go",
    "make",
    # File operations (read-only)
    "ls",
    "cat",
    "head",
    "tail",
    "grep",
    "find",
    "wc",
    "tree",
    "file",
    "stat",
    "pwd",
    # Git (read-only)
    "git",
    # Development tools
    "node",
    "deno",
    "bun",
    "docker",
    "kubectl",
    "curl",
    "wget",  # For API testing
]


class RunCommandTool(BaseTool):
    """
    Tool for executing shell commands with safety controls.

    Features:
    - Command whitelist
    - Timeout protection
    - Output truncation
    - User confirmation for non-whitelisted commands
    """

    name = "run_command"
    description = "Execute a shell command in the project directory"
    parameters = [
        ToolParameter(
            name="command",
            type="string",
            description="The command to execute",
            required=True,
        ),
        ToolParameter(
            name="cwd",
            type="string",
            description="Working directory (relative to project root)",
            required=False,
        ),
        ToolParameter(
            name="timeout",
            type="integer",
            description="Timeout in seconds (default: 30)",
            required=False,
        ),
    ]
    risk_level = "high"

    def __init__(
        self,
        project_root: Path,
        timeout: int = 30,
        max_output: int = 50000,
        whitelist: Optional[list[str]] = None,
        require_confirmation: bool = True,
    ) -> None:
        """
        Initialize the command tool.

        Args:
            project_root: Project root directory
            timeout: Default timeout in seconds
            max_output: Maximum output characters (default 50000 for test output)
            whitelist: List of allowed commands (None = use default)
            require_confirmation: Whether to require user confirmation
        """
        self.project_root = project_root
        self.default_timeout = timeout
        self.max_output = max_output
        self.whitelist = whitelist if whitelist is not None else DEFAULT_WHITELIST
        self.require_confirmation = require_confirmation
        self._confirm_callback: Optional[Callable[[str], bool]] = None

    def set_confirm_callback(self, callback: Callable[[str], bool]) -> None:
        """
        Set callback for user confirmation.

        Args:
            callback: Function that returns True if command is approved
        """
        self._confirm_callback = callback

    async def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> ToolResult:
        """
        Execute a shell command.

        Args:
            command: Command to execute
            cwd: Working directory (relative to project root)
            timeout: Timeout in seconds

        Returns:
            ToolResult with command output
        """
        try:
            # Validate command
            if not command.strip():
                return ToolResult(
                    success=False,
                    output="",
                    error="Empty command",
                )

            # Check whitelist
            if not self._is_whitelisted(command):
                if self.require_confirmation:
                    if not await self._request_confirmation(command):
                        return ToolResult(
                            success=False,
                            output="",
                            error="Command execution denied by user",
                        )

            # Determine working directory
            work_dir = self.project_root
            if cwd:
                work_dir = self.project_root / cwd
                if not work_dir.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Directory not found: {cwd}",
                    )
                if not work_dir.is_dir():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Not a directory: {cwd}",
                    )

            # Determine timeout
            cmd_timeout = timeout or self.default_timeout

            # Execute command
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=cmd_timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Command timed out after {cmd_timeout} seconds",
                    metadata={"timeout": True},
                )

            # Decode output
            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # Truncate if needed
            if len(stdout_str) > self.max_output:
                stdout_str = stdout_str[: self.max_output] + "\n... (output truncated)"
            if len(stderr_str) > self.max_output:
                stderr_str = stderr_str[: self.max_output] + "\n... (error output truncated)"

            # Combine output
            output = stdout_str
            if stderr_str:
                if output:
                    output += "\n\n--- stderr ---\n" + stderr_str
                else:
                    output = stderr_str

            return ToolResult(
                success=process.returncode == 0,
                output=output or "(no output)",
                error=None if process.returncode == 0 else f"Exit code: {process.returncode}",
                metadata={
                    "exit_code": process.returncode,
                    "cwd": str(work_dir),
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )

    def _is_whitelisted(self, command: str) -> bool:
        """Check if command is in whitelist"""
        try:
            # Parse command to get the base command
            parts = shlex.split(command)
            if not parts:
                return False

            base_cmd = parts[0]

            # Handle paths (e.g., /usr/bin/python)
            if "/" in base_cmd:
                base_cmd = Path(base_cmd).name

            return base_cmd in self.whitelist

        except ValueError:
            # shlex parse error - be safe and deny
            return False

    async def _request_confirmation(self, command: str) -> bool:
        """Request user confirmation for command execution"""
        if self._confirm_callback:
            # If callback is async, await it; otherwise call directly
            result = self._confirm_callback(command)
            if asyncio.iscoroutine(result):
                return await result
            return result
        return False
