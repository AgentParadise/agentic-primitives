#!/bin/bash
# Run a benchmark recording
#
# Usage:
#   ./scripts/run_benchmark.sh <benchmark-name>
#   ./scripts/run_benchmark.sh context-window-growth
#   ./scripts/run_benchmark.sh context-compaction
#
# Requires: yq (brew install yq)
#
# See providers/workspaces/claude-cli/fixtures/benchmarks.yaml for available benchmarks

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BENCHMARKS_FILE="$REPO_ROOT/providers/workspaces/claude-cli/fixtures/benchmarks.yaml"
COMPOSE_DIR="$REPO_ROOT/providers/workspaces/claude-cli"

# Check for required tools
if ! command -v yq &> /dev/null; then
    echo "Error: yq is required. Install with: brew install yq"
    exit 1
fi

# Get benchmark name
BENCHMARK="${1:-}"
if [ -z "$BENCHMARK" ]; then
    echo "Usage: $0 <benchmark-name>"
    echo ""
    echo "Available benchmarks:"
    yq '.benchmarks | keys | .[]' "$BENCHMARKS_FILE"
    exit 1
fi

# Check if benchmark exists (use bracket notation for hyphenated keys)
if ! yq -e ".benchmarks[\"$BENCHMARK\"]" "$BENCHMARKS_FILE" > /dev/null 2>&1; then
    echo "Error: Benchmark '$BENCHMARK' not found"
    echo ""
    echo "Available benchmarks:"
    yq '.benchmarks | keys | .[]' "$BENCHMARKS_FILE"
    exit 1
fi

# Extract benchmark details (use bracket notation for hyphenated keys)
PROMPT=$(yq -r ".benchmarks[\"$BENCHMARK\"].prompt" "$BENCHMARKS_FILE")
DESCRIPTION=$(yq -r ".benchmarks[\"$BENCHMARK\"].description" "$BENCHMARKS_FILE")
EXPECTED_COST=$(yq -r ".benchmarks[\"$BENCHMARK\"].expected_cost" "$BENCHMARKS_FILE")

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Running Benchmark: $BENCHMARK"
echo "╠════════════════════════════════════════════════════════════════╣"
echo "║  Description: $DESCRIPTION"
echo "║  Expected cost: ~\$$EXPECTED_COST"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Press Enter to continue or Ctrl+C to cancel..."
read -r

# Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    if [ -f "$REPO_ROOT/.env" ]; then
        # shellcheck disable=SC1091
        source "$REPO_ROOT/.env"
    elif [ -f "$REPO_ROOT/../../.env" ]; then
        # AEF root .env
        # shellcheck disable=SC1091
        source "$REPO_ROOT/../../.env"
    fi
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "Error: ANTHROPIC_API_KEY not set"
    echo "Set it in environment or create .env file"
    exit 1
fi

# Run the benchmark
cd "$COMPOSE_DIR"

echo "Starting recording..."
export TASK="$BENCHMARK"
export PROMPT="$PROMPT"
export ANTHROPIC_API_KEY

docker compose -f docker-compose.record.yaml up

echo ""
echo "Recording complete! Check fixtures/recordings/$BENCHMARK/"
