"""Bridge configuration. All values overridable via environment variables.

The token-file path is the shared contract with the plugin: the plugin writes
the per-session token there, the bridge reads it. Keep both sides in sync.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_token_file() -> Path:
    # Mirrors the plugin's token location (see cura-plugin/server/auth.py).
    return Path.home() / ".cura-mcp" / "token"


@dataclass(frozen=True)
class Settings:
    host: str = os.environ.get("CURA_MCP_HOST", "127.0.0.1")
    port: int = int(os.environ.get("CURA_MCP_PORT", "8765"))
    token_file: Path = Path(os.environ.get("CURA_MCP_TOKEN_FILE", "")) or _default_token_file()
    # General request timeout (seconds). Slicing uses slice_timeout instead.
    timeout: float = float(os.environ.get("CURA_MCP_TIMEOUT", "30"))
    slice_timeout: float = float(os.environ.get("CURA_MCP_SLICE_TIMEOUT", "300"))

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


def load_settings() -> Settings:
    # Resolve token_file explicitly (dataclass default expr runs at import time).
    env_token = os.environ.get("CURA_MCP_TOKEN_FILE")
    token_file = Path(env_token) if env_token else _default_token_file()
    return Settings(
        host=os.environ.get("CURA_MCP_HOST", "127.0.0.1"),
        port=int(os.environ.get("CURA_MCP_PORT", "8765")),
        token_file=token_file,
        timeout=float(os.environ.get("CURA_MCP_TIMEOUT", "30")),
        slice_timeout=float(os.environ.get("CURA_MCP_SLICE_TIMEOUT", "300")),
    )
