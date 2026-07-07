#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXP="$ROOT/experiments/2026-07-07--langfuse--trace-query-cli"
RUNS="$EXP/runs/mock-query"
ITMUX_BIN="${ITMUX_BIN:-$ROOT/providers/workspaces/interactive-tmux/driver-rs/target/debug/itmux}"

rm -rf "$RUNS"
mkdir -p "$RUNS"

if [[ ! -x "$ITMUX_BIN" ]]; then
  echo "itmux binary is missing or not executable: $ITMUX_BIN" >"$RUNS/summary.txt"
  exit 78
fi

python3 - "$RUNS" <<'PY' &
import base64
import http.server
import json
import pathlib
import socketserver
import sys

runs = pathlib.Path(sys.argv[1])
expected_auth = "Basic " + base64.b64encode(b"pk-query-test:sk-query-test").decode("ascii")

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        captured = {
            "method": "GET",
            "path": self.path,
            "authorization_matches_expected": self.headers.get("Authorization") == expected_auth,
            "authorization_redacted": "<present>" if self.headers.get("Authorization") else "<missing>",
        }
        (runs / "captured-request.redacted.json").write_text(
            json.dumps(captured, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        body = {
            "data": [
                {
                    "id": "obs-1",
                    "traceId": "abc123",
                    "type": "SPAN",
                    "name": "agentic_primitives.run",
                }
            ],
            "meta": {"totalItems": 1},
        }
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        return

with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
    (runs / "port.txt").write_text(str(server.server_address[1]) + "\n", encoding="utf-8")
    server.handle_request()
PY

server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT

for _ in {1..100}; do
  [[ -s "$RUNS/port.txt" ]] && break
  sleep 0.05
done

if [[ ! -s "$RUNS/port.txt" ]]; then
  echo "mock server did not publish a port" >"$RUNS/summary.txt"
  exit 1
fi

port="$(cat "$RUNS/port.txt")"
set +e
LANGFUSE_BASE_URL="http://127.0.0.1:$port" \
LANGFUSE_PUBLIC_KEY="pk-query-test" \
LANGFUSE_SECRET_KEY="sk-query-test" \
"$ITMUX_BIN" langfuse-trace \
  --trace-id abc123 \
  --from-start-time 2026-07-07T20:00:00Z \
  --to-start-time 2026-07-07T21:00:00Z \
  --limit 25 \
  >"$RUNS/query-response.json"
exit_code=$?
set -e
printf '%s\n' "$exit_code" >"$RUNS/query-exit.txt"
wait "$server_pid"
trap - EXIT

{
  echo "exit_code=$exit_code"
  echo "captured_request=runs/mock-query/captured-request.redacted.json"
  echo "query_response=runs/mock-query/query-response.json"
} >"$RUNS/summary.txt"

rm -f "$RUNS/port.txt"

exit "$exit_code"
