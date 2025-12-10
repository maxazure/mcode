"""Pytest configuration and fixtures"""

import tempfile
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def project_root(temp_dir: Path):
    """Create a mock project directory structure"""
    # Create basic project structure
    (temp_dir / "src").mkdir()
    (temp_dir / "src" / "main.py").write_text("def hello(): return 'world'")
    (temp_dir / "tests").mkdir()
    (temp_dir / "tests" / "__init__.py").write_text("")
    (temp_dir / "pyproject.toml").write_text(
        """
[project]
name = "test-project"
version = "0.1.0"

[tool.pytest.ini_options]
testpaths = ["tests"]
"""
    )

    yield temp_dir


@pytest.fixture
def clean_env(monkeypatch):
    """Clear API-related environment variables"""
    env_vars = [
        "GLM_API_KEY",
        "ZHIPU_KEY",  # Also clear ZHIPU_KEY
        "OPENAI_API_KEY",
        "LITELLM_API_KEY",
        "LITELLM_BASE_URL",
        "OPENAI_BASE_URL",
        "LLC_MODEL",
        "MAXAGENT_MODEL",
        "LLC_TEMPERATURE",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    yield


@pytest.fixture
def mock_config_data() -> dict[str, Any]:
    """Mock configuration data"""
    return {
        "litellm": {
            "base_url": "http://localhost:4000",
            "api_key": "test-key",
            "provider": "test",
        },
        "model": {
            "default": "test-model",
            "temperature": 0.7,
            "max_tokens": 4096,
        },
        "tools": {
            "enabled": ["read_file", "list_files"],
            "disabled": [],
        },
        "security": {
            "ignore_patterns": [".env"],
            "require_confirmation": ["write_file"],
        },
    }
