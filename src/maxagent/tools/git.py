"""Git tools for repository operations"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from .base import BaseTool, ToolParameter, ToolResult


class GitStatusTool(BaseTool):
    """Tool to get git repository status"""
    
    name = "git_status"
    description = "Get the current git status showing modified, staged, and untracked files"
    parameters = [
        ToolParameter(
            name="short",
            type="boolean",
            description="Use short format output",
            required=False,
        ),
    ]
    risk_level = "low"
    
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
    
    async def execute(
        self,
        short: bool = False,
    ) -> ToolResult:
        """Get git status"""
        try:
            cmd = ["git", "status"]
            if short:
                cmd.append("--short")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.project_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                if "not a git repository" in error_msg.lower():
                    return ToolResult(
                        success=False,
                        output="",
                        error="Not a git repository",
                    )
                return ToolResult(
                    success=False,
                    output="",
                    error=error_msg,
                )
            
            output = stdout.decode("utf-8", errors="replace")
            return ToolResult(
                success=True,
                output=output or "Nothing to report (clean working tree)",
            )
            
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error="git command not found",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )


class GitDiffTool(BaseTool):
    """Tool to get git diff output"""
    
    name = "git_diff"
    description = "Get git diff showing changes in the working tree or between commits"
    parameters = [
        ToolParameter(
            name="path",
            type="string",
            description="Specific file or directory to diff (optional)",
            required=False,
        ),
        ToolParameter(
            name="staged",
            type="boolean",
            description="Show staged changes (--cached)",
            required=False,
        ),
        ToolParameter(
            name="ref",
            type="string",
            description="Reference to compare against (branch, commit, etc.)",
            required=False,
        ),
    ]
    risk_level = "low"
    
    def __init__(self, project_root: Path, max_output: int = 10000) -> None:
        self.project_root = project_root
        self.max_output = max_output
    
    async def execute(
        self,
        path: Optional[str] = None,
        staged: bool = False,
        ref: Optional[str] = None,
    ) -> ToolResult:
        """Get git diff"""
        try:
            cmd = ["git", "diff"]
            
            if staged:
                cmd.append("--cached")
            
            if ref:
                cmd.append(ref)
            
            if path:
                cmd.append("--")
                cmd.append(path)
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.project_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=stderr.decode("utf-8", errors="replace"),
                )
            
            output = stdout.decode("utf-8", errors="replace")
            
            # Truncate if too long
            if len(output) > self.max_output:
                output = output[:self.max_output] + "\n... (diff truncated)"
            
            return ToolResult(
                success=True,
                output=output or "No changes",
            )
            
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error="git command not found",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )


class GitLogTool(BaseTool):
    """Tool to view git commit history"""
    
    name = "git_log"
    description = "View git commit history"
    parameters = [
        ToolParameter(
            name="count",
            type="integer",
            description="Number of commits to show (default: 10)",
            required=False,
        ),
        ToolParameter(
            name="oneline",
            type="boolean",
            description="Use one-line format",
            required=False,
        ),
        ToolParameter(
            name="path",
            type="string",
            description="Show commits for specific file/directory",
            required=False,
        ),
    ]
    risk_level = "low"
    
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
    
    async def execute(
        self,
        count: int = 10,
        oneline: bool = True,
        path: Optional[str] = None,
    ) -> ToolResult:
        """Get git log"""
        try:
            cmd = ["git", "log", f"-{count}"]
            
            if oneline:
                cmd.append("--oneline")
            
            if path:
                cmd.append("--")
                cmd.append(path)
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.project_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=stderr.decode("utf-8", errors="replace"),
                )
            
            output = stdout.decode("utf-8", errors="replace")
            return ToolResult(
                success=True,
                output=output or "No commits found",
            )
            
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error="git command not found",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )


class GitBranchTool(BaseTool):
    """Tool to list git branches"""
    
    name = "git_branch"
    description = "List git branches"
    parameters = [
        ToolParameter(
            name="all",
            type="boolean",
            description="Show all branches including remote",
            required=False,
        ),
    ]
    risk_level = "low"
    
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
    
    async def execute(
        self,
        all: bool = False,
    ) -> ToolResult:
        """List git branches"""
        try:
            cmd = ["git", "branch"]
            
            if all:
                cmd.append("-a")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.project_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=stderr.decode("utf-8", errors="replace"),
                )
            
            output = stdout.decode("utf-8", errors="replace")
            return ToolResult(
                success=True,
                output=output or "No branches found",
            )
            
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error="git command not found",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )
