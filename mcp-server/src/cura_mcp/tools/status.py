"""get_status tool: report Cura connection and active profile state."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..errors import CuraMcpError
from ..models import StatusOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def get_status() -> StatusOutput:
        """Check whether Cura is reachable and report the active machine/material.

        Use this first to diagnose connectivity before other tools.
        """
        try:
            data = await client.call("get_status")
        except CuraMcpError:
            return StatusOutput(cura_connected=False)
        return StatusOutput(cura_connected=True, **data)
