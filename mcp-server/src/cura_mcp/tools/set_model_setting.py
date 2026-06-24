"""set_model_setting tool: apply a per-object setting override to one model."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import ModelSettingOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def set_model_setting(node_id: str, key: str, value: Any) -> ModelSettingOutput:
        """Override a setting for ONE model only (e.g. a different
        ``infill_sparse_density`` on a single part), leaving every other model and
        the global profile untouched. Validated exactly like ``set_setting``
        (key/type/range/enum) — unknown key → ``unknown_setting``, bad value →
        ``invalid_setting_value``, unknown model → ``node_not_found``.
        """
        data = await client.call(
            "set_model_setting", {"node_id": node_id, "key": key, "value": value}
        )
        return ModelSettingOutput(**data)
