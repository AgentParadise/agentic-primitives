#!/usr/bin/env bash
# Test script for Claude Code hooks integration
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

EXAMPLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURES_DIR="$EXAMPLE_DIR/fixtures"
HOOKS_DIR="$EXAMPLE_DIR/.claude/hooks"

echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo -e "${BLUE}  Claude Code Hooks Integration Test${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo ""

# Function to test a hook
test_hook() {
    local hook_name="$1"
    local hook_path="$2"
    local fixture="$3"
    local expected="$4"
    
    echo -e "${YELLOW}Testing:${NC} $hook_name"
    echo -e "${YELLOW}Fixture:${NC} $(basename $fixture)"
    
    if [ ! -f "$hook_path" ]; then
        echo -e "${RED}✗ Hook not found:${NC} $hook_path"
        return 1
    fi
    
    if [ ! -f "$fixture" ]; then
        echo -e "${RED}✗ Fixture not found:${NC} $fixture"
        return 1
    fi
    
    # Run hook with fixture
    local output
    if output=$(cat "$fixture" | "$hook_path" 2>&1); then
        echo -e "${GREEN}✓ Hook executed successfully${NC}"
        
        # Try to parse as JSON and show decision
        if echo "$output" | jq -e . >/dev/null 2>&1; then
            local decision=$(echo "$output" | jq -r '.decision // "allow"')
            echo -e "${BLUE}Decision:${NC} $decision"
            
            if [ "$decision" = "$expected" ]; then
                echo -e "${GREEN}✓ Expected decision: $expected${NC}"
            else
                echo -e "${RED}✗ Expected $expected, got $decision${NC}"
            fi
        else
            echo -e "${YELLOW}Output (non-JSON):${NC}"
            echo "$output" | head -5
        fi
    else
        echo -e "${RED}✗ Hook execution failed${NC}"
        echo "$output" | head -10
        return 1
    fi
    
    echo ""
}

echo -e "${BLUE}--- Bash Validator Tests ---${NC}"
echo ""

test_hook \
    "bash-validator (dangerous)" \
    "$HOOKS_DIR/security/bash-validator.py" \
    "$FIXTURES_DIR/dangerous-bash.json" \
    "block"

test_hook \
    "bash-validator (safe)" \
    "$HOOKS_DIR/security/bash-validator.py" \
    "$FIXTURES_DIR/safe-bash.json" \
    "allow"

echo -e "${BLUE}--- File Security Tests ---${NC}"
echo ""

test_hook \
    "file-security (sensitive)" \
    "$HOOKS_DIR/security/file-security.py" \
    "$FIXTURES_DIR/sensitive-file.json" \
    "block"

test_hook \
    "file-security (normal)" \
    "$HOOKS_DIR/security/file-security.py" \
    "$FIXTURES_DIR/normal-file.json" \
    "allow"

echo -e "${BLUE}--- Prompt Filter Tests ---${NC}"
echo ""

test_hook \
    "prompt-filter (PII)" \
    "$HOOKS_DIR/security/prompt-filter.py" \
    "$FIXTURES_DIR/pii-prompt.json" \
    "allow"  # Allow with warning

test_hook \
    "prompt-filter (normal)" \
    "$HOOKS_DIR/security/prompt-filter.py" \
    "$FIXTURES_DIR/normal-prompt.json" \
    "allow"

echo -e "${BLUE}--- Universal Collector Tests ---${NC}"
echo ""

test_hook \
    "hooks-collector (bash)" \
    "$HOOKS_DIR/core/hooks-collector.py" \
    "$FIXTURES_DIR/dangerous-bash.json" \
    "allow"  # Never blocks

test_hook \
    "hooks-collector (prompt)" \
    "$HOOKS_DIR/core/hooks-collector.py" \
    "$FIXTURES_DIR/pii-prompt.json" \
    "allow"  # Never blocks

echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}  All tests completed!${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"


