"""rotate tool: rotate the active model about an axis."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import Axis, OrientationOutput, RotateInput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def rotate(axis: Axis, degrees: float) -> OrientationOutput:
        """Rotate the active model by ``degrees`` about ``axis`` (x, y, or z).

        Triggers a re-slice; call ``slice`` afterwards before reading estimates.
        """
        payload = RotateInput(axis=axis, degrees=degrees).model_dump(mode="json")
        data = await client.call("rotate", payload)
        return OrientationOutput(**data)
