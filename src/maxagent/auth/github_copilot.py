"""GitHub Copilot OAuth authentication and API client"""

from __future__ import annotations

import json
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

# GitHub OAuth App configuration (VS Code's Copilot extension client ID)
GITHUB_CLIENT_ID = "Iv1.b507a08c87ecfe98"

# API endpoints
GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"
COPILOT_CHAT_URL = "https://api.githubcopilot.com/chat/completions"

# Token storage location
DEFAULT_TOKEN_DIR = Path.home() / ".llc" / "copilot"
DEFAULT_TOKEN_FILE = "token.json"

# Editor headers required by Copilot API
EDITOR_VERSION = "vscode/1.95.0"
EDITOR_PLUGIN_VERSION = "copilot-chat/0.22.0"
COPILOT_INTEGRATION_ID = "vscode-chat"
USER_AGENT = "GitHubCopilotChat/0.22.0"


@dataclass
class CopilotToken:
    """GitHub Copilot API token"""

    token: str
    expires_at: int  # Unix timestamp
    refresh_token: Optional[str] = None
    github_token: Optional[str] = None  # GitHub OAuth token for refreshing

    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 5 minute buffer)"""
        return time.time() > (self.expires_at - 300)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "token": self.token,
            "expires_at": self.expires_at,
            "refresh_token": self.refresh_token,
            "github_token": self.github_token,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CopilotToken:
        """Create from dictionary"""
        return cls(
            token=data["token"],
            expires_at=data["expires_at"],
            refresh_token=data.get("refresh_token"),
            github_token=data.get("github_token"),
        )


@dataclass
class CopilotSession:
    """Manages session state for X-Initiator header optimization

    GitHub Copilot uses X-Initiator header to track premium requests:
    - 'user': First message in a session (counts as premium request)
    - 'agent': Subsequent messages (tool calls, etc.) (doesn't count as premium)

    This helps avoid double-counting premium requests.
    """

    is_first_message: bool = True
    conversation_id: Optional[str] = None
    _message_count: int = 0

    def get_initiator(self) -> str:
        """Get the X-Initiator header value for current request

        Returns:
            'user' for first message, 'agent' for subsequent messages
        """
        if self.is_first_message:
            self.is_first_message = False
            self._message_count = 1
            return "user"
        self._message_count += 1
        return "agent"

    def reset(self) -> None:
        """Reset session for new conversation"""
        self.is_first_message = True
        self.conversation_id = None
        self._message_count = 0

    @property
    def message_count(self) -> int:
        """Get total message count in this session"""
        return self._message_count


@dataclass
class DeviceCodeResponse:
    """GitHub Device Code flow response"""

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class GitHubCopilotAuth:
    """GitHub Copilot OAuth authentication handler"""

    def __init__(
        self,
        token_dir: Optional[Path] = None,
        auto_open_browser: bool = True,
    ) -> None:
        self.token_dir = token_dir or DEFAULT_TOKEN_DIR
        self.token_file = self.token_dir / DEFAULT_TOKEN_FILE
        self.auto_open_browser = auto_open_browser
        self._token: Optional[CopilotToken] = None
        self._github_token: Optional[str] = None
        self._session = CopilotSession()

    @property
    def session(self) -> CopilotSession:
        """Get current session"""
        return self._session

    def new_session(self) -> CopilotSession:
        """Create a new session (resets X-Initiator tracking)"""
        self._session = CopilotSession()
        return self._session

    def _ensure_token_dir(self) -> None:
        """Ensure token directory exists"""
        self.token_dir.mkdir(parents=True, exist_ok=True)

    def load_token(self) -> Optional[CopilotToken]:
        """Load stored token from disk"""
        if self._token is not None:
            return self._token

        if not self.token_file.exists():
            return None

        try:
            with open(self.token_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._token = CopilotToken.from_dict(data)
                self._github_token = data.get("github_token")
                return self._token
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            return None

    def save_token(self, token: CopilotToken) -> None:
        """Save token to disk"""
        self._ensure_token_dir()
        self._token = token

        data = token.to_dict()
        if self._github_token:
            data["github_token"] = self._github_token

        with open(self.token_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def clear_token(self) -> None:
        """Clear stored token"""
        self._token = None
        self._github_token = None
        if self.token_file.exists():
            self.token_file.unlink()

    async def get_device_code(self) -> DeviceCodeResponse:
        """Start OAuth Device Code flow

        Returns:
            DeviceCodeResponse with user_code and verification_uri
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                GITHUB_DEVICE_CODE_URL,
                data={
                    "client_id": GITHUB_CLIENT_ID,
                    "scope": "read:user",
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            return DeviceCodeResponse(
                device_code=data["device_code"],
                user_code=data["user_code"],
                verification_uri=data["verification_uri"],
                expires_in=data["expires_in"],
                interval=data["interval"],
            )

    async def poll_for_token(
        self,
        device_code: str,
        interval: int = 5,
        timeout: int = 300,
    ) -> str:
        """Poll for OAuth access token after user authorization

        Args:
            device_code: Device code from get_device_code()
            interval: Polling interval in seconds
            timeout: Maximum time to wait in seconds

        Returns:
            GitHub OAuth access token

        Raises:
            TimeoutError: If user doesn't authorize within timeout
            httpx.HTTPStatusError: If authorization fails
        """
        start_time = time.time()

        async with httpx.AsyncClient() as client:
            while time.time() - start_time < timeout:
                response = await client.post(
                    GITHUB_ACCESS_TOKEN_URL,
                    data={
                        "client_id": GITHUB_CLIENT_ID,
                        "device_code": device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                    headers={"Accept": "application/json"},
                )

                data = response.json()

                if "access_token" in data:
                    self._github_token = data["access_token"]
                    return data["access_token"]

                error = data.get("error")
                if error == "authorization_pending":
                    # User hasn't authorized yet, continue polling
                    await self._async_sleep(interval)
                elif error == "slow_down":
                    # Need to slow down polling
                    interval += 5
                    await self._async_sleep(interval)
                elif error == "expired_token":
                    raise TimeoutError("Device code expired. Please try again.")
                elif error == "access_denied":
                    raise PermissionError("User denied authorization.")
                else:
                    raise RuntimeError(
                        f"OAuth error: {error} - {data.get('error_description', '')}"
                    )

        raise TimeoutError("Authorization timed out. Please try again.")

    async def _async_sleep(self, seconds: int) -> None:
        """Async sleep helper"""
        import asyncio

        await asyncio.sleep(seconds)

    async def get_copilot_token(self, github_token: Optional[str] = None) -> CopilotToken:
        """Exchange GitHub token for Copilot API token

        Args:
            github_token: GitHub OAuth token (uses stored token if not provided)

        Returns:
            CopilotToken for API access
        """
        token = github_token or self._github_token
        if not token:
            raise ValueError("No GitHub token available. Please authenticate first.")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                COPILOT_TOKEN_URL,
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/json",
                    "Editor-Version": EDITOR_VERSION,
                    "Editor-Plugin-Version": EDITOR_PLUGIN_VERSION,
                    "User-Agent": USER_AGENT,
                },
            )
            response.raise_for_status()
            data = response.json()

            copilot_token = CopilotToken(
                token=data["token"],
                expires_at=data["expires_at"],
                github_token=token,
            )

            # Save the token for future use
            self.save_token(copilot_token)

            return copilot_token

    async def ensure_valid_token(self) -> CopilotToken:
        """Ensure we have a valid Copilot token, refreshing if needed

        Returns:
            Valid CopilotToken
        """
        # Try to load existing token
        token = self.load_token()

        if token and not token.is_expired:
            return token

        # Token expired or doesn't exist - need to refresh
        if token and token.github_token:
            # Try to get new Copilot token with stored GitHub token
            try:
                return await self.get_copilot_token(token.github_token)
            except httpx.HTTPStatusError:
                # GitHub token might be invalid, need full re-auth
                pass

        # No valid token, need full authentication
        raise ValueError("No valid Copilot token. Please run 'llc auth copilot' to authenticate.")

    async def authenticate(self, callback: Optional[Any] = None) -> CopilotToken:
        """Full authentication flow

        Args:
            callback: Optional callback for status updates
                     callback(status: str, data: dict)

        Returns:
            CopilotToken after successful authentication
        """
        # Step 1: Get device code
        if callback:
            callback("device_code", {})
        device_code_response = await self.get_device_code()

        # Step 2: Show user instructions
        if callback:
            callback(
                "waiting_for_user",
                {
                    "user_code": device_code_response.user_code,
                    "verification_uri": device_code_response.verification_uri,
                },
            )
        else:
            print(f"\n🔐 GitHub Copilot Authentication")
            print(f"   1. Open: {device_code_response.verification_uri}")
            print(f"   2. Enter code: {device_code_response.user_code}")
            print(f"\n   Waiting for authorization...")

        # Auto-open browser if enabled
        if self.auto_open_browser:
            try:
                webbrowser.open(device_code_response.verification_uri)
            except Exception:
                pass

        # Step 3: Poll for GitHub token
        github_token = await self.poll_for_token(
            device_code_response.device_code,
            interval=device_code_response.interval,
        )

        if callback:
            callback("github_token_received", {})
        else:
            print("   ✓ GitHub authorization successful")

        # Step 4: Get Copilot token
        copilot_token = await self.get_copilot_token(github_token)

        if callback:
            callback("copilot_token_received", {})
        else:
            print("   ✓ Copilot token obtained")
            print(f"\n✅ Authentication successful! Token saved to {self.token_file}")

        return copilot_token

    def get_api_headers(self, include_initiator: bool = True) -> dict[str, str]:
        """Get headers for Copilot API requests

        Args:
            include_initiator: Whether to include X-Initiator header

        Returns:
            Dictionary of headers for API requests
        """
        token = self.load_token()
        if not token:
            raise ValueError("No Copilot token available. Please authenticate first.")

        headers = {
            "Authorization": f"Bearer {token.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Editor-Version": EDITOR_VERSION,
            "Editor-Plugin-Version": EDITOR_PLUGIN_VERSION,
            "Copilot-Integration-Id": COPILOT_INTEGRATION_ID,
            "User-Agent": USER_AGENT,
            "Openai-Intent": "conversation-panel",  # Required for chat
        }

        if include_initiator:
            headers["X-Initiator"] = self._session.get_initiator()

        return headers

    @property
    def chat_endpoint(self) -> str:
        """Get the Copilot chat completions endpoint"""
        return COPILOT_CHAT_URL

    @property
    def is_authenticated(self) -> bool:
        """Check if we have a stored token (may be expired)"""
        return self.token_file.exists()

    @property
    def has_valid_token(self) -> bool:
        """Check if we have a valid (non-expired) token"""
        token = self.load_token()
        return token is not None and not token.is_expired
