"""switch_variant tool: set the active extruder's nozzle variant."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import SwitchVariantOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def switch_variant(name: str) -> SwitchVariantOutput:
        """Set the active extruder's nozzle variant by display name or id (see
        ``list_variants``). Changing the nozzle can narrow the compatible-material
        set, so the result notes whether the active material was swapped. Unknown
        variant -> ``unknown_profile`` error.
        """
        data = await client.call("switch_variant", {"name": name})
        return SwitchVariantOutput(**data)
