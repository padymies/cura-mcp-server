# cura-mcp-server

**Fully local. No hub. No telemetry.** An open-source [MCP](https://modelcontextprotocol.io)
server that lets an AI client (Claude Desktop, Claude Code, …) drive the
[UltiMaker Cura](https://ultimaker.com/software/ultimaker-cura/) slicer
conversationally: load a model, reorient it, slice it, and get material usage and
print time — without any third-party server in the loop.

> Ask: *"load this STL, rotate it 45° on X, slice it, and tell me how much
> filament it uses"* — and get a real answer from your own Cura install.

## How it works

Two components in one repo, talking over loopback only:

- **`mcp-server/`** — the bridge. Speaks MCP to your AI client and exposes typed
  tools. Runs in your own Python environment.
- **`cura-plugin/`** — a Cura plugin (standard-library only) that runs inside
  Cura, hosts a token-authenticated local server, and is the only thing that
  touches Cura's APIs.

See the component READMEs ([`mcp-server/`](mcp-server/README.md) and
[`cura-plugin/`](cura-plugin/README.md)) for details.

## Status

Early development. See `CHANGELOG.md`. Targets Cura **5.x** (validated minor
versions noted in `cura-plugin/plugin.json`).

## Install

Two pieces: the **plugin** (inside Cura) and the **bridge** (in your own Python
environment, launched by your MCP client).

### 1. Install the Cura plugin

Copy the [`cura-plugin/`](cura-plugin/) directory into Cura's plugins folder,
**renamed to `CuraMcp`** (the folder must be a valid Python package name):

- **Windows:** `%APPDATA%\cura\<version>\plugins\CuraMcp\`
- **Linux:** `~/.local/share/cura/<version>/plugins/CuraMcp/`
- **macOS:** `~/Library/Application Support/cura/<version>/plugins/CuraMcp/`

Restart Cura. On startup the plugin writes a per-session token to
`~/.cura-mcp/token` and starts a loopback-only server on `127.0.0.1:8765`.
Check the binding with `netstat -an | findstr 8765` (Windows) or
`ss -ltn | grep 8765` (Linux) — the address must be `127.0.0.1`, not `0.0.0.0`.

### 2. Install the bridge

```bash
cd mcp-server
pip install -e .
```

### 3. Point your MCP client at the bridge

See [`examples/claude-desktop-config.json`](examples/claude-desktop-config.json):

```json
{
  "mcpServers": {
    "cura": {
      "command": "python",
      "args": ["-m", "cura_mcp.server"],
      "env": { "CURA_MCP_PORT": "8765" }
    }
  }
}
```

Restart the client. With Cura open, ask it to `get_status` first to confirm the
connection.

### Configuration (environment variables)

| Variable | Default | Used by |
|----------|---------|---------|
| `CURA_MCP_HOST` | `127.0.0.1` | both |
| `CURA_MCP_PORT` | `8765` | both |
| `CURA_MCP_TOKEN_FILE` | `~/.cura-mcp/token` | both (must match) |
| `CURA_MCP_TIMEOUT` | `30` | bridge |
| `CURA_MCP_SLICE_TIMEOUT` | `300` | bridge |
| `CURA_MCP_ALLOWED_DIRS` | user home dir | plugin (filesystem sandbox) |

## Try this

Drop [`agent/cura-slicing-assistant.md`](agent/cura-slicing-assistant.md) into
your MCP client as a system prompt — it maps your intent to the right tools, so
you don't need to know any tool names — then ask:

- *"Load `~/models/bracket.stl`, lay it flat, set 0.2 mm layers and 20 % infill,
  slice it, and tell me filament and print time — then show me the plate."*
- *"I want 6 of these on one plate. Duplicate, arrange them, slice, and tell me
  total filament and how many fit."*
- *"Try this at 0.12 mm and again at 0.28 mm and compare time vs material."*
- *"Rotate it 45° on X, re-slice, and tell me how the totals changed."*

## Security

This software opens a local server and (in future versions) can interact with
hardware. Read [`SECURITY.md`](SECURITY.md). The server binds to `127.0.0.1`
only, requires a per-session token, and makes no outbound network calls. File
reads/writes are sandboxed to your home directory by default; set
`CURA_MCP_ALLOWED_DIRS` (OS path-separated) to restrict or relocate that scope.

## License & disclaimers

MIT — see [`LICENSE`](LICENSE).

Not affiliated with, endorsed by, or sponsored by UltiMaker. "Cura" and
"UltiMaker" are trademarks of UltiMaker B.V., used here only to identify
compatibility.

This software interacts with 3D printing software and may, in future versions,
control hardware that reaches high temperatures and moves mechanically. **Use at
your own risk.** The authors accept no liability for damage to equipment,
material, or property.
