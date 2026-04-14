"""Compatibility package for running the backend from the project root.

The backend source code lives under ``backend/app`` but many modules import
from ``app.*`` directly. When running commands like
``uvicorn backend.app.main:app`` from the repository root, Python can import
``backend.app.main`` but cannot resolve the top-level ``app`` package.

This shim exposes ``backend/app`` as the ``app`` package so both of these work:

- ``uvicorn app.main:app --app-dir backend``
- ``uvicorn backend.app.main:app``
"""

from __future__ import annotations

from pathlib import Path

_BACKEND_APP_DIR = Path(__file__).resolve().parent.parent / "backend" / "app"

if not _BACKEND_APP_DIR.exists():
    raise RuntimeError(f"backend app directory not found: {_BACKEND_APP_DIR}")

# Make this package behave like backend/app for submodule imports such as
# ``app.api.router`` and ``app.core.config``.
__path__ = [str(_BACKEND_APP_DIR)]

