#!/bin/bash
# Build and install security hooks for Claude Agent SDK integration
# 
# This script copies hooks from the 000-claude-integration example
# which already has tested, working security hooks.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_HOOKS="${SCRIPT_DIR}/../000-claude-integration/.claude/hooks"
TARGET_DIR="${SCRIPT_DIR}/.claude/hooks"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Building Security Hooks for 001-claude-agent-sdk-integration  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo

# Check source exists
if [ ! -d "$SOURCE_HOOKS" ]; then
    echo "❌ Error: Source hooks not found at $SOURCE_HOOKS"
    echo "   Run this from the 001-claude-agent-sdk-integration directory"
    exit 1
fi

# Create target directory structure
echo "📁 Creating hook directories..."
mkdir -p "$TARGET_DIR/security"
mkdir -p "$TARGET_DIR/analytics"

# Copy security hooks
echo "📋 Copying security hooks..."
cp -f "$SOURCE_HOOKS/security/bash-validator.py" "$TARGET_DIR/security/"
cp -f "$SOURCE_HOOKS/security/bash-validator.impl.py" "$TARGET_DIR/security/"
cp -f "$SOURCE_HOOKS/security/file-security.py" "$TARGET_DIR/security/"
cp -f "$SOURCE_HOOKS/security/file-security.impl.py" "$TARGET_DIR/security/"
cp -f "$SOURCE_HOOKS/security/prompt-filter.py" "$TARGET_DIR/security/"
cp -f "$SOURCE_HOOKS/security/prompt-filter.impl.py" "$TARGET_DIR/security/"

# Copy analytics hook
echo "📋 Copying analytics hook..."
cp -f "$SOURCE_HOOKS/analytics/analytics-collector.py" "$TARGET_DIR/analytics/"

# Make hooks executable
echo "🔧 Making hooks executable..."
chmod +x "$TARGET_DIR/security/"*.py
chmod +x "$TARGET_DIR/analytics/"*.py

# Verify hooks
echo
echo "✅ Hooks installed:"
echo "   Security:"
for hook in "$TARGET_DIR/security/"*.py; do
    if [[ ! "$hook" == *".impl.py" ]]; then
        echo "     - $(basename "$hook")"
    fi
done
echo "   Analytics:"
for hook in "$TARGET_DIR/analytics/"*.py; do
    echo "     - $(basename "$hook")"
done

echo
echo "🔑 Hook Configuration:"
echo "   Settings file: .claude/settings.json"
echo "   Hooks dir: .claude/hooks/"
echo
echo "✨ Done! Hooks ready for use with Claude Agent SDK."

