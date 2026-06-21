"""arrange_all tool: auto-arrange every model on the plate."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import ArrangeAllOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def arrange_all() -> ArrangeAllOutput:
        """Auto-arrange all models on the build plate so they don't overlap.

        Uses Cura's own nesting arranger. Returns how many models were arranged.
        """
        data = await client.call("arrange_all")
        return ArrangeAllOutput(**data)
