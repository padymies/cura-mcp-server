"""Cura plugin registration entrypoint.

Cura calls ``register(app)`` and expects a dict mapping plugin types to objects.
We register an Extension that owns the local server lifecycle.
"""
from __future__ import annotations

try:
    # Cura imports this folder as a package, so the relative import resolves.
    # Guarded so the module can also be imported by tooling/tests outside Cura
    # (mirrors the import guards in CuraMcpPlugin.py / adapters/cura_api.py).
    from .CuraMcpPlugin import CuraMcpPlugin
except ImportError:  # pragma: no cover - only hit when imported without package context
    CuraMcpPlugin = None  # type: ignore[assignment, misc]


def getMetaData() -> dict:
    return {}


def register(app) -> dict:  # noqa: ANN001 - Cura passes its application
    return {"extension": CuraMcpPlugin()}
