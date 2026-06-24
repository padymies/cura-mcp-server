"""list_variants tool: nozzle variants compatible with the active machine."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import ListVariantsOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def list_variants() -> ListVariantsOutput:
        """List the nozzle variants available for the active machine, marking the
        active one (and returning its name in ``active``).
        """
        data = await client.call("list_variants")
        return ListVariantsOutput(**data)
