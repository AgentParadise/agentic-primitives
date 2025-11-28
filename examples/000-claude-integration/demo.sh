#!/usr/bin/env bash
# Demo script for Claude Code hooks integration

set -e

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo -e "${BLUE}  Claude Code Hooks Integration Demo${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo ""

# Check if hooks are installed
if [ ! -d ".claude/hooks" ]; then
    echo -e "${YELLOW}⚠️  Hooks not found. Building...${NC}"
    cd ../..
    cargo run --manifest-path cli/Cargo.toml -- build --provider claude
    cp -r build/claude/.claude examples/000-claude-integration/
    cd examples/000-claude-integration
    echo -e "${GREEN}✓ Hooks installed${NC}"
    echo ""
fi

echo -e "${BLUE}Running all scenarios...${NC}"
echo ""

uv run python main.py --scenario all

echo ""
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}  Demo Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo ""
echo "To test specific scenarios:"
echo "  uv run python main.py --scenario dangerous-bash"
echo "  uv run python main.py --scenario sensitive-file"
echo "  uv run python main.py --scenario pii-prompt"
echo ""
echo "To test with specific hooks:"
echo "  uv run python main.py --hook bash-validator"
echo "  uv run python main.py --hook file-security"
echo ""
echo "For REAL Claude Code integration:"
echo "1. Copy .claude/ to your VS Code project"
echo "2. Open in VS Code/Cursor with Claude Code"
echo "3. Ask Claude to run commands"
echo "4. Watch hooks fire in real-time!"


