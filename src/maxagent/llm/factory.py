"""LLM client factory based on provider configuration."""

from __future__ import annotations

from typing import Optional

from maxagent.config.schema import APIProvider, Config

from .client import LLMClient, LLMConfig
from .copilot_client import CopilotLLMClient, CopilotLLMConfig


_LITELLM_PROXY_DEFAULTS = {"http://localhost:4000", "http://127.0.0.1:4000"}


def _copilot_base_url(config: Config) -> Optional[str]:
    base_url = (config.litellm.base_url or "").rstrip("/")
    if not base_url or base_url in _LITELLM_PROXY_DEFAULTS:
        return None
    return base_url


def create_llm_client(config: Config) -> LLMClient:
    """Create an LLM client based on configured provider.

    - For `github_copilot`, returns `CopilotLLMClient` with device-flow auth.
    - Otherwise returns the standard OpenAI-compatible `LLMClient`.
    """
    provider = config.litellm.provider
    if isinstance(provider, str):
        try:
            provider = APIProvider(provider)
        except ValueError:
            provider = APIProvider.CUSTOM

    if provider == APIProvider.GITHUB_COPILOT:
        kwargs = dict(
            model=config.model.default,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens,
        )
        base_url = _copilot_base_url(config)
        if base_url:
            kwargs["base_url"] = base_url
        copilot_config = CopilotLLMConfig(**kwargs)
        return CopilotLLMClient(copilot_config)

    llm_config = LLMConfig(
        base_url=config.litellm.base_url,
        api_key=config.litellm.api_key,
        model=config.model.default,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens,
    )
    return LLMClient(llm_config)

