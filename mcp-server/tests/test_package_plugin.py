"""Unit test for the plugin packager's file filter (scripts/package_plugin.py).

The packager is a repo-root script with no test suite of its own; this guards
that instrumentation logs (latest_logs/, archived_logs/, any *.log) never leak
into the release zip.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "package_plugin.py"
_spec = importlib.util.spec_from_file_location("package_plugin", _SCRIPT)
assert _spec is not None and _spec.loader is not None
package_plugin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(package_plugin)


def test_included_excludes_logs_and_keeps_source() -> None:
    excluded = [
        Path("latest_logs/x.log"),
        Path("archived_logs/y.log"),
        Path("foo.log"),
    ]
    for rel in excluded:
        assert package_plugin._included(rel) is False, rel

    assert package_plugin._included(Path("operations/load.py")) is True
