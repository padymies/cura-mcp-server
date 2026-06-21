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

See [`docs/architecture.md`](docs/architecture.md) for the full picture.

## Status

Early development. See `CHANGELOG.md`. Targets Cura **5.x** (validated minor
versions noted in `cura-plugin/plugin.json`).

## Install

See [`docs/installation.md`](docs/installation.md) and
[`examples/claude-desktop-config.json`](examples/claude-desktop-config.json).

## Security

This software opens a local server and (in future versions) can interact with
hardware. Read [`SECURITY.md`](SECURITY.md). The server binds to `127.0.0.1`
only, requires a per-session token, and makes no outbound network calls.

## License & disclaimers

MIT — see [`LICENSE`](LICENSE).

Not affiliated with, endorsed by, or sponsored by UltiMaker. "Cura" and
"UltiMaker" are trademarks of UltiMaker B.V., used here only to identify
compatibility.

This software interacts with 3D printing software and may, in future versions,
control hardware that reaches high temperatures and moves mechanically. **Use at
your own risk.** The authors accept no liability for damage to equipment,
material, or property.
