# Cura plugin (cura-mcp-plugin)

Runs **inside** UltiMaker Cura. Hosts a loopback-only, token-authenticated HTTP
server and is the only component that touches Cura's APIs.

## Hard constraints

- **Standard library only.** No third-party dependencies — this runs in Cura's
  bundled interpreter where `pip install` is impractical.
- **All Cura-internal access lives in `adapters/cura_api.py`.** Nothing else
  imports from `cura.*` / `UM.*`. When a Cura version changes an internal, fix
  one file.
- **Mutating scene/backend calls go through `bridge/main_thread.py`.** The HTTP
  server runs on a worker thread; Cura operations must run on the main thread.

## Install

Copy this `cura-plugin/` directory into Cura's plugins folder as `CuraMcp`:

- Windows: `%APPDATA%\cura\<version>\plugins\CuraMcp\`
- Linux: `~/.local/share/cura/<version>/plugins/CuraMcp/`
- macOS: `~/Library/Application Support/cura/<version>/plugins/CuraMcp/`

Restart Cura. On startup the plugin writes a per-session token to
`~/.cura-mcp/token` and starts the server on `127.0.0.1:8765`.

## Layout

```
CuraMcpPlugin.py     Extension lifecycle (start/stop server)
server/              http_server.py (stdlib), auth.py (token + Host), router.py
bridge/main_thread.py  marshal callables onto Cura's main thread
operations/          load, transform, slice (handshake), estimate, status
adapters/cura_api.py THE only Cura-internals touchpoint (fill from docs)
```

See `../docs/hard-problems.md` and `../docs/cura-api-reference.md`.

## Validated Cura versions

The full smoke test (`../docs/manual-smoke-test.md`) is green on:

- **UltiMaker Cura 5.10.0** (plugin SDK 8)
- **UltiMaker Cura 5.13.0** (plugin SDK 8.12.0)

`plugin.json` declares `api: 8` / `supported_sdk_versions: [8, 9]`, which loads on
both. The adapter (`adapters/cura_api.py`) is identical across the two — no
version-specific branches were needed.
