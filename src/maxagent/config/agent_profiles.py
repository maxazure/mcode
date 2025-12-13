"""Load per-agent overrides from user markdown files.

This module supports configuring subagents independently from the main config.
Users can place files under:
  ~/.llc/agents/<agent>.md

File format supports optional YAML front matter followed by markdown body.

Example:

---
model: github_copilot/gpt-4o
# or:
# provider: github_copilot
# model: gpt-4o
---

# Instructions
You are a coding agent...

The body is treated as additional system prompt appended to the built-in prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Tuple

import yaml


@dataclass(frozen=True)
class AgentProfile:
    """Agent-specific overrides."""

    provider: Optional[str] = None
    model: Optional[str] = None
    system_prompt: str = ""


def get_user_agents_dir(home: Optional[Path] = None) -> Path:
    """Return the directory containing agent profile markdown files."""

    base = home or Path.home()
    return base / ".llc" / "agents"


def _parse_front_matter(text: str) -> Tuple[dict[str, Any], str]:
    """Parse YAML front matter.

    Returns:
        (front_matter_dict, body_text)
    """

    raw = (text or "").lstrip("\ufeff")
    if not raw.startswith("---"):
        return {}, text

    lines = raw.splitlines()
    if not lines:
        return {}, text

    # Find closing ---
    end_idx: Optional[int] = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}, text

    fm_text = "\n".join(lines[1:end_idx]).strip()
    body = "\n".join(lines[end_idx + 1 :])

    if not fm_text:
        return {}, body

    try:
        data = yaml.safe_load(fm_text) or {}
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}

    return data, body


def _split_provider_model(value: str) -> Tuple[Optional[str], Optional[str]]:
    value = (value or "").strip()
    if not value:
        return None, None

    if "/" in value:
        provider, model = value.split("/", 1)
        provider = provider.strip() or None
        model = model.strip() or None
        return provider, model

    return None, value


def load_agent_profile(agent_name: str, home: Optional[Path] = None) -> Optional[AgentProfile]:
    """Load agent profile from ~/.llc/agents/<agent_name>.md.

    Args:
        agent_name: Logical agent name (e.g. "coder", "architect", "tester", "shell")
        home: Optional home dir override (useful for tests)

    Returns:
        AgentProfile if found, else None
    """

    name = (agent_name or "").strip()
    if not name:
        return None

    path = get_user_agents_dir(home=home) / f"{name}.md"
    if not path.exists() or not path.is_file():
        return None

    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None

    fm, body = _parse_front_matter(text)

    provider: Optional[str] = None
    model: Optional[str] = None

    # Accept either {model: "provider/model"} or {provider: "...", model: "..."}
    fm_provider = fm.get("provider") if isinstance(fm, dict) else None
    fm_model = fm.get("model") if isinstance(fm, dict) else None

    if isinstance(fm_provider, str) and fm_provider.strip():
        provider = fm_provider.strip()

    if isinstance(fm_model, str) and fm_model.strip():
        raw_model = fm_model.strip()
        if provider is None:
            p, m = _split_provider_model(raw_model)
            provider = p
            model = m
        else:
            # If provider explicitly provided, treat model as pure model name
            model = raw_model

    # Alternative keys for convenience
    if provider is None and isinstance(fm.get("provider_model"), str):
        p, m = _split_provider_model(str(fm.get("provider_model")))
        provider = p
        model = m

    # Body is the system prompt / additional instructions
    system_prompt = ""

    if isinstance(fm.get("system_prompt"), str) and fm.get("system_prompt"):
        system_prompt = str(fm.get("system_prompt"))
    else:
        system_prompt = (body or "").strip()

    if not (provider or model or system_prompt):
        return None

    return AgentProfile(provider=provider, model=model, system_prompt=system_prompt)
