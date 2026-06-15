#!/usr/bin/env bash
# interactive-tmux provider smoke test — Rust driver edition.
#
# Mirrors scripts/smoke.sh line-for-line, but drives the workspace through
# the Rust `itmux` binary instead of `python3 driver/interactive_tmux.py`.
# Sends ONE prompt+response round-trip per agent (claude, codex, gemini)
# and verifies each agent returned its unique echo token. Writes per-agent
# transcripts to runs/smoke-rs-<agent>.txt alongside this script.
#
# Usage:
#   bash providers/workspaces/interactive-tmux/scripts/smoke-rs.sh
#
# Pre-reqs:
#   - Image agentic-workspace-interactive-tmux:latest built
#     (uv run scripts/build-provider.py interactive-tmux)
#   - ~/.claude, ~/.codex, ~/.gemini present on host (authed)
#   - The Rust driver built (cargo build --release inside driver-rs/).

set -euo pipefail

PROVIDER_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DRIVER_RS_DIR="$PROVIDER_DIR/driver-rs"
RUNS_DIR="$PROVIDER_DIR/runs"
mkdir -p "$RUNS_DIR"

# Build (release) on demand so a fresh checkout runs without an extra step.
ITMUX_BIN="${ITMUX_BIN:-}"
if [ -z "$ITMUX_BIN" ]; then
    if [ -x "$DRIVER_RS_DIR/target/release/itmux" ]; then
        ITMUX_BIN="$DRIVER_RS_DIR/target/release/itmux"
    else
        # Honour CARGO_TARGET_DIR if set; otherwise let cargo emit its
        # workspace-relative target/release/itmux.
        echo "[smoke-rs] building itmux (release)…"
        (cd "$DRIVER_RS_DIR" && cargo build --release --quiet)
        # Resolve the target dir cargo actually used.
        TARGET_DIR=$(cd "$DRIVER_RS_DIR" && cargo metadata --no-deps --format-version 1 \
            | python3 -c "import json,sys; print(json.load(sys.stdin)['target_directory'])")
        ITMUX_BIN="$TARGET_DIR/release/itmux"
    fi
fi

if [ ! -x "$ITMUX_BIN" ]; then
    echo "[smoke-rs] FATAL: itmux binary not found at $ITMUX_BIN" >&2
    exit 1
fi
echo "[smoke-rs] using itmux: $ITMUX_BIN"

NAME="smoke-rs-$(date +%s)"

cleanup() {
    "$ITMUX_BIN" stop --name "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[smoke-rs] starting workspace $NAME"
"$ITMUX_BIN" start --name "$NAME"

declare -A TOKENS=(
    [claude]="SMOKE-RS-CLAUDE-$$"
    [codex]="SMOKE-RS-CODEX-$$"
    [gemini]="SMOKE-RS-GEMINI-$$"
)
# Per-agent response marker prefixed in front of the model's reply. Used
# to distinguish the echoed prompt from the model output (otherwise
# grepping for the token alone matches the prompt line and false-passes).
declare -A MARKERS=(
    [claude]="● "
    [codex]="• "
    [gemini]="✦ "
)

FAILED=()

for AGENT in claude codex gemini; do
    TOKEN="${TOKENS[$AGENT]}"
    MARKER="${MARKERS[$AGENT]}"
    echo "[smoke-rs] $AGENT: send \"Reply only with: $TOKEN\""
    "$ITMUX_BIN" send --name "$NAME" --agent "$AGENT" \
        --text "Reply only with: $TOKEN"

    echo "[smoke-rs] $AGENT: await completion (timeout=120s)"
    if ! "$ITMUX_BIN" await --name "$NAME" --agent "$AGENT" --timeout 120 >/dev/null; then
        echo "[smoke-rs] $AGENT: await TIMEOUT (will still check transcript)"
    fi

    "$ITMUX_BIN" capture --name "$NAME" --agent "$AGENT" \
        > "$RUNS_DIR/smoke-rs-$AGENT.txt"

    # Pass requires the response marker AND the echo token on the same line —
    # this catches the model's reply, not the echoed prompt.
    if grep -qF "${MARKER}${TOKEN}" "$RUNS_DIR/smoke-rs-$AGENT.txt"; then
        echo "[smoke-rs] $AGENT: PASS — response \"${MARKER}${TOKEN}\" in transcript"
    else
        echo "[smoke-rs] $AGENT: FAIL — response \"${MARKER}${TOKEN}\" missing"
        FAILED+=("$AGENT")
    fi
done

echo
if [ ${#FAILED[@]} -eq 0 ]; then
    echo "[smoke-rs] ALL PASS (3/3 agents)"
    exit 0
else
    echo "[smoke-rs] FAILED: ${FAILED[*]}"
    exit 1
fi
