"""Centralized, environment-aware configuration for Offline Agent HQ.

Local config.json remains private and optional. Environment variables override
only explicitly supported settings; secrets and user data are never logged.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping


class ConfigError(ValueError):
    """Raised when configuration is malformed or an override is invalid."""


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
_SECTION_NAMES = ("model", "runner", "dashboard", "video_studio")


def _parse_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be true/false (or 1/0).")


def _parse_int(value: str, name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value.strip())
    except (AttributeError, ValueError) as exc:
        raise ConfigError(f"{name} must be an integer.") from exc
    if not minimum <= parsed <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}.")
    return parsed


def load_config(path: str | os.PathLike[str] | None = None, *, environ: Mapping[str, str] | None = None) -> dict:
    """Load and validate configuration, then apply supported environment overrides.

    A missing config.json is valid and yields an empty object so callers retain
    safe defaults. Invalid JSON or section types fail clearly. The injectable
    environment mapping keeps tests deterministic.
    """
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    env = os.environ if environ is None else environ
    try:
        raw = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        config: dict = {}
    except OSError as exc:
        raise ConfigError(f"Cannot read configuration file: {config_path.name} ({type(exc).__name__}).") from exc
    else:
        try:
            config = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{config_path.name} contains invalid JSON at line {exc.lineno}, column {exc.colno}.") from exc
        if not isinstance(config, dict):
            raise ConfigError(f"{config_path.name} must contain a JSON object.")

    for section in _SECTION_NAMES:
        if section in config and not isinstance(config[section], dict):
            raise ConfigError(f"Configuration section {section!r} must be an object.")

    overrides = (
        ("AGENT_HQ_MODEL_ENABLED", "model", "enabled", "bool"),
        ("AGENT_HQ_MODEL_BASE_URL", "model", "base_url", "text"),
        ("AGENT_HQ_MODEL_NAME", "model", "model", "text"),
        ("AGENT_HQ_MODEL_TIMEOUT_SECONDS", "model", "timeout_seconds", "timeout"),
        ("AGENT_HQ_RUNNER_INTERVAL_SECONDS", "runner", "interval_seconds", "interval"),
        ("AGENT_HQ_RUNNER_MAX_TASKS_PER_CYCLE", "runner", "max_tasks_per_cycle", "batch"),
        ("AGENT_HQ_DASHBOARD_HOST", "dashboard", "host", "text"),
        ("AGENT_HQ_DASHBOARD_PORT", "dashboard", "port", "port"),
    )
    for env_name, section, key, kind in overrides:
        if env_name not in env:
            continue
        value = env[env_name]
        if kind == "bool":
            parsed = _parse_bool(value, env_name)
        elif kind == "timeout":
            parsed = _parse_int(value, env_name, 1, 300)
        elif kind == "interval":
            parsed = _parse_int(value, env_name, 1, 86400)
        elif kind == "batch":
            parsed = _parse_int(value, env_name, 1, 20)
        elif kind == "port":
            parsed = _parse_int(value, env_name, 1, 65535)
        else:
            parsed = value.strip()
            if not parsed:
                raise ConfigError(f"{env_name} must not be empty.")
        config.setdefault(section, {})[key] = parsed
    return config
