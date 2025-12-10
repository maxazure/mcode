"""GitHub Copilot LLM Client"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Optional

import httpx

from .client import LLMClient, LLMConfig
from .models import ChatResponse, Message, StreamDelta
from maxagent.auth.github_copilot import (
    GitHubCopilotAuth,
    CopilotSession,
    COPILOT_CHAT_URL,
    EDITOR_VERSION,
    EDITOR_PLUGIN_VERSION,
    COPILOT_INTEGRATION_ID,
    USER_AGENT,
)


class CopilotLLMConfig(LLMConfig):
    """Configuration for GitHub Copilot LLM client"""

    def __init__(self, **kwargs: Any) -> None:
        # Set Copilot-specific defaults
        kwargs.setdefault("base_url", "https://api.githubcopilot.com")
        kwargs.setdefault("model", "gpt-4o")
        kwargs.setdefault("chat_endpoint", "/chat/completions")
        super().__init__(**kwargs)


class CopilotLLMClient(LLMClient):
    """LLM client specialized for GitHub Copilot API

    Features:
    - Automatic OAuth token management
    - X-Initiator header for premium request optimization
    - Copilot-specific headers
    """

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        auth: Optional[GitHubCopilotAuth] = None,
    ) -> None:
        config = config or CopilotLLMConfig()
        super().__init__(config)
        self._auth = auth or GitHubCopilotAuth()
        self._session: Optional[CopilotSession] = None

    @property
    def auth(self) -> GitHubCopilotAuth:
        """Get the auth handler"""
        return self._auth

    @property
    def session(self) -> CopilotSession:
        """Get current session"""
        if self._session is None:
            self._session = self._auth.new_session()
        return self._session

    def new_session(self) -> CopilotSession:
        """Start a new session (resets X-Initiator tracking)"""
        self._session = self._auth.new_session()
        return self._session

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with Copilot-specific headers"""
        if self._client is None or self._client.is_closed:
            # Ensure we have a valid token
            token = await self._auth.ensure_valid_token()

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {token.token}",
                "Editor-Version": EDITOR_VERSION,
                "Editor-Plugin-Version": EDITOR_PLUGIN_VERSION,
                "Copilot-Integration-Id": COPILOT_INTEGRATION_ID,
                "User-Agent": USER_AGENT,
                "Openai-Intent": "conversation-panel",
                **self.config.extra_headers,
            }

            self._client = httpx.AsyncClient(
                base_url=self.config.base_url.rstrip("/"),
                headers=headers,
                timeout=httpx.Timeout(self.config.timeout),
            )
        return self._client

    async def _send_request(self, payload: dict[str, Any]) -> ChatResponse:
        """Send non-streaming request with X-Initiator header"""
        client = await self._get_client()

        # Add X-Initiator header for this request
        headers = {"X-Initiator": self.session.get_initiator()}

        response = await client.post(
            self._chat_endpoint,
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        chat_response = ChatResponse.from_api_response(data)

        # Process thinking content if enabled
        if self.config.parse_thinking:
            chat_response = self._process_thinking_response(chat_response)

        return chat_response

    async def _stream_response(self, payload: dict[str, Any]) -> AsyncIterator[StreamDelta]:
        """Stream response chunks with X-Initiator header"""
        client = await self._get_client()

        # Add X-Initiator header for this request
        headers = {"X-Initiator": self.session.get_initiator()}

        async with client.stream(
            "POST",
            self._chat_endpoint,
            json=payload,
            headers=headers,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = self._parse_stream_delta(data)
                        if delta:
                            yield delta
                    except json.JSONDecodeError:
                        continue

    async def refresh_token_if_needed(self) -> None:
        """Refresh the Copilot token if it's expired or about to expire"""
        token = self._auth.load_token()
        if token is None or token.is_expired:
            await self._auth.ensure_valid_token()
            # Close the existing client so it gets recreated with new token
            await self.close()

    @property
    def is_authenticated(self) -> bool:
        """Check if we have a valid authentication"""
        return self._auth.has_valid_token

    async def authenticate(self, callback: Optional[Any] = None) -> None:
        """Run the full authentication flow"""
        await self._auth.authenticate(callback)
        # Close the existing client so it gets recreated with new token
        await self.close()


def create_copilot_client(
    model: str = "gpt-4o",
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> CopilotLLMClient:
    """Factory function to create a Copilot LLM client

    Args:
        model: Model to use (gpt-4o, claude-3.5-sonnet, etc.)
        temperature: Sampling temperature
        max_tokens: Maximum tokens in response

    Returns:
        Configured CopilotLLMClient
    """
    config = CopilotLLMConfig(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return CopilotLLMClient(config)
