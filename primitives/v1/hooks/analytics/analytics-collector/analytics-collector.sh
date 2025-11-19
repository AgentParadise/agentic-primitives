#!/bin/bash
# Analytics Collector Hook Wrapper
# This script wraps the Python implementation for Claude Code compatibility

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Get the base name of this script (without .sh extension)
HOOK_ID="$(basename "$0" .sh)"

# Path to the Python implementation (look for both patterns)
if [ -f "$SCRIPT_DIR/impl.python.py" ]; then
    PYTHON_IMPL="$SCRIPT_DIR/impl.python.py"
elif [ -f "$SCRIPT_DIR/${HOOK_ID}.impl.python.py" ]; then
    PYTHON_IMPL="$SCRIPT_DIR/${HOOK_ID}.impl.python.py"
else
    echo "{\"status\":\"error\",\"message\":\"Python implementation not found in $SCRIPT_DIR\"}" >&2
    exit 0  # Exit 0 to not block agent
fi

# Execute the Python implementation
# Pass stdin through to the Python script
python3 "$PYTHON_IMPL"

