"""Authentication module for external providers"""

from .github_copilot import GitHubCopilotAuth, CopilotToken, CopilotSession

__all__ = ["GitHubCopilotAuth", "CopilotToken", "CopilotSession"]
