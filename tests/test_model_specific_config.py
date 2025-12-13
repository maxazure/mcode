"""Tests for model-specific configuration (max_tokens, context_length, temperature)"""

import pytest
from pathlib import Path

from maxagent.config.schema import Config, ModelConfig, ModelSpecificConfig
from maxagent.config.loader import load_config
from maxagent.utils.context import get_model_context_limit, ContextManager, MODEL_CONTEXT_LIMITS
from maxagent.llm.factory import get_model_max_tokens, get_model_temperature


class TestModelSpecificConfig:
    """Test ModelSpecificConfig schema"""

    def test_model_specific_config_defaults(self):
        """All fields should be None by default"""
        config = ModelSpecificConfig()
        assert config.max_tokens is None
        assert config.context_length is None
        assert config.temperature is None

    def test_model_specific_config_with_values(self):
        """Should accept valid values"""
        config = ModelSpecificConfig(
            max_tokens=8192,
            context_length=128000,
            temperature=0.5,
        )
        assert config.max_tokens == 8192
        assert config.context_length == 128000
        assert config.temperature == 0.5

    def test_model_config_with_models_dict(self):
        """ModelConfig should accept models dict"""
        model_config = ModelConfig(
            default="gpt-4o",
            models={
                "gpt-4o": ModelSpecificConfig(max_tokens=8192, context_length=128000),
                "deepseek-chat": ModelSpecificConfig(max_tokens=4096, context_length=64000),
            },
        )
        assert "gpt-4o" in model_config.models
        assert model_config.models["gpt-4o"].max_tokens == 8192
        assert model_config.models["deepseek-chat"].context_length == 64000

    def test_model_config_context_length_default(self):
        """ModelConfig should have context_length field with default"""
        model_config = ModelConfig()
        assert model_config.context_length == 128000


class TestGetModelContextLimit:
    """Test get_model_context_limit function with config support"""

    def test_without_config_uses_hardcoded(self):
        """Without config, should use hardcoded defaults"""
        limit = get_model_context_limit("gpt-4")
        assert limit == MODEL_CONTEXT_LIMITS["gpt-4"]

    def test_with_config_model_specific(self):
        """With config, should use model-specific value"""
        config = Config(
            model=ModelConfig(
                models={
                    "custom-model": ModelSpecificConfig(context_length=50000),
                }
            )
        )
        limit = get_model_context_limit("custom-model", config)
        assert limit == 50000

    def test_config_overrides_hardcoded(self):
        """Config should override hardcoded defaults"""
        config = Config(
            model=ModelConfig(
                models={
                    "gpt-4": ModelSpecificConfig(context_length=16000),
                }
            )
        )
        limit = get_model_context_limit("gpt-4", config)
        assert limit == 16000
        # Without config, should use hardcoded
        assert get_model_context_limit("gpt-4") == MODEL_CONTEXT_LIMITS["gpt-4"]

    def test_fallback_to_hardcoded_when_not_in_config(self):
        """Should fall back to hardcoded when model not in config"""
        config = Config(
            model=ModelConfig(
                models={
                    "some-other-model": ModelSpecificConfig(context_length=50000),
                }
            )
        )
        limit = get_model_context_limit("gpt-4", config)
        assert limit == MODEL_CONTEXT_LIMITS["gpt-4"]

    def test_fallback_to_global_for_unknown_model(self):
        """Should fall back to global config for unknown model"""
        config = Config(
            model=ModelConfig(
                context_length=100000,
            )
        )
        limit = get_model_context_limit("unknown-model", config)
        assert limit == 100000

    def test_partial_match_still_works(self):
        """Partial matching should still work"""
        # Test that partial matching finds a match (gpt-4 or gpt-4-turbo)
        limit = get_model_context_limit("gpt-4-turbo-preview")
        # Should match something (either gpt-4 or gpt-4-turbo depending on dict order)
        assert limit in [MODEL_CONTEXT_LIMITS["gpt-4"], MODEL_CONTEXT_LIMITS["gpt-4-turbo"]]
        assert limit != MODEL_CONTEXT_LIMITS["default"]

    def test_provider_specific_config(self):
        """Should use provider/model specific config when provider is given"""
        config = Config(
            model=ModelConfig(
                models={
                    "github_copilot/gpt-4o": ModelSpecificConfig(context_length=100000),
                    "openai/gpt-4o": ModelSpecificConfig(context_length=200000),
                    "gpt-4o": ModelSpecificConfig(context_length=128000),
                }
            )
        )
        # With provider, should use provider-specific config
        assert get_model_context_limit("gpt-4o", config, "github_copilot") == 100000
        assert get_model_context_limit("gpt-4o", config, "openai") == 200000
        # Without provider, should use model-specific config
        assert get_model_context_limit("gpt-4o", config) == 128000

    def test_provider_fallback_to_model_config(self):
        """Should fall back to model config when provider config not found"""
        config = Config(
            model=ModelConfig(
                models={
                    "gpt-4o": ModelSpecificConfig(context_length=128000),
                }
            )
        )
        # Provider config not found, should fall back to model config
        assert get_model_context_limit("gpt-4o", config, "github_copilot") == 128000


class TestGetModelMaxTokens:
    """Test get_model_max_tokens function"""

    def test_uses_global_default(self):
        """Should use global default when model not in config"""
        config = Config(
            model=ModelConfig(max_tokens=4096)
        )
        result = get_model_max_tokens("some-model", config)
        assert result == 4096

    def test_uses_model_specific(self):
        """Should use model-specific value when available"""
        config = Config(
            model=ModelConfig(
                max_tokens=4096,
                models={
                    "gpt-4o": ModelSpecificConfig(max_tokens=8192),
                }
            )
        )
        result = get_model_max_tokens("gpt-4o", config)
        assert result == 8192

    def test_falls_back_to_global(self):
        """Should fall back to global when model-specific is None"""
        config = Config(
            model=ModelConfig(
                max_tokens=4096,
                models={
                    "gpt-4o": ModelSpecificConfig(context_length=128000),  # No max_tokens
                }
            )
        )
        result = get_model_max_tokens("gpt-4o", config)
        assert result == 4096

    def test_provider_specific_max_tokens(self):
        """Should use provider/model specific max_tokens"""
        config = Config(
            model=ModelConfig(
                max_tokens=4096,
                models={
                    "github_copilot/gpt-4o": ModelSpecificConfig(max_tokens=4096),
                    "openai/gpt-4o": ModelSpecificConfig(max_tokens=16384),
                    "gpt-4o": ModelSpecificConfig(max_tokens=8192),
                }
            )
        )
        assert get_model_max_tokens("gpt-4o", config, "github_copilot") == 4096
        assert get_model_max_tokens("gpt-4o", config, "openai") == 16384
        assert get_model_max_tokens("gpt-4o", config) == 8192


class TestGetModelTemperature:
    """Test get_model_temperature function"""

    def test_uses_global_default(self):
        """Should use global default when model not in config"""
        config = Config(
            model=ModelConfig(temperature=0.7)
        )
        result = get_model_temperature("some-model", config)
        assert result == 0.7

    def test_uses_model_specific(self):
        """Should use model-specific value when available"""
        config = Config(
            model=ModelConfig(
                temperature=0.7,
                models={
                    "gpt-4o": ModelSpecificConfig(temperature=0.3),
                }
            )
        )
        result = get_model_temperature("gpt-4o", config)
        assert result == 0.3

    def test_provider_specific_temperature(self):
        """Should use provider/model specific temperature"""
        config = Config(
            model=ModelConfig(
                temperature=0.7,
                models={
                    "github_copilot/gpt-4o": ModelSpecificConfig(temperature=0.5),
                    "gpt-4o": ModelSpecificConfig(temperature=0.3),
                }
            )
        )
        assert get_model_temperature("gpt-4o", config, "github_copilot") == 0.5
        assert get_model_temperature("gpt-4o", config) == 0.3


class TestContextManagerWithConfig:
    """Test ContextManager with config support"""

    def test_context_manager_uses_config(self):
        """ContextManager should use config for context limits"""
        config = Config(
            model=ModelConfig(
                models={
                    "custom-model": ModelSpecificConfig(context_length=50000),
                }
            )
        )
        cm = ContextManager(model="custom-model", config=config)
        assert cm._stats.max_tokens == 50000

    def test_set_config_updates_limits(self):
        """set_config should update context limits"""
        config = Config(
            model=ModelConfig(
                models={
                    "glm-4.6": ModelSpecificConfig(context_length=200000),
                }
            )
        )
        cm = ContextManager(model="glm-4.6")
        old_limit = cm._stats.max_tokens

        cm.set_config(config)
        assert cm._stats.max_tokens == 200000
        assert cm._stats.max_tokens != old_limit

    def test_set_model_respects_config(self):
        """set_model should respect existing config"""
        config = Config(
            model=ModelConfig(
                models={
                    "model-a": ModelSpecificConfig(context_length=100000),
                    "model-b": ModelSpecificConfig(context_length=200000),
                }
            )
        )
        cm = ContextManager(model="model-a", config=config)
        assert cm._stats.max_tokens == 100000

        cm.set_model("model-b")
        assert cm._stats.max_tokens == 200000

    def test_context_manager_with_provider(self):
        """ContextManager should use provider-specific config"""
        config = Config(
            model=ModelConfig(
                models={
                    "github_copilot/gpt-4o": ModelSpecificConfig(context_length=100000),
                    "openai/gpt-4o": ModelSpecificConfig(context_length=200000),
                    "gpt-4o": ModelSpecificConfig(context_length=128000),
                }
            )
        )
        # With provider
        cm = ContextManager(model="gpt-4o", config=config, provider="github_copilot")
        assert cm._stats.max_tokens == 100000

        # Change provider
        cm.set_provider("openai")
        assert cm._stats.max_tokens == 200000

        # Without provider
        cm_no_provider = ContextManager(model="gpt-4o", config=config)
        assert cm_no_provider._stats.max_tokens == 128000


class TestLoadConfigWithModels:
    """Test loading config with models dict from YAML"""

    def test_load_models_from_yaml(self, temp_dir, monkeypatch):
        """Should load models dict from YAML config"""
        config_file = temp_dir / ".llc.yaml"
        config_file.write_text("""
model:
  default: gpt-4o
  max_tokens: 4096
  context_length: 128000
  models:
    gpt-4o:
      max_tokens: 8192
      context_length: 128000
    deepseek-chat:
      max_tokens: 4096
      context_length: 64000
      temperature: 0.5
""")
        monkeypatch.setenv("GLM_API_KEY", "test-key")

        config = load_config(
            project_root=temp_dir,
            user_config_path=temp_dir / "nonexistent.yaml",
            project_config_path=config_file,
        )

        assert config.model.default == "gpt-4o"
        assert "gpt-4o" in config.model.models
        assert config.model.models["gpt-4o"].max_tokens == 8192
        assert config.model.models["deepseek-chat"].context_length == 64000
        assert config.model.models["deepseek-chat"].temperature == 0.5
