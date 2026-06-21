"""orientation tools: lay_flat and reset_orientation."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import OrientationOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def lay_flat() -> OrientationOutput:
        """Lay the active model flat on the build plate (minimize height)."""
        data = await client.call("lay_flat")
        return OrientationOutput(**data)

    @mcp.tool()
    async def reset_orientation() -> OrientationOutput:
        """Reset the active model to its original (unrotated) orientation."""
        data = await client.call("reset_orientation")
        return OrientationOutput(**data)
