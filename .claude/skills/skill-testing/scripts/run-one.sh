#!/usr/bin/env bash
# Run a single test prompt and extract the first Skill invocation.
#
# Usage:
#   run-one.sh <prompt-id> <expected-skill> <prompt-text>
#
# Env vars (required):
#   PLUGIN_DIR   absolute path to the plugin under test
#   PLUGIN_NAME  the plugin's name as declared in .claude-plugin/plugin.json
#                (used to filter Skill tool calls in the stream-json output)
#
# Env vars (optional):
#   OUT_DIR      directory for stream-json artifacts (default: /tmp/skill-testing/results)
#   MAX_BUDGET   per-call USD cap (default: 0.30)
#
# Output (tab-separated, one line):
#   <prompt-id>\t<expected-skill>\t<got-skill>\t<PASS|FAIL>

set -uo pipefail

PROMPT_ID="$1"
EXPECTED="$2"
PROMPT="$3"

: "${PLUGIN_DIR:?set PLUGIN_DIR to the absolute plugin path}"
: "${PLUGIN_NAME:?set PLUGIN_NAME to the plugin name from plugin.json}"
OUT_DIR="${OUT_DIR:-/tmp/skill-testing/results}"
MAX_BUDGET="${MAX_BUDGET:-0.30}"

mkdir -p "$OUT_DIR"
STREAM_FILE="$OUT_DIR/${PROMPT_ID}.jsonl"

claude -p \
  --plugin-dir "$PLUGIN_DIR" \
  --output-format stream-json --verbose \
  --dangerously-skip-permissions \
  --max-budget-usd "$MAX_BUDGET" \
  --no-session-persistence \
  --append-system-prompt "After reading the user request, decide whether to invoke a skill from the ${PLUGIN_NAME} plugin. If a skill clearly applies, invoke it via the Skill tool. If no ${PLUGIN_NAME} skill applies, do not invoke any Skill and just answer briefly. Do not do real work; just route." \
  "$PROMPT" > "$STREAM_FILE" 2>&1

# Extract the first Skill invocation matching this plugin's prefix.
FIRST_SKILL=$(grep -oE "\"skill\":\"${PLUGIN_NAME}:[a-z-]+\"" "$STREAM_FILE" | head -1 | sed "s/.*${PLUGIN_NAME}://;s/\"//")
if [ -z "$FIRST_SKILL" ]; then
  FIRST_SKILL="NONE"
fi

if [ "$EXPECTED" = "$FIRST_SKILL" ]; then
  STATUS="PASS"
else
  STATUS="FAIL"
fi

echo -e "${PROMPT_ID}\t${EXPECTED}\t${FIRST_SKILL}\t${STATUS}"
