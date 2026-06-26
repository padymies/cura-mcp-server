#!/usr/bin/env python3
"""Package the Cura plugin into an installable zip.

Produces ``dist/CuraMcp-<version>.zip`` whose single top-level folder is
``CuraMcp/`` — the exact name Cura needs — so installing is just "extract into the
plugins folder", with no manual rename. Development-only files (tests, pytest.ini,
caches) are excluded.

Usage: python scripts/package_plugin.py [--outdir dist]
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

PLUGIN_DIRNAME = "CuraMcp"  # the folder name Cura imports as a package
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "cura-plugin"

# Paths (relative to cura-plugin/) that must NOT ship in the installable plugin.
EXCLUDE_DIRS = {"tests", "__pycache__", "archived_logs", "latest_logs"}
EXCLUDE_FILES = {"pytest.ini"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".log"}


def _included(rel: Path) -> bool:
    # Skip hidden/cache dirs (.pytest_cache, .ruff_cache, .mypy_cache, .git, ...).
    if any(part.startswith(".") or part in EXCLUDE_DIRS for part in rel.parts):
        return False
    if rel.name in EXCLUDE_FILES:
        return False
    return rel.suffix not in EXCLUDE_SUFFIXES


def _version() -> str:
    meta = json.loads((SRC / "plugin.json").read_text(encoding="utf-8"))
    return str(meta.get("version", "0.0.0"))


def build(outdir: Path) -> Path:
    if not SRC.is_dir():
        raise SystemExit(f"Plugin source not found: {SRC}")
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{PLUGIN_DIRNAME}-{_version()}.zip"

    files = sorted(p for p in SRC.rglob("*") if p.is_file() and _included(p.relative_to(SRC)))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            arcname = Path(PLUGIN_DIRNAME) / path.relative_to(SRC)
            zf.write(path, arcname.as_posix())

    print(f"Wrote {out} ({len(files)} files)")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Package the Cura plugin into an installable zip.")
    parser.add_argument("--outdir", type=Path, default=ROOT / "dist")
    build(parser.parse_args().outdir)


if __name__ == "__main__":
    main()
