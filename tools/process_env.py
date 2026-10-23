"""The environment a child process is allowed to inherit.

Two tools ran subprocesses with hand-built environments: the sandbox
(``tool_runtime``) and the test runner (``test_fix``). Both kept the same
allowlist and the same five defaults, in two copies that could drift apart - and
an allowlist that drifts is a leak: the day one copy adds ``*_TOKEN`` the other
one still passes it to a child.

Rules:

* only the variables a program needs to start, find its interpreter, and write
  to its own temporary directory are passed through;
* everything else - API keys, cloud credentials, user configuration - is
  dropped, whatever its name;
* the locale and unbuffered-output defaults are set explicitly so output is
  readable and complete on every platform.

``extra`` exists for the rare program that needs one more variable; it is
explicit at the call site, which is the point.
"""
from __future__ import annotations

import os
from typing import Iterable, Mapping

#: Variables a child process may inherit. Nothing credential-shaped belongs here.
ENV_ALLOWLIST = (
    "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
    "TMPDIR", "PATHEXT", "COMSPEC", "NUMBER_OF_PROCESSORS", "APPDATA",
    "LOCALAPPDATA", "LANG", "LC_ALL",
)

#: Fixed values, applied after the inherited ones.
ENV_DEFAULTS = {
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUNBUFFERED": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
}


def clean_environment(
    *,
    extra: Mapping[str, str] | None = None,
    allow: Iterable[str] = (),
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """A minimal, predictable environment for a child process."""
    environ = os.environ if source is None else source
    names = tuple(ENV_ALLOWLIST) + tuple(allow)
    environment = {key: environ[key] for key in names if key in environ}
    environment.setdefault("LANG", "C.UTF-8")
    environment.setdefault("LC_ALL", "C.UTF-8")
    environment.update(ENV_DEFAULTS)
    if extra:
        environment.update({str(key): str(value) for key, value in extra.items()})
    return environment


__all__ = ["clean_environment", "ENV_ALLOWLIST", "ENV_DEFAULTS"]
