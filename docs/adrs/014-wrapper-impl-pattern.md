# ADR-014: Atomic Hook Architecture

**Status:** Accepted (Revision 2)  
**Date:** 2025-11-27  
**Decision Makers:** Core Team  
**Supersedes:** Original ADR-014 (Wrapper+Impl Pattern)

## Context

The original Wrapper+Impl pattern attempted to solve configuration injection and subprocess optimization but introduced new problems:

### Why Wrapper+Impl Failed

```
┌─────────────────────────────────────────────────────────────────────────┐
│  The Wrapper+Impl Pattern                                               │
│                                                                         │
│  ┌──────────────┐     spawn      ┌──────────────┐                      │
│  │ Claude Agent │ ──────────────▶│ wrapper.py   │                      │
│  └──────────────┘                └──────┬───────┘                      │
│                                         │ import                        │
│                                         ▼                               │
│                                  ┌──────────────┐                      │
│                                  │ impl.py      │                      │
│                                  │              │                      │
│                                  │ import ───────▶ agentic_analytics   │
│                                  │              │          ❌ FAILS     │
│                                  └──────────────┘                      │
│                                                                         │
│  Problems:                                                              │
│  1. Subprocess has different Python environment                        │
│  2. Editable installs don't persist across subprocess boundaries       │
│  3. Import failures are silent (hooks return JSON but don't log)       │
│  4. Two files per hook = complexity for no real benefit                │
└─────────────────────────────────────────────────────────────────────────┘
```

**Root Cause:** Python packaging is unreliable across subprocess boundaries. When Claude spawns a hook, the subprocess may:
- Use a different Python interpreter
- Have different `sys.path` entries
- Not see editable installs from the parent environment
- Fail silently when imports don't resolve

## Decision

Replace the two-file pattern with an **Atomic Hook Architecture**:

```
.claude/hooks/
  │
  ├── handlers/                     # Entry points (3 files)
  │   ├── pre-tool-use.py           # Routes PreToolUse events
  │   ├── post-tool-use.py          # Handles PostToolUse events
  │   └── user-prompt.py            # Handles UserPromptSubmit events
  │
  └── validators/                   # Pure validation functions
      ├── security/
      │   ├── bash.py               # Validates shell commands
      │   └── file.py               # Validates file operations
      │
      └── prompt/
          └── pii.py                # Detects PII patterns
```

### Core Principles

1. **No External Package Dependencies** - Hooks use Python stdlib only
2. **Handlers Compose Validators** - Single entry point per event type
3. **Validators Are Pure Functions** - Input → Validation → Output
4. **Inline Analytics** - 6 lines of code, not a package import
5. **In-Process Imports** - Validators imported dynamically, no subprocess

### Architecture Diagram

```
Claude Event (stdin JSON)
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Handler (e.g., pre-tool-use.py)                                │
│                                                                 │
│  1. Parse event from stdin                                      │
│  2. Route to validators based on tool_name                      │
│  3. Import validators in-process (importlib.util)               │
│  4. Call validate() functions                                   │
│  5. Aggregate results                                           │
│  6. Log to analytics (inline, no imports)                       │
│  7. Output decision to stdout                                   │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
   JSON Response (stdout)
```

### Handler Responsibilities

| Responsibility | Implementation |
|----------------|----------------|
| Parse stdin JSON | `json.loads(sys.stdin.read())` |
| Route to validators | `TOOL_VALIDATORS` mapping |
| Call validators | `importlib.util.spec_from_file_location()` |
| Aggregate decisions | First failure or success |
| Log to analytics | Inline file append (6 lines) |
| Output to stdout | `print(json.dumps(response))` |

### Validator Contract

Each validator exports a single `validate()` function:

```python
def validate(tool_input: dict, context: dict | None = None) -> dict:
    """
    Args:
        tool_input: The tool_input from the hook event
        context: Optional context (session_id, tool_name, etc.)
    
    Returns:
        {
            "safe": bool,
            "reason": str | None,      # Required if safe=False
            "metadata": dict | None    # Optional extra data
        }
    """
```

**Validators MUST:**
- Be pure functions (no side effects)
- Use only Python stdlib
- Return the standard response format
- Be testable standalone

**Validators MUST NOT:**
- Import external packages
- Read/write files
- Make network calls
- Log to analytics (handlers do this)

### Inline Analytics

Analytics logging is embedded directly in handlers (no package import):

```python
def log_analytics(event: dict) -> None:
    """Log to analytics file. Fail-safe - never blocks."""
    try:
        path = Path(os.getenv("ANALYTICS_PATH", ".agentic/analytics/events.jsonl"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps({"timestamp": datetime.now(UTC).isoformat(), **event}) + "\n")
    except Exception:
        pass  # Never block on analytics failure
```

This eliminates the need for `agentic_analytics` package imports in hooks.

## Consequences

### Positive

✅ **Reliability** - No import failures across subprocess boundaries  
✅ **Simplicity** - Single entry point per event type (3 handlers vs N wrappers)  
✅ **Testability** - Validators are pure functions, easily unit tested  
✅ **Composability** - Handlers can mix-and-match validators  
✅ **Zero Dependencies** - Python stdlib only, works anywhere  
✅ **Debuggability** - Clear stack traces, no wrapper→runpy→impl layers

### Negative

⚠️ **Validator Discovery** - Handlers must know validator locations  
⚠️ **Manual Routing** - Must update `TOOL_VALIDATORS` map for new validators

### Comparison

| Aspect | Wrapper+Impl | Atomic |
|--------|--------------|--------|
| Files per hook | 2 (wrapper + impl) | 1 (validator) |
| Entry points | N (one per hook) | 3 (one per event type) |
| Package deps | Required (agentic_analytics) | None (stdlib only) |
| Analytics | Package import | Inline (6 lines) |
| Import reliability | ❌ Fails in subprocess | ✅ In-process |
| Testing | Complex (mock subprocess) | Simple (call function) |

## Implementation

### Handler Template

```python
#!/usr/bin/env python3
"""PreToolUse Handler - Routes tool validation to atomic validators."""

import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

TOOL_VALIDATORS = {
    "Bash": ["security.bash"],
    "Write": ["security.file"],
    "Edit": ["security.file"],
    "Read": ["security.file"],
}

def log_analytics(event: dict) -> None:
    try:
        path = Path(os.getenv("ANALYTICS_PATH", ".agentic/analytics/events.jsonl"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps({"timestamp": datetime.now(UTC).isoformat(), **event}) + "\n")
    except Exception:
        pass

def run_validators(tool_name: str, tool_input: dict, context: dict) -> dict:
    validators_dir = Path(__file__).parent.parent / "validators"
    for validator_name in TOOL_VALIDATORS.get(tool_name, []):
        module_path = validators_dir / (validator_name.replace(".", "/") + ".py")
        if module_path.exists():
            import importlib.util
            spec = importlib.util.spec_from_file_location(validator_name, module_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                result = module.validate(tool_input, context)
                if not result.get("safe", True):
                    return result
    return {"safe": True}

def main():
    try:
        event = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}
        tool_name = event.get("tool_name", "")
        tool_input = event.get("tool_input", {})
        context = {
            "session_id": event.get("session_id"),
            "tool_use_id": event.get("tool_use_id"),
        }
        
        result = run_validators(tool_name, tool_input, context)
        decision = "block" if not result.get("safe", True) else "allow"
        
        log_analytics({
            "event_type": "hook_decision",
            "handler": "pre-tool-use",
            "tool_name": tool_name,
            "decision": decision,
            "reason": result.get("reason"),
            "tool_use_id": context.get("tool_use_id"),
        })
        
        print(json.dumps({"decision": decision, "reason": result.get("reason")}))
    except Exception as e:
        print(json.dumps({"decision": "allow", "error": str(e)}))

if __name__ == "__main__":
    main()
```

### Validator Template

```python
#!/usr/bin/env python3
"""Bash Command Validator - Checks for dangerous patterns."""

import re

DANGEROUS_PATTERNS = [
    (r'\brm\s+-rf\s+/', "rm -rf / (root deletion)"),
    (r'\bdd\s+if=.*of=/dev/', "disk overwrite"),
    (r'\bcurl.*\|\s*bash', "curl pipe to bash"),
]

def validate(tool_input: dict, context: dict | None = None) -> dict:
    command = tool_input.get("command", "")
    for pattern, description in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return {"safe": False, "reason": f"Blocked: {description}"}
    return {"safe": True}

if __name__ == "__main__":
    import json, sys
    print(json.dumps(validate(json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {})))
```

### Build Output

```
build/claude/.claude/hooks/
├── handlers/
│   ├── pre-tool-use.py
│   ├── post-tool-use.py
│   └── user-prompt.py
└── validators/
    ├── security/
    │   ├── bash.py
    │   └── file.py
    └── prompt/
        └── pii.py
```

### Settings.json

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": ["$CLAUDE_PROJECT_DIR/.claude/hooks/handlers/pre-tool-use.py"]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": ["$CLAUDE_PROJECT_DIR/.claude/hooks/handlers/post-tool-use.py"]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": ["$CLAUDE_PROJECT_DIR/.claude/hooks/handlers/user-prompt.py"]
      }
    ]
  }
}
```

## Migration

### Files Removed
- `cli/src/templates/hook_wrapper.py.template`
- `cli/src/templates/hook_wrapper_with_config.py.template`
- All `*.impl.py` files in examples
- All individual hook wrapper files

### Files Added
- `primitives/v1/hooks/handlers/*.py`
- `primitives/v1/hooks/validators/**/*.py`

### Build System Changes
- Removed: `generate_python_wrapper()` functions
- Added: `copy_handlers()` and `copy_validators()` functions
- Simplified: Direct file copy instead of template rendering

## References

- [ADR-013: Hybrid Hook Architecture](./013-hybrid-hook-architecture.md)
- [ADR-016: Hook Event Correlation](./016-hook-event-correlation.md)
- [Python importlib.util](https://docs.python.org/3/library/importlib.html#importlib.util.spec_from_file_location)

## Revision History

- **2025-11-27**: Revision 2 - Replaced with Atomic Hook Architecture
- **2025-11-25**: Revision 1 - Original Wrapper+Impl pattern (deprecated)
