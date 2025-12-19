#!/usr/bin/env python3
"""
PreToolUse Handler - Routes tool validation to atomic validators.

This handler:
1. Receives PreToolUse events from Claude
2. Determines which validators to run based on tool_name
3. Calls validators in-process (no subprocess)
4. Emits events to stdout (captured by agent runner)
5. Returns allow/block decision

Events are emitted as JSONL to stdout, captured by the agent runner
and stored in TimescaleDB for observability.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

# === VALIDATOR COMPOSITION ===
# Map tool names to validator modules
TOOL_VALIDATORS: dict[str, list[str]] = {
    "Bash": ["security.bash"],
    "Write": ["security.file"],
    "Edit": ["security.file"],
    "Read": ["security.file"],
    "MultiEdit": ["security.file"],
}

# === EVENT EMITTER (lazy initialized) ===
_emitter = None


def _get_emitter(session_id: str | None = None):
    """Get event emitter, creating if needed."""
    global _emitter
    if _emitter is not None:
        return _emitter

    try:
        from agentic_events import EventEmitter

        _emitter = EventEmitter(
            session_id=session_id or os.getenv("CLAUDE_SESSION_ID", "unknown"),
            provider="claude",
        )
        return _emitter
    except ImportError:
        return None


def load_validator(validator_name: str, validators_dir: Path):
    """Dynamically load a validator module."""
    module_path = validators_dir / (validator_name.replace(".", "/") + ".py")

    if not module_path.exists():
        return None

    import importlib.util

    spec = importlib.util.spec_from_file_location(validator_name, module_path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    return None


def run_validators(tool_name: str, tool_input: dict, context: dict) -> dict:
    """Run all validators for a tool, return first failure or success."""
    validator_names = TOOL_VALIDATORS.get(tool_name, [])

    if not validator_names:
        return {"safe": True, "reason": None, "validators_run": []}

    validators_dir = Path(__file__).parent.parent / "validators"
    validators_run = []

    for validator_name in validator_names:
        module = load_validator(validator_name, validators_dir)
        if module and hasattr(module, "validate"):
            validators_run.append(validator_name)
            result = module.validate(tool_input, context)
            if not result.get("safe", True):
                result["validators_run"] = validators_run
                return result

    return {"safe": True, "reason": None, "validators_run": validators_run}


def main() -> None:
    """Main entry point."""
    try:
        # Read event from stdin
        input_data = ""
        if not sys.stdin.isatty():
            input_data = sys.stdin.read()

        if not input_data:
            print(json.dumps({"decision": "allow"}))
            return

        event = json.loads(input_data)

        # Extract fields
        tool_name = event.get("tool_name", "")
        tool_input = event.get("tool_input", {})
        session_id = event.get("session_id")
        tool_use_id = event.get("tool_use_id", "unknown")

        context = {
            "session_id": session_id,
            "tool_use_id": tool_use_id,
            "hook_event_name": event.get("hook_event_name", "PreToolUse"),
        }

        # Get emitter and emit tool started event
        emitter = _get_emitter(session_id)
        if emitter:
            emitter.tool_started(
                tool_name=tool_name,
                tool_use_id=tool_use_id,
                input_preview=json.dumps(tool_input)[:500] if tool_input else "",
            )

        # Run validators
        result = run_validators(tool_name, tool_input, context)
        decision = "block" if not result.get("safe", True) else "allow"

        # Emit security decision
        if emitter:
            emitter.security_decision(
                tool_name=tool_name,
                decision=decision,
                reason=result.get("reason", ""),
                validators=result.get("validators_run", []),
                tool_use_id=tool_use_id,
            )

        # Output response
        response: dict[str, Any] = {"decision": decision}
        if result.get("reason"):
            response["reason"] = result["reason"]

        print(json.dumps(response))

    except Exception as e:
        # Fail open - allow on error
        print(json.dumps({"decision": "allow", "error": str(e)}))


if __name__ == "__main__":
    main()
