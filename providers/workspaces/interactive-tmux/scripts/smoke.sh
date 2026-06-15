#!/usr/bin/env bash
# interactive-tmux provider smoke test.
#
# Runs ONE prompt+response round-trip per agent (claude, codex, gemini)
# through the host-side driver and verifies each agent returned its
# unique echo token. Writes per-agent transcripts to runs/smoke-<agent>.txt
# alongside this script.
#
# Usage:
#   bash providers/workspaces/interactive-tmux/scripts/smoke.sh
#
# Pre-reqs:
#   - Image agentic-workspace-interactive-tmux:latest built
#     (uv run scripts/build-provider.py interactive-tmux)
#   - ~/.claude, ~/.codex, ~/.gemini present on host (authed)

set -euo pipefail

PROVIDER_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DRIVER="$PROVIDER_DIR/driver/interactive_tmux.py"
RUNS_DIR="$PROVIDER_DIR/runs"
mkdir -p "$RUNS_DIR"

NAME="smoke-$(date +%s)"

cleanup() {
    python3 "$DRIVER" stop --name "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[smoke] starting workspace $NAME"
python3 "$DRIVER" start --name "$NAME"

declare -A TOKENS=(
    [claude]="SMOKE-CLAUDE-$$"
    [codex]="SMOKE-CODEX-$$"
    [gemini]="SMOKE-GEMINI-$$"
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
    echo "[smoke] $AGENT: send \"Reply only with: $TOKEN\""
    python3 "$DRIVER" send --name "$NAME" --agent "$AGENT" \
        --text "Reply only with: $TOKEN"

    echo "[smoke] $AGENT: await completion (timeout=120s)"
    if ! python3 "$DRIVER" await --name "$NAME" --agent "$AGENT" --timeout 120 >/dev/null; then
        echo "[smoke] $AGENT: await TIMEOUT (will still check transcript)"
    fi

    python3 "$DRIVER" capture --name "$NAME" --agent "$AGENT" \
        > "$RUNS_DIR/smoke-$AGENT.txt"

    # Pass requires the response marker AND the echo token on the same line —
    # this catches the model's reply, not the echoed prompt.
    if grep -qF "${MARKER}${TOKEN}" "$RUNS_DIR/smoke-$AGENT.txt"; then
        echo "[smoke] $AGENT: PASS — response \"${MARKER}${TOKEN}\" in transcript"
    else
        echo "[smoke] $AGENT: FAIL — response \"${MARKER}${TOKEN}\" missing"
        FAILED+=("$AGENT")
    fi
done

echo
if [ ${#FAILED[@]} -eq 0 ]; then
    echo "[smoke] ALL PASS (3/3 agents)"
    exit 0
else
    echo "[smoke] FAILED: ${FAILED[*]}"
    exit 1
fi
