"""Plugin-side errors. Each carries a ``code`` that the router serializes into
the response envelope; the bridge maps the same codes back to typed exceptions.
Keep these codes in sync with ``mcp-server/src/cura_mcp/errors.py``.
"""
from __future__ import annotations


class PluginError(Exception):
    code = "cura_mcp_error"


class InvalidPath(PluginError):
    code = "invalid_path"


class NodeNotFound(PluginError):
    code = "node_not_found"


class ExportFailed(PluginError):
    code = "export_failed"


class UnknownSetting(PluginError):
    code = "unknown_setting"


class InvalidSettingValue(PluginError):
    code = "invalid_setting_value"


class PerExtruderUnsupported(PluginError):
    code = "per_extruder_unsupported"


class UnknownProfile(PluginError):
    code = "unknown_profile"


class LoadFailed(PluginError):
    code = "load_failed"


class SliceFailed(PluginError):
    code = "slice_failed"


class SliceTimeout(PluginError):
    code = "slice_timeout"


class NoActiveProfile(PluginError):
    code = "no_active_profile"


class AuthError(PluginError):
    code = "auth_error"
