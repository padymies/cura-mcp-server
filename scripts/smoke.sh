#!/usr/bin/env bash
# Live smoke-test runner for the cura-mcp plugin (see docs/manual-smoke-test.md).
# Requires Cura 5.10.0 running WITH the CuraMcp plugin installed.
# Usage: scripts/smoke.sh [/abs/path/to/model.stl]
set -u
PORT="${CURA_MCP_PORT:-8765}"
TOKENFILE="${CURA_MCP_TOKEN_FILE:-$HOME/.cura-mcp/token}"
MODEL="${1:-}"

rpc() { # rpc <method> <json-params>
  local method="$1" params="${2:-{}}"
  curl -s -m 320 -X POST "http://127.0.0.1:${PORT}/rpc" \
    -H 'Host: 127.0.0.1' -H "X-Cura-Mcp-Token: $(cat "$TOKENFILE")" \
    -d "{\"method\":\"${method}\",\"params\":${params}}"
  echo
}

code() { # code <host-header> <token> -> prints HTTP status
  curl -s -o /dev/null -w "%{http_code}" -m 10 -X POST "http://127.0.0.1:${PORT}/rpc" \
    -H "Host: $1" -H "X-Cura-Mcp-Token: $2" -d '{"method":"get_status"}'
}

echo "### token file: $TOKENFILE"; ls -la "$TOKENFILE" 2>&1
echo "### port $PORT binding (want 127.0.0.1):"; netstat -ano 2>/dev/null | grep -i "$PORT" | head
echo
echo "### §1 auth rejects (want 401 / 401 / 403):"
echo "  no token  -> $(code 127.0.0.1 '')"
echo "  bad token -> $(code 127.0.0.1 nope)"
echo "  bad host  -> $(code evil.example.com "$(cat "$TOKENFILE" 2>/dev/null)")"
echo
echo "### §2 get_status:"; rpc get_status
if [ -n "$MODEL" ]; then
  echo "### §3 load_model ($MODEL):"; rpc load_model "{\"path\":\"$MODEL\"}"
  echo "### §4 rotate x 45:";        rpc rotate '{"axis":"x","degrees":45}'
  echo "### §5 slice:";              rpc slice
  echo "### §5 get_estimates:";      rpc get_estimates
  echo "### §4 reset_orientation:";  rpc reset_orientation
  echo "### lay_flat:";              rpc lay_flat
else
  echo "(pass a model path as \$1 to run §3-§5 load/rotate/slice/estimates)"
fi
