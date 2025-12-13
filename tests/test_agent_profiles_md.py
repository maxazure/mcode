from __future__ import annotations

from pathlib import Path

import pytest

from maxagent.config.agent_profiles import load_agent_profile
from maxagent.config.schema import APIProvider, Config, LiteLLMConfig, ModelConfig
from maxagent.core.agent import create_agent
from maxagent.llm.client import LLMClient


def _write_agent_md(home: Path, name: str, content: str) -> None:
    agents_dir = home / ".llc" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{name}.md").write_text(content, encoding="utf-8")


def test_load_agent_profile_parses_model_provider_frontmatter(temp_dir: Path):
    _write_agent_md(
        temp_dir,
        "coder",
        """---
model: openai/gpt-4o
---
You are the coder.\n""",
    )

    profile = load_agent_profile("coder", home=temp_dir)
    assert profile is not None
    assert profile.provider == "openai"
    assert profile.model == "gpt-4o"
    assert "You are the coder" in profile.system_prompt


def test_load_agent_profile_parses_separate_provider_and_model(temp_dir: Path):
    _write_agent_md(
        temp_dir,
        "architect",
        """---
provider: github_copilot
model: gpt-4o
---
Architect rules.\n""",
    )

    profile = load_agent_profile("architect", home=temp_dir)
    assert profile is not None
    assert profile.provider == "github_copilot"
    assert profile.model == "gpt-4o"
    assert "Architect rules" in profile.system_prompt


def test_create_agent_uses_profile_model_and_prompt(monkeypatch: pytest.MonkeyPatch, temp_dir: Path):
    _write_agent_md(
        temp_dir,
        "coder",
        """---
model: openai/gpt-4
---
Custom coder instruction: prefer minimal diffs.\n""",
    )

    # Force Path.home() used by loader to point to temp_dir
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    config = Config(
        litellm=LiteLLMConfig(provider=APIProvider.GITHUB_COPILOT, base_url="https://api.githubcopilot.com"),
        model=ModelConfig(default="gpt-4o"),
    )

    agent = create_agent(config=config, project_root=temp_dir, agent_name="coder")

    assert isinstance(agent.llm, LLMClient)
    assert agent.llm.config.model == "gpt-4"
    assert "Custom coder instruction" in agent.agent_config.system_prompt
