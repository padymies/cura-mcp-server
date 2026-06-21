"""get_snapshot tool: render the plate to a PNG image the model can see."""
from __future__ import annotations

import base64

from mcp.server.fastmcp import FastMCP, Image

from ..client import PluginClient
from ..config import Settings
from ..errors import CuraMcpError


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def get_snapshot(width: int = 600, height: int = 600) -> Image:
        """Render the current build plate to a PNG image so you can see the layout
        of the models. Returns the image directly.
        """
        data = await client.call("get_snapshot", {"width": width, "height": height})
        encoded = data.get("image_base64")
        if not encoded:
            raise CuraMcpError("The build plate is empty; load a model before snapshotting.")
        return Image(data=base64.b64decode(encoded), format="png")
