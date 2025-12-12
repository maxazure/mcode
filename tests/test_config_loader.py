"""Tests for configuration loader"""

import os
import pytest
from pathlib import Path

from maxagent.config.loader import (
    load_config,
    _deep_merge,
    _apply_env_vars,
    _load_yaml_file,
    get_user_config_path,
    get_project_config_path,
    save_config,
)
from maxagent.config.schema import Config


class TestDeepMerge:
    """Test deep merge function"""

    def test_merge_simple(self):
        """Test simple merge"""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_merge_nested(self):
        """Test nested merge"""
        base = {"level1": {"a": 1, "b": 2}}
        override = {"level1": {"b": 3, "c": 4}}
        result = _deep_merge(base, override)
        assert result == {"level1": {"a": 1, "b": 3, "c": 4}}

    def test_merge_deep_nested(self):
        """Test deeply nested merge"""
        base = {"l1": {"l2": {"l3": {"a": 1}}}}
        override = {"l1": {"l2": {"l3": {"b": 2}}}}
        result = _deep_merge(base, override)
        assert result == {"l1": {"l2": {"l3": {"a": 1, "b": 2}}}}

    def test_merge_override_non_dict(self):
        """Test override replaces non-dict values"""
        base = {"a": {"b": 1}}
        override = {"a": "string"}
        result = _deep_merge(base, override)
        assert result == {"a": "string"}


class TestApplyEnvVars:
    """Test environment variable application"""

    def test_glm_api_key(self, monkeypatch):
        """Test GLM API key configuration"""
        monkeypatch.setenv("GLM_API_KEY", "test-glm-key")

        config_data = {}
        result = _apply_env_vars(config_data)

        assert result["litellm"]["api_key"] == "test-glm-key"
        assert result["litellm"]["provider"] == "glm"
        assert "bigmodel.cn" in result["litellm"]["base_url"]
        assert result["model"]["default"] == "glm-4.6"

    def test_openai_api_key(self, monkeypatch, clean_env):
        """Test OpenAI API key configuration"""
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

        config_data = {}
        result = _apply_env_vars(config_data)

        assert result["litellm"]["api_key"] == "test-openai-key"
        assert result["litellm"]["provider"] == "openai"
        assert "api.openai.com" in result["litellm"]["base_url"]
        assert result["model"]["default"] == "gpt-4"

    def test_litellm_api_key(self, monkeypatch, clean_env):
        """Test LiteLLM API key configuration"""
        monkeypatch.setenv("LITELLM_API_KEY", "test-litellm-key")

        config_data = {}
        result = _apply_env_vars(config_data)

        assert result["litellm"]["api_key"] == "test-litellm-key"
        assert result["litellm"]["provider"] == "litellm"

    def test_api_key_priority(self, monkeypatch):
        """Test API key priority: GLM > OpenAI > LiteLLM"""
        monkeypatch.setenv("GLM_API_KEY", "glm-key")
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
        monkeypatch.setenv("LITELLM_API_KEY", "litellm-key")

        config_data = {}
        result = _apply_env_vars(config_data)

        # GLM should win
        assert result["litellm"]["api_key"] == "glm-key"
        assert result["litellm"]["provider"] == "glm"

    def test_base_url_override(self, monkeypatch):
        """Test base URL override"""
        monkeypatch.setenv("GLM_API_KEY", "test-key")
        monkeypatch.setenv("LITELLM_BASE_URL", "http://custom.url")

        config_data = {}
        result = _apply_env_vars(config_data)

        assert result["litellm"]["base_url"] == "http://custom.url"

    def test_model_override(self, monkeypatch, clean_env):
        """Test model override"""
        monkeypatch.setenv("LLC_MODEL", "custom-model")

        config_data = {}
        result = _apply_env_vars(config_data)

        assert result["model"]["default"] == "custom-model"

    def test_temperature_override(self, monkeypatch, clean_env):
        """Test temperature override"""
        monkeypatch.setenv("LLC_TEMPERATURE", "0.5")

        config_data = {}
        result = _apply_env_vars(config_data)

        assert result["model"]["temperature"] == 0.5

    def test_invalid_temperature(self, monkeypatch, clean_env):
        """Test invalid temperature is ignored"""
        monkeypatch.setenv("LLC_TEMPERATURE", "invalid")

        config_data = {}
        result = _apply_env_vars(config_data)

        assert "temperature" not in result.get("model", {})


class TestLoadYamlFile:
    """Test YAML file loading"""

    def test_load_existing_file(self, temp_dir):
        """Test loading existing YAML file"""
        yaml_file = temp_dir / "test.yaml"
        yaml_file.write_text(
            """
key1: value1
key2:
  nested: value2
"""
        )

        result = _load_yaml_file(yaml_file)
        assert result == {"key1": "value1", "key2": {"nested": "value2"}}

    def test_load_nonexistent_file(self, temp_dir):
        """Test loading non-existent file returns empty dict"""
        result = _load_yaml_file(temp_dir / "nonexistent.yaml")
        assert result == {}

    def test_load_empty_file(self, temp_dir):
        """Test loading empty file returns empty dict"""
        yaml_file = temp_dir / "empty.yaml"
        yaml_file.write_text("")

        result = _load_yaml_file(yaml_file)
        assert result == {}

    def test_load_invalid_yaml(self, temp_dir):
        """Test loading invalid YAML returns empty dict"""
        yaml_file = temp_dir / "invalid.yaml"
        yaml_file.write_text("not: valid: yaml: [")

        result = _load_yaml_file(yaml_file)
        assert result == {}


class TestLoadConfig:
    """Test config loading"""

    def test_load_default_config(self, clean_env, temp_dir, monkeypatch):
        """Test loading default config when no files exist"""
        monkeypatch.setattr(
            "maxagent.config.loader.get_user_config_path", lambda: temp_dir / "nonexistent.yaml"
        )

        # Set a minimal API key to avoid validation errors
        monkeypatch.setenv("GLM_API_KEY", "test-key")

        config = load_config(
            project_root=temp_dir,
            user_config_path=temp_dir / "user.yaml",
            project_config_path=temp_dir / "project.yaml",
        )

        assert isinstance(config, Config)

    def test_load_dotenv_sets_env_vars(self, clean_env, temp_dir):
        """.env in project root should populate env overrides"""
        (temp_dir / ".env").write_text('GLM_API_KEY="dotenv-key"\n')

        config = load_config(
            project_root=temp_dir,
            user_config_path=temp_dir / "user.yaml",
            project_config_path=temp_dir / "project.yaml",
        )

        assert config.litellm.api_key == "dotenv-key"
        assert config.model.default == "glm-4.6"

    def test_load_dotenv_does_not_override_exported_env(self, clean_env, temp_dir, monkeypatch):
        """.env should not override already-exported environment variables"""
        (temp_dir / ".env").write_text('GLM_API_KEY="dotenv-key"\n')
        monkeypatch.setenv("GLM_API_KEY", "exported-key")

        config = load_config(project_root=temp_dir)

        assert config.litellm.api_key == "exported-key"

    def test_load_user_config(self, clean_env, temp_dir, monkeypatch):
        """Test loading user config"""
        user_config = temp_dir / "user.yaml"
        user_config.write_text(
            """
model:
  temperature: 0.9
"""
        )

        monkeypatch.setenv("GLM_API_KEY", "test-key")

        config = load_config(
            project_root=temp_dir,
            user_config_path=user_config,
            project_config_path=temp_dir / "nonexistent.yaml",
        )

        assert config.model.temperature == 0.9

    def test_load_project_config(self, clean_env, temp_dir, monkeypatch):
        """Test project config overrides user config"""
        user_config = temp_dir / "user.yaml"
        user_config.write_text(
            """
model:
  temperature: 0.9
"""
        )

        project_config = temp_dir / "project.yaml"
        project_config.write_text(
            """
model:
  temperature: 0.3
"""
        )

        monkeypatch.setenv("GLM_API_KEY", "test-key")

        config = load_config(
            project_root=temp_dir,
            user_config_path=user_config,
            project_config_path=project_config,
        )

        # Project config should override user config
        assert config.model.temperature == 0.3


class TestSaveConfig:
    """Test config saving"""

    def test_save_config(self, temp_dir):
        """Test saving config to file"""
        config = Config()
        config_path = temp_dir / "config" / "test.yaml"

        save_config(config, config_path)

        assert config_path.exists()

    def test_save_creates_directory(self, temp_dir):
        """Test save creates parent directory"""
        config = Config()
        config_path = temp_dir / "nested" / "dir" / "config.yaml"

        save_config(config, config_path)

        assert config_path.exists()
        assert config_path.parent.exists()


class TestConfigPaths:
    """Test config path functions"""

    def test_get_user_config_path(self):
        """Test user config path"""
        path = get_user_config_path()
        assert path.name == "config.yaml"
        assert ".llc" in str(path)

    def test_get_project_config_path(self, temp_dir):
        """Test project config path"""
        path = get_project_config_path(temp_dir)
        assert path.name == ".llc.yaml"
        assert temp_dir in path.parents or path.parent == temp_dir
