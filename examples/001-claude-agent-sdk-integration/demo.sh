#!/bin/bash
# Demo script for Claude Agent SDK Integration
#
# This script runs the test scenarios and displays results.
# Requires: ANTHROPIC_API_KEY environment variable

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
cat << 'EOF'
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║       Claude Agent SDK Integration Demo                        ║
║       Metrics Collection & Security Hooks                      ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

# Check uv
if ! command -v uv &> /dev/null; then
    echo -e "${RED}❌ uv not found. Install with:${NC}"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
echo -e "${GREEN}✓${NC} uv installed"

# Check API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${RED}❌ ANTHROPIC_API_KEY not set${NC}"
    echo "   Export your API key:"
    echo "   export ANTHROPIC_API_KEY='sk-ant-...'"
    exit 1
fi
echo -e "${GREEN}✓${NC} ANTHROPIC_API_KEY set"

# Build hooks if needed
if [ ! -f ".claude/hooks/security/bash-validator.py" ]; then
    echo -e "${YELLOW}Building security hooks...${NC}"
    ./build-hooks.sh
fi
echo -e "${GREEN}✓${NC} Security hooks installed"

# Sync dependencies
echo -e "${YELLOW}Syncing dependencies...${NC}"
uv sync --quiet
echo -e "${GREEN}✓${NC} Dependencies ready"

# Clean previous workspace
echo -e "${YELLOW}Cleaning workspace...${NC}"
rm -rf .workspace/*
rm -f .agentic/analytics/events.jsonl
mkdir -p .workspace .agentic/analytics
echo -e "${GREEN}✓${NC} Workspace clean"

echo
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo

# Parse arguments
DRY_RUN=false
SCENARIO=""
MODEL="claude-haiku-4-5-20251001"  # Default to cheaper model for demos (latest Haiku)
VERBOSE=""

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --dry-run|-n) DRY_RUN=true ;;
        --scenario|-s) SCENARIO="$2"; shift ;;
        --model|-m) MODEL="$2"; shift ;;
        --verbose|-v) VERBOSE="-v" ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo
            echo "Options:"
            echo "  --dry-run, -n     Show what would run without executing"
            echo "  --scenario, -s    Run specific scenario"
            echo "  --model, -m       Use specific model (default: claude-3-5-haiku-20241022)"
            echo "  --verbose, -v     Show detailed output"
            echo "  --help, -h        Show this help"
            echo
            echo "Available scenarios:"
            uv run python main.py --list 2>/dev/null | grep "^  [a-z]" || true
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

# Build command
CMD="uv run python main.py --model $MODEL $VERBOSE"

if [ "$DRY_RUN" = true ]; then
    CMD="$CMD --dry-run"
fi

if [ -n "$SCENARIO" ]; then
    CMD="$CMD --scenario $SCENARIO"
fi

# Run scenarios
echo -e "${YELLOW}Running scenarios with $MODEL...${NC}"
echo
eval $CMD

# Show analytics summary
if [ -f ".agentic/analytics/events.jsonl" ]; then
    echo
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}Analytics Events:${NC}"
    EVENT_COUNT=$(wc -l < .agentic/analytics/events.jsonl | tr -d ' ')
    echo "  Total events: $EVENT_COUNT"
    echo "  File: .agentic/analytics/events.jsonl"
    echo
    echo "  Event types:"
    cat .agentic/analytics/events.jsonl | jq -r '.event_type' 2>/dev/null | sort | uniq -c | sort -rn | head -10 || echo "  (jq not installed - cannot parse events)"
    echo
    
    # Validate events
    echo -e "${YELLOW}Validating events...${NC}"
    if uv run python validate_events.py 2>/dev/null; then
        echo -e "${GREEN}✓${NC} All events valid"
    else
        echo -e "${YELLOW}⚠${NC} Some events may have issues"
    fi
fi

echo
echo -e "${GREEN}Demo complete!${NC}"
echo
echo "Next steps:"
echo "  - View events: cat .agentic/analytics/events.jsonl | jq"
echo "  - Run specific scenario: ./demo.sh --scenario create-file"
echo "  - Use different model: ./demo.sh --model claude-sonnet-4-5-20250929"

