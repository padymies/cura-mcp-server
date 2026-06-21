"""HTTP client to the Cura plugin's local server.

Reads the per-session token written by the plugin, injects it on every request,
and maps the plugin's structured error envelope back to typed exceptions. This is
the only place the bridge talks to the plugin.
"""
from __future__ import annotations

from typing import Any

import httpx

from .config import Settings
from .errors import CuraNotRunning, from_plugin_code
from .models import PluginResponse


class PluginClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(base_url=settings.base_url, timeout=settings.timeout)

    def _read_token(self) -> str:
        try:
            return self._settings.token_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise CuraNotRunning(
                "No Cura plugin token found. Is Cura running with the cura-mcp plugin?"
            ) from exc

    async def call(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Call a plugin method; return ``data`` on success, raise a typed error otherwise."""
        token = self._read_token()
        try:
            resp = await self._client.post(
                "/rpc",
                json={"method": method, "params": payload or {}},
                headers={"X-Cura-Mcp-Token": token, "Host": self._settings.host},
                timeout=timeout or self._settings.timeout,
            )
        except httpx.ConnectError as exc:
            raise CuraNotRunning(
                "Could not reach the Cura plugin server. Is Cura open?"
            ) from exc

        body = PluginResponse.model_validate(resp.json())
        if body.ok:
            return body.data or {}
        assert body.error is not None
        raise from_plugin_code(body.error.code, body.error.message)

    async def aclose(self) -> None:
        await self._client.aclose()
