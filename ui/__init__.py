"""Presentation layer: request handling and page rendering only.

Nothing in ``ui`` may be imported by ``app``. If a workflow ever needs to know
what a page looks like, the data it needs belongs in ``app.services.status``.
"""
