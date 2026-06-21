"""Typed error hierarchy for the bridge.

Tool functions catch these and return structured errors to the LLM rather than
leaking stack traces. The plugin returns an error ``code`` in its JSON response;
``from_plugin_code`` maps it back to the right class.
"""
from __future__ import annotations


class CuraMcpError(Exception):
    """Base class for all bridge-surfaced errors."""

    code = "cura_mcp_error"


class CuraNotRunning(CuraMcpError):
    """The plugin's local server could not be reached (Cura not open?)."""

    code = "cura_not_running"


class AuthError(CuraMcpError):
    """Token missing/invalid, or request rejected by the plugin's auth layer."""

    code = "auth_error"


class InvalidPath(CuraMcpError):
    """load_model path failed the plugin's sandbox (allow-list / traversal / ext)."""

    code = "invalid_path"


class NodeNotFound(CuraMcpError):
    """No model on the plate matches the given node_id."""

    code = "node_not_found"


class ExportFailed(CuraMcpError):
    """Writing the mesh to disk failed (no writer for the format, or I/O error)."""

    code = "export_failed"


class UnknownSetting(CuraMcpError):
    """The setting key does not exist in the active machine definition."""

    code = "unknown_setting"


class InvalidSettingValue(CuraMcpError):
    """The value is the wrong type or outside the setting's allowed range/options."""

    code = "invalid_setting_value"


class PerExtruderUnsupported(CuraMcpError):
    """The setting is per-extruder; v1 of the settings API handles global only."""

    code = "per_extruder_unsupported"


class UnknownProfile(CuraMcpError):
    """No machine/material/quality profile matches the given name."""

    code = "unknown_profile"


class LoadFailed(CuraMcpError):
    """The model load did not complete (e.g. timed out or the reader failed)."""

    code = "load_failed"


class SliceFailed(CuraMcpError):
    """The slice ended in an error state or the model was unsliceable."""

    code = "slice_failed"


class SliceTimeout(CuraMcpError):
    """The slice did not settle within the timeout."""

    code = "slice_timeout"


class NoActiveProfile(CuraMcpError):
    """No machine/material profile is active; estimates would be meaningless."""

    code = "no_active_profile"


_BY_CODE = {
    cls.code: cls
    for cls in (
        CuraMcpError,
        CuraNotRunning,
        AuthError,
        InvalidPath,
        NodeNotFound,
        ExportFailed,
        UnknownSetting,
        InvalidSettingValue,
        PerExtruderUnsupported,
        UnknownProfile,
        LoadFailed,
        SliceFailed,
        SliceTimeout,
        NoActiveProfile,
    )
}


def from_plugin_code(code: str, message: str) -> CuraMcpError:
    """Build the right error subtype from a plugin error code."""
    return _BY_CODE.get(code, CuraMcpError)(message)
