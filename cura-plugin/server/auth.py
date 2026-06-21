"""Per-session token + Host-header allow-list.

Security controls (see docs/security-model.md):
- A random token is generated at startup and written to a user-readable file
  (restrictive permissions). Every request must present it.
- The Host header must be in the loopback allow-list (anti DNS-rebinding).
"""
from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

TOKEN_HEADER = "X-Cura-Mcp-Token"
_ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


def default_token_file() -> Path:
    # Shared contract with the bridge (mcp-server/src/cura_mcp/config.py).
    return Path.home() / ".cura-mcp" / "token"


class TokenManager:
    def __init__(self, token_file: Path | None = None) -> None:
        self._token_file = token_file or default_token_file()
        self._token = secrets.token_urlsafe(32)

    @property
    def token(self) -> str:
        return self._token

    def write(self) -> None:
        self._token_file.parent.mkdir(parents=True, exist_ok=True)
        self._token_file.write_text(self._token, encoding="utf-8")
        # Best-effort tighten permissions to owner-only (POSIX; no-op on Windows).
        try:
            os.chmod(self._token_file, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def cleanup(self) -> None:
        try:
            self._token_file.unlink(missing_ok=True)
        except OSError:
            pass

    def check_token(self, presented: str | None) -> bool:
        return bool(presented) and secrets.compare_digest(presented, self._token)


def host_allowed(host_header: str | None) -> bool:
    if not host_header:
        return False
    host = host_header.split(":", 1)[0].strip().lower()
    return host in _ALLOWED_HOSTS
