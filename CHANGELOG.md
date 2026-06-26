# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0]

First public release. Two components: the MCP bridge (`mcp-server/`) and the
Cura plugin (`cura-plugin/`), talking over loopback HTTP.

### Added
- **Architecture & transport**: FastMCP bridge (stdio) forwarding each tool call
  to a standard-library Cura plugin over a token-authenticated loopback HTTP
  server; Qt main-thread marshalling and a synchronous slice/load handshake.
- **Security baseline**: loopback-only binding, per-session token
  (constant-time compare), `Host` allow-list, request size cap, and a filesystem
  sandbox for reads and writes (directory allow-list, traversal rejection,
  extension allow-list; configurable via `CURA_MCP_ALLOWED_DIRS`).
- **Core tools**: `get_status`, `load_model`, `clear_plate`, `rotate`,
  `lay_flat`, `reset_orientation`, `slice`, `get_estimates`.
- **Model management & transforms**: `list_models`, `select_model`,
  `remove_model`, `duplicate_model`, `arrange_all`, `scale_model`,
  `mirror_model`, `move_model`, `center_model`, `scale_to_fit`.
- **Info / snapshot / export**: `get_machine_info`, `get_snapshot`,
  `export_model`.
- **Settings**: `get_setting`, `set_setting`, `reset_setting`, curated writers
  (`set_layer_height`, `set_infill_density`, `set_supports`, `set_adhesion`,
  `set_quality`), `get_all_user_settings`, `reset_all_settings`.
- **Profiles & variants**: `list_machines`, `switch_machine`, `list_materials`,
  `switch_material`, `list_variants`, `switch_variant`.
- **G-code export**: `export_gcode` (gated on a completed slice).
- **Grouping & projects**: `group_models`, `ungroup_model`, `merge_models`,
  `save_project`, `open_project` (two-step preview/confirm; destructive).
- **Per-object settings & mesh types**: `set_model_setting`,
  `reset_model_setting`, `set_mesh_type`, `get_model_settings`.

### Validated
- Live against UltiMaker Cura 5.10.0 and 5.13.0.

[Unreleased]: https://github.com/padicodeai-cloud/cura-mcp-server/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/padicodeai-cloud/cura-mcp-server/releases/tag/v0.1.0
