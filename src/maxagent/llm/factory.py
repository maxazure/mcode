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


def get_provider_for_model(model: str, config: Config) -> Optional[APIProvider]:
    """Get the provider for a given model by checking config.model.models.

    This function dynamically reads the model-to-provider mapping from the
    configuration file (e.g., ~/.llc/config.yaml). It looks for keys in the
    format "provider/model" (e.g., "github_copilot/gpt-4.1") and extracts
    the provider.

    Args:
        model: Model name (e.g., "gpt-4.1", "glm-4.6")
        config: Config object containing model.models mapping

    Returns:
        The first provider that supports this model, or None if not found
    """
    # Search for "provider/model" keys in config.model.models
    for key in config.model.models.keys():
        if "/" in key:
            provider_name, model_name = key.split("/", 1)
            if model_name == model:
                try:
                    return APIProvider(provider_name)
                except ValueError:
                    # Unknown provider, continue searching
                    continue

    # Fallback: check if model name starts with known provider prefixes
    model_lower = model.lower()
    if model_lower.startswith("glm"):
        return APIProvider.GLM
    elif model_lower.startswith(("gpt", "o1", "o3")):
        # GPT models - prefer GitHub Copilot if available
        return APIProvider.GITHUB_COPILOT
    elif model_lower.startswith("claude"):
        return APIProvider.GITHUB_COPILOT

    return None


def create_llm_client(
    config: Config,
    *,
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None,
) -> LLMClient:
    """Create an LLM client based on configured provider.

    - For `github_copilot`, returns `CopilotLLMClient` with device-flow auth.
    - Otherwise returns the standard OpenAI-compatible `LLMClient`.

    When model_override is specified without provider_override, the function will
    automatically select the first provider that supports the model based on
    MODEL_PROVIDER_MAP.
    """
    provider = config.litellm.provider
    model = model_override or config.model.default

    # Auto-select provider based on model if no explicit provider override
    if model_override and not provider_override:
        # Try to find a provider that supports this model from config
        auto_provider = get_provider_for_model(model_override, config)
        if auto_provider:
            provider = auto_provider

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

    # If provider is overridden but model wasn't, prefer provider default model
    if provider_override and not model_override:
        defaults = PROVIDER_DEFAULTS.get(provider)
        if defaults and defaults.get("model"):
            model = str(defaults["model"])

    # Best-effort base_url adjustment when provider changes (only when config base_url
    # matches the original provider default or is empty).
    base_url = config.litellm.base_url
    original_provider = config.litellm.provider
    provider_changed = provider != original_provider
    try:
        original_defaults = PROVIDER_DEFAULTS.get(original_provider)
        # Adjust base_url if:
        # 1. Provider changed (either via override or auto-selection)
        # 2. And current base_url is empty or matches original provider's default
        if provider_changed and (
            (not base_url) or (original_defaults and base_url == original_defaults.get("base_url"))
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
        # Only use custom base_url if:
        # 1. Provider didn't change (user configured Copilot with custom URL)
        # 2. Or if base_url was explicitly set to a Copilot-like URL
        if not provider_changed:
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
