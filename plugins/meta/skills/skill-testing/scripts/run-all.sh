#!/usr/bin/env bash
# Run all prompts from a test matrix in parallel batches.
#
# Usage:
#   run-all.sh [path/to/prompts.tsv]
#
# Env vars (required):
#   PLUGIN_DIR   absolute path to the plugin under test
#   PLUGIN_NAME  the plugin's name as declared in .claude-plugin/plugin.json
#
# Env vars (optional):
#   BATCH        parallel job cap (default: 5)
#   OUT_DIR      results directory (default: /tmp/skill-testing)
#   PROMPTS      explicit matrix path (overrides positional arg)
#
# Test matrix format (TSV, one prompt per line):
#   <id>\t<expected-skill-name-or-NONE>\t<prompt-text>
#
# Output: writes <OUT_DIR>/results.tsv sorted by prompt id, plus a summary
# count of PASS/FAIL on stdout.

set -uo pipefail

: "${PLUGIN_DIR:?set PLUGIN_DIR to the absolute plugin path}"
: "${PLUGIN_NAME:?set PLUGIN_NAME to the plugin name from plugin.json}"
BATCH="${BATCH:-5}"
OUT_DIR="${OUT_DIR:-/tmp/skill-testing}"
PROMPTS="${PROMPTS:-${1:-}}"

if [ -z "${PROMPTS}" ] || [ ! -f "${PROMPTS}" ]; then
  echo "usage: run-all.sh <path/to/prompts.tsv>"
  echo "   or: PROMPTS=<path> run-all.sh"
  echo "  PLUGIN_DIR=$PLUGIN_DIR"
  echo "  PLUGIN_NAME=$PLUGIN_NAME"
  exit 2
fi

mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/results.tsv"
rm -f "$OUT"

# Discover runner alongside this script.
RUNNER="$(cd "$(dirname "$0")" && pwd)/run-one.sh"
[ -x "$RUNNER" ] || { echo "missing $RUNNER" >&2; exit 1; }

export PLUGIN_DIR PLUGIN_NAME OUT_DIR

running=0
while IFS=$'\t' read -r id expected prompt; do
  [ -z "$id" ] && continue
  ( "$RUNNER" "$id" "$expected" "$prompt" >> "$OUT" 2>&1 ) &
  running=$((running + 1))
  if [ "$running" -ge "$BATCH" ]; then
    wait
    running=0
  fi
done < "$PROMPTS"
wait

sort -o "$OUT" "$OUT"
echo "--- results.tsv ---"
cat "$OUT"
echo
echo "--- summary ---"
awk -F'\t' '{c[$4]++} END {for (s in c) printf "%s: %d\n", s, c[s]}' "$OUT"
