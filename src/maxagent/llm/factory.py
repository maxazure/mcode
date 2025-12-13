"""LLM client factory based on provider configuration."""

from __future__ import annotations

from typing import Optional

from maxagent.config.schema import APIProvider, Config
from maxagent.config.schema import PROVIDER_DEFAULTS

from .client import LLMClient, LLMConfig
from .copilot_client import CopilotLLMClient, CopilotLLMConfig


_LITELLM_PROXY_DEFAULTS = {"http://localhost:4000", "http://127.0.0.1:4000"}


def get_model_max_tokens(model: str, config: Config, provider: Optional[str] = None) -> int:
    """Get max_tokens for a specific model.

    Priority:
    1. Provider-specific config (config.model.models["provider/model"].max_tokens)
    2. Model-specific config (config.model.models[model].max_tokens)
    3. Global config default (config.model.max_tokens)

    Args:
        model: Model name
        config: Config object
        provider: Optional provider name (e.g., "github_copilot", "openai", "glm")

    Returns:
        max_tokens value for the model
    """
    # 1. Check provider-specific config
    if provider:
        provider_model_key = f"{provider}/{model}"
        model_config = config.model.models.get(provider_model_key)
        if model_config and model_config.max_tokens is not None:
            return model_config.max_tokens

    # 2. Check model-specific config
    model_config = config.model.models.get(model)
    if model_config and model_config.max_tokens is not None:
        return model_config.max_tokens

    # 3. Global default
    return config.model.max_tokens


def get_model_temperature(model: str, config: Config, provider: Optional[str] = None) -> float:
    """Get temperature for a specific model.

    Priority:
    1. Provider-specific config (config.model.models["provider/model"].temperature)
    2. Model-specific config (config.model.models[model].temperature)
    3. Global config default (config.model.temperature)

    Args:
        model: Model name
        config: Config object
        provider: Optional provider name (e.g., "github_copilot", "openai", "glm")

    Returns:
        temperature value for the model
    """
    # 1. Check provider-specific config
    if provider:
        provider_model_key = f"{provider}/{model}"
        model_config = config.model.models.get(provider_model_key)
        if model_config and model_config.temperature is not None:
            return model_config.temperature

    # 2. Check model-specific config
    model_config = config.model.models.get(model)
    if model_config and model_config.temperature is not None:
        return model_config.temperature

    # 3. Global default
    return config.model.temperature


def _copilot_base_url(config: Config) -> Optional[str]:
    base_url = (config.litellm.base_url or "").rstrip("/")
    if not base_url or base_url in _LITELLM_PROXY_DEFAULTS:
        return None
    return base_url


def create_llm_client(
    config: Config,
    *,
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None,
) -> LLMClient:
    """Create an LLM client based on configured provider.

    - For `github_copilot`, returns `CopilotLLMClient` with device-flow auth.
    - Otherwise returns the standard OpenAI-compatible `LLMClient`.
    """
    provider = config.litellm.provider
    if provider_override:
        try:
            provider = APIProvider(str(provider_override))
        except ValueError:
            provider = APIProvider.CUSTOM
    if isinstance(provider, str):
        try:
            provider = APIProvider(provider)
        except ValueError:
            provider = APIProvider.CUSTOM

    model = model_override or config.model.default

    # If provider is overridden but model wasn't, prefer provider default model
    if provider_override and not model_override:
        defaults = PROVIDER_DEFAULTS.get(provider)
        if defaults and defaults.get("model"):
            model = str(defaults["model"])

    # Best-effort base_url adjustment when provider changes (only when config base_url
    # matches the original provider default or is empty).
    base_url = config.litellm.base_url
    try:
        original_provider = config.litellm.provider
        original_defaults = PROVIDER_DEFAULTS.get(original_provider)
        if provider_override and (
            (not base_url)
            or (original_defaults and base_url == original_defaults.get("base_url"))
        ):
            new_defaults = PROVIDER_DEFAULTS.get(provider)
            if new_defaults and new_defaults.get("base_url"):
                base_url = str(new_defaults["base_url"])
    except Exception:
        pass
    provider_name = provider.value if provider else None

    if provider == APIProvider.GITHUB_COPILOT:
        kwargs = dict(
            model=model,
            temperature=get_model_temperature(model, config, provider_name),
            max_tokens=get_model_max_tokens(model, config, provider_name),
            parallel_tool_calls=config.model.parallel_tool_calls,
        )
        copilot_base_url = _copilot_base_url(config)
        if copilot_base_url:
            kwargs["base_url"] = copilot_base_url
        copilot_config = CopilotLLMConfig(**kwargs)
        return CopilotLLMClient(copilot_config)

    llm_config = LLMConfig(
        base_url=base_url,
        api_key=config.litellm.api_key,
        model=model,
        temperature=get_model_temperature(model, config, provider_name),
        max_tokens=get_model_max_tokens(model, config, provider_name),
        parallel_tool_calls=config.model.parallel_tool_calls,
    )
    return LLMClient(llm_config)
