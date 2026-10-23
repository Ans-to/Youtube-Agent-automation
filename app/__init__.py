"""The local application package (business logic, no HTTP, no HTML).

Layer rules, enforced by ``tools/check_structure.py``:

``app``
    configuration, paths, runtime state, and use-case services.
``app.services``
    one workflow each - the task queue, its worker, the CEO pipeline runner.
``app.infrastructure``
    adapters to the outside world: the local model, FFmpeg, JSON files.
``ui``
    request handling and presentation only. It may import ``app``; nothing in
    ``app`` may import ``ui``.

Top-level scripts (``agent.py``, ``dashboard.py``, ``queue_store.py``,
``app_config.py``) remain the public entry points that launchers and tests call.
They are thin: real behaviour lives in this package.
"""

__all__ = ["errors", "paths", "state"]
