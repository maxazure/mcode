"""Configuration loader"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml

from .schema import APIProvider, Config, PROVIDER_DEFAULTS

# Default config file names
USER_CONFIG_DIR = ".llc"
USER_CONFIG_FILE = "config.yaml"
PROJECT_CONFIG_FILE = ".llc.yaml"


def get_user_config_path() -> Path:
    """Get user configuration file path"""
    return Path.home() / USER_CONFIG_DIR / USER_CONFIG_FILE


def get_project_config_path(project_root: Optional[Path] = None) -> Path:
    """Get project configuration file path"""
    root = project_root or Path.cwd()
    return root / PROJECT_CONFIG_FILE


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries"""
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def _apply_env_vars(config_data: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides"""

    # API Provider detection and configuration
    # Priority (implicit): GLM_API_KEY/ZHIPU_KEY > OPENAI_API_KEY > LITELLM_API_KEY > GITHUB_COPILOT
    # Explicit overrides:
    #   - LLC_PROVIDER / MAXAGENT_PROVIDER: force provider
    #   - GITHUB_COPILOT / USE_COPILOT: force Copilot even if other keys exist

    explicit_provider = os.getenv("LLC_PROVIDER") or os.getenv("MAXAGENT_PROVIDER")
    if explicit_provider:
        config_data.setdefault("litellm", {})["provider"] = explicit_provider
        try:
            provider_enum = APIProvider(explicit_provider)
            defaults = PROVIDER_DEFAULTS.get(provider_enum)
            if defaults:
                config_data.setdefault("litellm", {}).setdefault(
                    "base_url", defaults.get("base_url", "")
                )
                config_data.setdefault("model", {}).setdefault(
                    "default", defaults.get("model", "")
                )
        except ValueError:
            pass

    forced_copilot = (
        not explicit_provider and (os.getenv("GITHUB_COPILOT") or os.getenv("USE_COPILOT"))
    )
    if forced_copilot:
        config_data.setdefault("litellm", {})["provider"] = "github_copilot"
        config_data.setdefault("litellm", {}).setdefault(
            "base_url", "https://api.githubcopilot.com"
        )
        if "default" not in config_data.get("model", {}):
            config_data.setdefault("model", {})["default"] = "gpt-4o"
        # Skip implicit priority chain when Copilot is forced.
    else:
        # Implicit priority chain (only used when not forced)
        # Check for GLM API Key first (Zhipu) - support both GLM_API_KEY and ZHIPU_KEY
        if glm_api_key := (os.getenv("GLM_API_KEY") or os.getenv("ZHIPU_KEY")):
            config_data.setdefault("litellm", {})["api_key"] = glm_api_key
            config_data.setdefault("litellm", {})["provider"] = "glm"
            # Set default base URL for GLM if not already set
            if "base_url" not in config_data.get("litellm", {}):
                config_data["litellm"]["base_url"] = "https://open.bigmodel.cn/api/paas/v4"
            # Set default model for GLM if not already set
            if "default" not in config_data.get("model", {}):
                config_data.setdefault("model", {})["default"] = "glm-4.6"

        # Check for OpenAI API Key
        elif openai_api_key := os.getenv("OPENAI_API_KEY"):
            config_data.setdefault("litellm", {})["api_key"] = openai_api_key
            config_data.setdefault("litellm", {})["provider"] = "openai"
            if "base_url" not in config_data.get("litellm", {}):
                config_data["litellm"]["base_url"] = "https://api.openai.com/v1"
            if "default" not in config_data.get("model", {}):
                config_data.setdefault("model", {})["default"] = "gpt-4"

        # Fallback to LITELLM_API_KEY
        elif litellm_api_key := os.getenv("LITELLM_API_KEY"):
            config_data.setdefault("litellm", {})["api_key"] = litellm_api_key
            config_data.setdefault("litellm", {})["provider"] = "litellm"

        # Check for GitHub Copilot (no API key needed, uses OAuth token)
        elif os.getenv("GITHUB_COPILOT") or os.getenv("USE_COPILOT"):
            config_data.setdefault("litellm", {})["provider"] = "github_copilot"
            config_data.setdefault("litellm", {})["base_url"] = "https://api.githubcopilot.com"
            if "default" not in config_data.get("model", {}):
                config_data.setdefault("model", {})["default"] = "gpt-4o"

    # Explicit base URL override (highest priority)
    if base_url := os.getenv("LITELLM_BASE_URL") or os.getenv("OPENAI_BASE_URL"):
        config_data.setdefault("litellm", {})["base_url"] = base_url

    # LLC_MODEL or MAXAGENT_MODEL (explicit model override)
    if model := os.getenv("LLC_MODEL") or os.getenv("MAXAGENT_MODEL"):
        config_data.setdefault("model", {})["default"] = model

    # LLC_TEMPERATURE
    if temp := os.getenv("LLC_TEMPERATURE"):
        try:
            config_data.setdefault("model", {})["temperature"] = float(temp)
        except ValueError:
            pass

    return config_data


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Load a YAML configuration file"""
    if not path.exists():
        return {}

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_dotenv_file(path: Path) -> dict[str, str]:
    """Load key/value pairs from a .env-style file.

    This is a minimal parser supporting lines like:
      KEY=value
      export KEY="value"
    Comments and empty lines are ignored.
    """
    if not path.exists():
        return {}

    env: dict[str, str] = {}
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key:
                env[key] = value
    except Exception:
        return {}

    return env


def load_config(
    project_root: Optional[Path] = None,
    user_config_path: Optional[Path] = None,
    project_config_path: Optional[Path] = None,
) -> Config:
    """
    Load configuration from multiple sources.

    Priority (highest to lowest):
    1. Environment variables
    2. Project config (.llc.yaml)
    3. User config (~/.llc/config.yaml)
    4. Default values

    Args:
        project_root: Project root directory (default: cwd)
        user_config_path: Custom user config path
        project_config_path: Custom project config path

    Returns:
        Merged Config object
    """
    config_data: dict[str, Any] = {}

    # Load .env in project root (if present) to populate os.environ for overrides.
    # Does not override already exported environment variables.
    root = project_root or Path.cwd()
    dotenv_path = root / ".env"
    dotenv_vars = _load_dotenv_file(dotenv_path)
    for k, v in dotenv_vars.items():
        os.environ.setdefault(k, v)

    # Load user config
    user_path = user_config_path or get_user_config_path()
    user_data = _load_yaml_file(user_path)
    if user_data:
        config_data = _deep_merge(config_data, user_data)

    # Load project config
    project_path = project_config_path or get_project_config_path(project_root)
    project_data = _load_yaml_file(project_path)
    if project_data:
        config_data = _deep_merge(config_data, project_data)

    # Apply environment variables
    config_data = _apply_env_vars(config_data)

    return Config(**config_data)


def save_config(config: Config, path: Path) -> None:
    """Save configuration to file"""
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict, excluding defaults
    data = config.model_dump(exclude_defaults=True)

    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)


def init_user_config() -> Path:
    """Initialize user configuration file with defaults"""
    config_path = get_user_config_path()

    if config_path.exists():
        return config_path

    # Create default config
    default_config = """# MaxAgent Configuration
# See documentation for all available options

# API Configuration
# Supported providers: litellm, openai, glm, custom
litellm:
  provider: "glm"  # or "openai", "litellm", "custom"
  base_url: "https://open.bigmodel.cn/api/paas/v4"
  api_key: ""  # Or set GLM_API_KEY / OPENAI_API_KEY environment variable

# Model Configuration
model:
  default: "glm-4.6"  # Default model to use
  thinking_model: "glm-4.6"  # Thinking 也固定使用 glm-4.6
  thinking_strategy: "auto"  # auto, enabled, disabled - auto decides based on question complexity
  show_thinking: true  # Show thinking process in output
  temperature: 0.7
  max_tokens: 4096

# Tools Configuration
tools:
  enabled:
    - read_file
    - list_files
    - search_code
    - write_file
    - run_command
    - grep
    - glob
    - find_files
    - git_status
    - git_diff
    - git_log
    - git_branch
    - webfetch
  disabled: []

# Security Configuration
security:
  ignore_patterns:
    - ".env"
    - ".env.*"
    - "*.pem"
    - "*.key"
  require_confirmation:
    - write_file
    - run_command

# Instructions Configuration (like AGENTS.md or CLAUDE.md)
instructions:
  filename: "MAXAGENT.md"  # Primary instruction file name
  alternative_names:
    - "AGENTS.md"
    - "CLAUDE.md"
    - ".maxagent.md"
  global_file: "~/.config/maxagent/MAXAGENT.md"  # Global instruction file
  additional_files: []  # Additional instruction files (supports glob)
  auto_discover: true  # Auto-discover instruction files in parent directories

# Environment Variables:
# - GLM_API_KEY: Zhipu GLM API key (auto-configures provider)
# - OPENAI_API_KEY: OpenAI API key (auto-configures provider)
# - LITELLM_API_KEY: LiteLLM proxy API key
# - LITELLM_BASE_URL: Override API base URL
# - LLC_MODEL: Override default model
# - LLC_TEMPERATURE: Override temperature
"""

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(default_config, encoding="utf-8")

    return config_path
