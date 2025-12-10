"""LLM Client for interacting with LiteLLM/OpenAI compatible APIs"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

import httpx

from .models import ChatResponse, Message, StreamDelta


@dataclass
class LLMConfig:
    """LLM client configuration"""

    base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    api_key: str = ""
    model: str = "glm-4-flash"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: float = 120.0
    extra_headers: dict[str, str] = field(default_factory=dict)
    # API endpoint path (auto-detected based on base_url)
    chat_endpoint: str = ""
    # Thinking model configuration
    thinking_model: str = "glm-z1-flash"
    # Whether to parse and extract thinking content
    parse_thinking: bool = True


class LLMClient:
    """Async LLM client with streaming support"""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._chat_endpoint = self._determine_chat_endpoint()

    def _determine_chat_endpoint(self) -> str:
        """Determine the chat completions endpoint based on base_url"""
        # If explicitly set, use it
        if self.config.chat_endpoint:
            return self.config.chat_endpoint

        base = self.config.base_url.rstrip("/")

        # GLM API: base_url already contains /v4
        if "bigmodel.cn" in base or base.endswith("/v4"):
            return "/chat/completions"

        # Standard OpenAI-compatible API
        return "/v1/chat/completions"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            headers = {
                "Content-Type": "application/json",
                **self.config.extra_headers,
            }
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.config.base_url.rstrip("/"),
                headers=headers,
                timeout=httpx.Timeout(self.config.timeout),
            )
        return self._client

    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[dict[str, Any]]] = None,
        stream: bool = False,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> ChatResponse | AsyncIterator[StreamDelta]:
        """
        Send chat completion request.

        Args:
            messages: List of messages
            tools: List of tool definitions (OpenAI format)
            stream: Whether to stream the response
            model: Override default model
            temperature: Override default temperature
            max_tokens: Override default max_tokens
            **kwargs: Additional parameters to pass to the API

        Returns:
            ChatResponse for non-streaming, AsyncIterator[StreamDelta] for streaming
        """
        payload = self._build_payload(
            messages=messages,
            tools=tools,
            stream=stream,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        if stream:
            return self._stream_response(payload)
        else:
            return await self._send_request(payload)

    def _build_payload(
        self,
        messages: list[Message],
        tools: Optional[list[dict[str, Any]]] = None,
        stream: bool = False,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build request payload"""
        payload: dict[str, Any] = {
            "model": model or self.config.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "stream": stream,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = kwargs.pop("tool_choice", "auto")

        payload.update(kwargs)
        return payload

    async def _send_request(self, payload: dict[str, Any]) -> ChatResponse:
        """Send non-streaming request"""
        client = await self._get_client()
        response = await client.post(self._chat_endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
        chat_response = ChatResponse.from_api_response(data)

        # Process thinking content if enabled
        if self.config.parse_thinking:
            chat_response = self._process_thinking_response(chat_response)

        return chat_response

    def _process_thinking_response(self, response: ChatResponse) -> ChatResponse:
        """Process and extract thinking content from response

        Handles:
        - GLM: <think>...</think> tags in content
        - DeepSeek: reasoning_content field (already extracted in from_api_response)
        """
        # Handle GLM thinking tags
        if response.content and "<think>" in response.content:
            from maxagent.utils.thinking import parse_thinking

            result = parse_thinking(response.content)
            response.thinking_content = result.thinking
            response.content = result.response

        # DeepSeek reasoning_content is already extracted in from_api_response
        # If we have reasoning_content but no thinking_content, copy it
        if response.reasoning_content and not response.thinking_content:
            response.thinking_content = response.reasoning_content

        return response

    async def _stream_response(self, payload: dict[str, Any]) -> AsyncIterator[StreamDelta]:
        """Stream response chunks"""
        client = await self._get_client()

        async with client.stream("POST", self._chat_endpoint, json=payload) as response:
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

    def _parse_stream_delta(self, data: dict[str, Any]) -> Optional[StreamDelta]:
        """Parse streaming response delta"""
        choices = data.get("choices", [])
        if not choices:
            return None

        choice = choices[0]
        delta = choice.get("delta", {})
        finish_reason = choice.get("finish_reason")

        return StreamDelta(
            content=delta.get("content"),
            tool_calls=delta.get("tool_calls"),
            finish_reason=finish_reason,
            # DeepSeek reasoning_content for streaming
            reasoning_content=delta.get("reasoning_content"),
        )

    async def close(self) -> None:
        """Close the HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "LLMClient":
        """Async context manager entry"""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit"""
        await self.close()
