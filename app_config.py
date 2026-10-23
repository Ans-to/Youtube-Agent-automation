"""Centralized, environment-aware configuration for Offline Agent HQ.

Three sources, in increasing priority:

1. ``config.json`` - private, optional, Git-ignored. Missing is valid.
2. ``.env`` beside it - machine-local overrides, also Git-ignored. Real
   environment variables win over it, so a launcher or a service manager can
   still override a stale file.
3. environment variables - an **allowlist**, listed in :data:`ENV_OVERRIDES`.
   Unknown variables are ignored; this is not a general environment-to-config
   merge, and it never becomes one by accident.

Absolute location overrides:

* ``AGENT_HQ_CONFIG`` - use this file instead of ``config.json``;
* ``AGENT_HQ_HOME`` - run against another checkout (see ``app/paths.py``).

Nothing here logs, echoes, or returns a secret. An invalid value raises
:class:`ConfigError` naming the variable and the rule, never the value.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Mapping

class ConfigError(ValueError):
    """Raised when configuration is malformed or an override is invalid."""


#: Root configuration file. Optional: a fresh checkout runs with defaults.
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

#: File the override variables may be read from.
ENV_FILE_NAME = ".env"

#: Variable that points at a different config file entirely.
CONFIG_PATH_ENV = "AGENT_HQ_CONFIG"

#: Sections whose values must be objects when present.
SECTION_NAMES = ("model", "runner", "dashboard", "video_studio")

#: ``KEY=VALUE`` with optional quotes. Anything else is a config error.
_ENV_LINE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$")

#: (variable, section, key, kind). The kind picks the validator below.
ENV_OVERRIDES: tuple[tuple[str, str, str, str], ...] = (
    ("AGENT_HQ_MODEL_ENABLED", "model", "enabled", "bool"),
    ("AGENT_HQ_MODEL_BASE_URL", "model", "base_url", "text"),
    ("AGENT_HQ_MODEL_NAME", "model", "model", "text"),
    ("AGENT_HQ_MODEL_TIMEOUT_SECONDS", "model", "timeout_seconds", "timeout"),
    ("AGENT_HQ_RUNNER_INTERVAL_SECONDS", "runner", "interval_seconds", "interval"),
    ("AGENT_HQ_RUNNER_MAX_TASKS_PER_CYCLE", "runner", "max_tasks_per_cycle", "batch"),
    ("AGENT_HQ_DASHBOARD_HOST", "dashboard", "host", "text"),
    ("AGENT_HQ_DASHBOARD_PORT", "dashboard", "port", "port"),
)

#: Bounds for the integer kinds, so the validator table stays data.
INTEGER_BOUNDS = {
    "timeout": (1, 300),
    "interval": (1, 86400),
    "batch": (1, 20),
    "port": (1, 65535),
}


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


def parse_env_file(text: str, *, source: str = ENV_FILE_NAME) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines. Comments and blank lines are skipped.

    Quotes around a value are removed, because a ``.env`` written by hand or by
    a script commonly has them. A malformed line fails with its line number and
    never with its content.
    """
    values: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Let PowerShell/DOS line endings and a leading "export" through.
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        match = _ENV_LINE.match(line)
        if not match:
            raise ConfigError(f"{source} line {number} is not KEY=VALUE.")
        value = match.group("value").strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[match.group("key")] = value
    return values


def load_env_file(
    path: str | os.PathLike[str] | None = None, *, environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Return the effective mapping: real environment over ``.env`` over nothing.

    A missing or unreadable ``.env`` is not an error - most installations have
    none. A malformed one is, because silently ignoring it would hide the typo
    that made a setting not apply.
    """
    env = dict(os.environ if environ is None else environ)
    source = Path(path) if path is not None else DEFAULT_CONFIG_PATH.parent / ENV_FILE_NAME
    try:
        text = source.read_text(encoding="utf-8")
    except FileNotFoundError:
        return env
    except OSError as exc:
        raise ConfigError(f"Cannot read {source.name} ({type(exc).__name__}).") from exc
    for key, value in parse_env_file(text, source=source.name).items():
        env.setdefault(key, value)
    return env


def _config_path(path, env: Mapping[str, str]) -> Path:
    if path is not None:
        return Path(path)
    override = env.get(CONFIG_PATH_ENV)
    return Path(override).expanduser() if override else DEFAULT_CONFIG_PATH


def _read_config_file(config_path: Path) -> dict:
    try:
        raw = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise ConfigError(
            f"Cannot read configuration file: {config_path.name} ({type(exc).__name__})."
        ) from exc
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"{config_path.name} contains invalid JSON at line {exc.lineno}, column {exc.colno}."
        ) from exc
    if not isinstance(config, dict):
        raise ConfigError(f"{config_path.name} must contain a JSON object.")
    return config


def apply_env_overrides(config: dict, env: Mapping[str, str]) -> dict:
    """Apply the allowlisted variables to a config dict, in place, and return it."""
    for env_name, section, key, kind in ENV_OVERRIDES:
        if env_name not in env:
            continue
        value = str(env[env_name])
        if kind == "bool":
            parsed = _parse_bool(value, env_name)
        elif kind in INTEGER_BOUNDS:
            minimum, maximum = INTEGER_BOUNDS[kind]
            parsed = _parse_int(value, env_name, minimum, maximum)
        else:
            parsed = value.strip()
            if not parsed:
                raise ConfigError(f"{env_name} must not be empty.")
        config.setdefault(section, {})[key] = parsed
    return config


def load_config(
    path: str | os.PathLike[str] | None = None, *, environ: Mapping[str, str] | None = None
) -> dict:
    """Load and validate configuration, then apply supported environment overrides.

    A missing config file is valid and yields an empty object so callers keep
    safe defaults. Invalid JSON, a wrong section type, or a bad override fail
    clearly. The injectable environment mapping keeps tests deterministic; when
    it is omitted, the real environment is read with ``.env`` underneath it.
    """
    # An explicitly supplied mapping means "use exactly this"; tests rely on it
    # and so does any caller that wants a deterministic environment.
    env = dict(environ) if environ is not None else load_env_file()
    config_path = _config_path(path, env)
    config = _read_config_file(config_path)
    for section in SECTION_NAMES:
        if section in config and not isinstance(config[section], dict):
            raise ConfigError(f"Configuration section {section!r} must be an object.")
    return apply_env_overrides(config, env)


__all__ = [
    "ConfigError",
    "load_config",
    "load_env_file",
    "parse_env_file",
    "apply_env_overrides",
    "ENV_OVERRIDES",
    "DEFAULT_CONFIG_PATH",
    "ENV_FILE_NAME",
    "CONFIG_PATH_ENV",
]
