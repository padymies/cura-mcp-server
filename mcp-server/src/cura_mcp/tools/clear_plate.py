"""clear_plate tool: remove all loaded models from the Cura build plate."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import ClearPlateOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def clear_plate() -> ClearPlateOutput:
        """Remove all printable models from the Cura build plate (undoable in Cura).

        Use before ``load_model`` to start from an empty plate; models otherwise
        accumulate across loads. Returns how many objects were removed.
        """
        data = await client.call("clear_plate")
        return ClearPlateOutput(**data)
