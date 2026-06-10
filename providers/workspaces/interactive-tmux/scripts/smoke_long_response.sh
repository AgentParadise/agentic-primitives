#!/usr/bin/env bash
# Long-response smoke — asks each agent for a multi-paragraph reply that
# overflows the visible tmux pane (default 200x50), then verifies that:
#
#   1. The capture returns FAR more than 50 rows (the full scrollback,
#      proving the `-S - -E -` fix landed everywhere) — D-block-3.
#   2. `await_completion` finished in well under the 240s old timeout
#      (proving the bottom-of-pane tail predicate sees the live idle
#      state past the multi-paragraph history) — D-block-2.
#
# Pre-reqs match scripts/smoke.sh: image built, ~/.claude / ~/.codex /
# ~/.gemini present and authed.

set -euo pipefail

PROVIDER_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DRIVER="$PROVIDER_DIR/driver/interactive_tmux.py"
RUNS_DIR="$PROVIDER_DIR/runs"
mkdir -p "$RUNS_DIR"

NAME="smoke-long-$(date +%s)"

cleanup() {
    python3 "$DRIVER" stop --name "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[long] starting workspace $NAME"
python3 "$DRIVER" start --name "$NAME" >/dev/null

# Each agent gets the same prompt asking for a long reply with a unique
# token sentinel. We then capture and check:
#  - response marker + token present in capture (existing smoke contract)
#  - capture has > 1 pane height (50 rows) of content (D-block-3)
#  - await completed in well under the 240s timeout (D-block-2)

declare -A TOKENS=(
    [claude]="LONG-CLAUDE-$$"
    [codex]="LONG-CODEX-$$"
    [gemini]="LONG-GEMINI-$$"
)
declare -A MARKERS=(
    [claude]="● "
    [codex]="• "
    [gemini]="✦ "
)

FAILED=()

for AGENT in claude codex gemini; do
    TOKEN="${TOKENS[$AGENT]}"
    MARKER="${MARKERS[$AGENT]}"

    # Multi-paragraph prompt — asks for ~7 short paragraphs of narrative
    # prose so the reply overflows the 50-row visible window and exercises
    # the scrollback / tail-predicate paths. Each paragraph is varied
    # enough (different topics) that gemini's loop detector does not flag
    # it as repetitive output (which would pop a modal and break the test).
    PROMPT="Reply with the sentinel '${TOKEN}' on its own line first, then write seven short paragraphs (5-7 sentences each). Vary the topics: 1) clean architecture, 2) the unreasonable effectiveness of small functions, 3) why structured logging beats ad-hoc print debugging, 4) the cost of premature optimization, 5) writing tests that survive refactors, 6) feedback loops in interactive systems, 7) when to choose a monolith over microservices. Use plain prose with no bullets or numbering inside paragraphs. Make the whole reply long enough to fill the terminal."

    echo "[long] $AGENT: send long prompt"
    python3 "$DRIVER" send --name "$NAME" --agent "$AGENT" --text "$PROMPT"

    echo "[long] $AGENT: await (timeout=120)"
    START_TS=$(date +%s)
    AWAIT_OUT=$(python3 "$DRIVER" await --name "$NAME" --agent "$AGENT" --timeout 120 || true)
    END_TS=$(date +%s)
    ELAPSED=$((END_TS - START_TS))

    OUT_FILE="$RUNS_DIR/long-$AGENT.txt"
    python3 "$DRIVER" capture --name "$NAME" --agent "$AGENT" >"$OUT_FILE"

    LINE_COUNT=$(wc -l <"$OUT_FILE")
    BYTE_COUNT=$(wc -c <"$OUT_FILE")

    REPLY_PRESENT=no
    if grep -qF "${MARKER}${TOKEN}" "$OUT_FILE" || grep -qF "${TOKEN}" "$OUT_FILE"; then
        REPLY_PRESENT=yes
    fi

    # D-block-3 gate: capture must include MORE than one pane height of rows.
    SCROLLBACK_OK=no
    if [ "$LINE_COUNT" -gt 50 ]; then
        SCROLLBACK_OK=yes
    fi

    # D-block-2 gate: await must complete in well under the old 240s
    # timeout (we passed --timeout 120, so anything finishing inside
    # that window is good; anything = 120 is suspect).
    AWAIT_FAST=no
    if [ "$ELAPSED" -lt 100 ]; then
        AWAIT_FAST=yes
    fi

    echo "[long] $AGENT: elapsed=${ELAPSED}s lines=$LINE_COUNT bytes=$BYTE_COUNT marker=$REPLY_PRESENT scrollback=$SCROLLBACK_OK await_fast=$AWAIT_FAST"
    echo "[long] $AGENT: await JSON: $AWAIT_OUT"

    if [ "$REPLY_PRESENT" = "no" ] || [ "$SCROLLBACK_OK" = "no" ] || [ "$AWAIT_FAST" = "no" ]; then
        FAILED+=("$AGENT(marker=$REPLY_PRESENT,scrollback=$SCROLLBACK_OK,await_fast=$AWAIT_FAST)")
    fi
done

echo
if [ ${#FAILED[@]} -eq 0 ]; then
    echo "[long] ALL PASS — scrollback returned, idle reached fast on every agent"
    exit 0
else
    echo "[long] FAILED: ${FAILED[*]}"
    exit 1
fi
