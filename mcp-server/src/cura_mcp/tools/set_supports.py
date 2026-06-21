"""set_supports tool: toggle support generation and placement."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import SupportsOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def set_supports(enabled: bool, type: str | None = None) -> SupportsOutput:  # noqa: A002
        """Enable or disable supports. Optional ``type``: "buildplate" (only touching
        the plate) or "everywhere". Returns the applied support_enable/support_type.
        """
        payload: dict[str, object] = {"enabled": enabled}
        if type is not None:
            payload["type"] = type
        data = await client.call("set_supports", payload)
        return SupportsOutput(**data)
