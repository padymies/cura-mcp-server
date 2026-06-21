"""list_machines tool: enumerate configured printers."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import ListMachinesOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def list_machines() -> ListMachinesOutput:
        """List the configured printers (id, name) and which one is active."""
        data = await client.call("list_machines")
        return ListMachinesOutput(**data)
