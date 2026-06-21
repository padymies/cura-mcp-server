"""scale_model tool: scale a model uniformly or per-axis."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import TransformOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def scale_model(
        node_id: str,
        factor: float | None = None,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
    ) -> TransformOutput:
        """Scale a model. Pass ``factor`` for uniform scaling (multiplies the model's
        CURRENT size, e.g. 2 = twice as big), or ``x``/``y``/``z`` for per-axis
        multipliers. The model is re-seated on the plate afterwards.
        """
        payload: dict[str, Any] = {"node_id": node_id}
        for key, value in (("factor", factor), ("x", x), ("y", y), ("z", z)):
            if value is not None:
                payload[key] = value
        data = await client.call("scale_model", payload)
        return TransformOutput(**data)
