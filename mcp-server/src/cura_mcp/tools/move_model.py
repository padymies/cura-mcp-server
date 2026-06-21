"""move_model tool: translate a model on the plate."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import TransformOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def move_model(
        node_id: str,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        relative: bool = False,
    ) -> TransformOutput:
        """Move a model. With ``relative=False`` (default) the model's origin is set
        to (x, y, z) in plate mm; with ``relative=True`` it is shifted by (x, y, z).

        This is the raw move and does NOT re-seat the model — it can be used to push
        a model partly/fully outside the build volume on purpose. The result's
        ``fits_build_volume`` reflects the new position.
        """
        data = await client.call(
            "move_model",
            {"node_id": node_id, "x": x, "y": y, "z": z, "relative": relative},
        )
        return TransformOutput(**data)
