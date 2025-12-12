#!/usr/bin/env python3
"""
Start a LiteLLM proxy backed by GitHub Copilot.

This script:
1) Writes a LiteLLM proxy config for the Copilot provider.
2) Launches LiteLLM proxy on the given host/port.

On first request, LiteLLM will guide you through GitHub Copilot OAuth
device flow and store the token under:
  ~/.config/litellm/github_copilot/
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple


DEFAULT_COPILOT_MODEL = "github_copilot/gpt-4.1"
DEFAULT_MODEL_NAME = "copilot-gpt-4.1"
DEFAULT_PORT = 4000
DEFAULT_HOST = "127.0.0.1"
DEFAULT_EDITOR_VERSION = "vscode/1.85.1"
DEFAULT_INTEGRATION_ID = "vscode-chat"


def _yaml_quote(value: str) -> str:
    # JSON string literals are valid YAML scalars.
    return json.dumps(value, ensure_ascii=False)


def build_litellm_config(
    copilot_model: str,
    model_name: str,
    extra_headers: Dict[str, str],
    master_key: str | None = None,
) -> str:
    lines: List[str] = []
    lines.append("model_list:")
    lines.append(f"  - model_name: {model_name}")
    lines.append("    litellm_params:")
    lines.append(f"      model: {copilot_model}")
    if extra_headers:
        lines.append("      extra_headers:")
        for k, v in extra_headers.items():
            lines.append(f"        {k}: {_yaml_quote(v)}")
    if master_key:
        lines.append("general_settings:")
        lines.append(f"  master_key: {_yaml_quote(master_key)}")
    lines.append("")
    return "\n".join(lines)


def parse_extra_headers(
    editor_version: str,
    integration_id: str,
    extra_header_args: List[str],
) -> Dict[str, str]:
    headers: Dict[str, str] = {
        "editor-version": editor_version,
        "Copilot-Integration-Id": integration_id,
    }
    for item in extra_header_args:
        if "=" not in item:
            raise ValueError(f"Invalid --extra-header {item!r}, expected KEY=VALUE")
        k, v = item.split("=", 1)
        headers[k.strip()] = v.strip()
    return headers


def find_litellm_cmd() -> List[str]:
    exe = shutil.which("litellm")
    if exe:
        return [exe]
    return [sys.executable, "-m", "litellm"]


def detect_proxy_subcommand(base_cmd: List[str]) -> bool:
    try:
        proc = subprocess.run(
            base_cmd + ["--help"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    help_text = (proc.stdout or "") + (proc.stderr or "")
    # Heuristic: newer LiteLLM exposes a "proxy" subcommand.
    return "proxy" in help_text and "proxy --config" in help_text


def ensure_config_file(config_path: Path, content: str, force: bool) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists() and not force:
        return
    config_path.write_text(content, encoding="utf-8")


def run_proxy(
    base_cmd: List[str],
    config_path: Path,
    host: str,
    port: int,
    model_name: str,
) -> int:
    use_proxy_subcmd = detect_proxy_subcommand(base_cmd)
    cmd: List[str] = base_cmd[:]
    if use_proxy_subcmd:
        cmd += ["proxy"]
    cmd += ["--config", str(config_path), "--host", host, "--port", str(port)]

    print("Starting LiteLLM proxy:")
    print("  " + " ".join(cmd))
    print("")
    print(f"Proxy URL: http://{host}:{port}")
    print("Model name for MaxAgent:", model_name)
    print("")
    print("If this is your first Copilot use, you'll be prompted to login.")
    print("")
    return subprocess.call(cmd)


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Start LiteLLM proxy using GitHub Copilot (default gpt-4.1)."
    )
    p.add_argument("--host", default=DEFAULT_HOST, help="Proxy bind host")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="Proxy port")
    p.add_argument(
        "--copilot-model",
        default=DEFAULT_COPILOT_MODEL,
        help="LiteLLM Copilot model string, e.g. github_copilot/gpt-4.1",
    )
    p.add_argument(
        "--model-name",
        default=DEFAULT_MODEL_NAME,
        help="Model alias exposed by LiteLLM proxy",
    )
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to write config (default: ~/.config/maxagent/litellm_copilot.yaml)",
    )
    p.add_argument("--force", action="store_true", help="Overwrite existing config")
    p.add_argument(
        "--master-key",
        default=os.getenv("LITELLM_MASTER_KEY", ""),
        help="Optional LiteLLM proxy master key (also set LITELLM_API_KEY for agent)",
    )
    p.add_argument(
        "--editor-version",
        default=DEFAULT_EDITOR_VERSION,
        help="Copilot header Editor-Version",
    )
    p.add_argument(
        "--integration-id",
        default=DEFAULT_INTEGRATION_ID,
        help="Copilot header Copilot-Integration-Id",
    )
    p.add_argument(
        "--extra-header",
        action="append",
        default=[],
        help="Additional Copilot header KEY=VALUE (repeatable)",
    )
    p.add_argument(
        "--config-only",
        action="store_true",
        help="Only write config, do not start proxy",
    )
    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    config_path = args.config or (
        Path.home() / ".config" / "maxagent" / "litellm_copilot.yaml"
    )

    try:
        headers = parse_extra_headers(
            args.editor_version, args.integration_id, args.extra_header
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    content = build_litellm_config(
        copilot_model=args.copilot_model,
        model_name=args.model_name,
        extra_headers=headers,
        master_key=args.master_key or None,
    )
    ensure_config_file(config_path, content, args.force)
    print("LiteLLM config written to:", config_path)

    if args.config_only:
        return 0

    base_cmd = find_litellm_cmd()
    # Quick check to give a friendly error early.
    try:
        version_proc = subprocess.run(
            base_cmd + ["--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        version_proc = None

    if version_proc is None or version_proc.returncode != 0:
        text = ""
        if version_proc is not None:
            text = (version_proc.stdout or "") + (version_proc.stderr or "")
        if "No module named litellm" in text or "ModuleNotFoundError" in text:
            print(
                "LiteLLM is not installed in this Python environment.\n"
                "Install it with: pip install 'litellm>=1.40'\n",
                file=sys.stderr,
            )
            return 1

    return run_proxy(
        base_cmd,
        config_path,
        args.host,
        args.port,
        args.model_name,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
