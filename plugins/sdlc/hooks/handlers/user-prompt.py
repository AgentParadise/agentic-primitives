#!/usr/bin/env python3
"""
UserPromptSubmit Handler - Validates user prompts before submission.

This handler:
1. Receives UserPromptSubmit events from Claude
2. Runs prompt validators (PII detection, etc.)
3. Emits events to stderr (captured by agent runner)
4. Returns allow/block decision
"""

import json
import os
import sys
from pathlib import Path

# === VALIDATOR COMPOSITION ===
# Validators to run on user prompts
PROMPT_VALIDATORS: list[str] = [
    "prompt.pii",
]

# === EVENT EMITTER (lazy initialized) ===
_emitter = None


def _get_emitter(session_id: str | None = None):
    """Get event emitter, creating if needed.

    Events are emitted to STDERR so they don't interfere with the
    hook decision output (which goes to STDOUT for Claude CLI).
    """
    global _emitter
    if _emitter is not None:
        return _emitter

    try:
        from agentic_events import EventEmitter

        _emitter = EventEmitter(
            session_id=session_id or os.getenv("CLAUDE_SESSION_ID", "unknown"),
            provider="claude",
            output=sys.stderr,  # Events to stderr, decision to stdout
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


def run_validators(prompt: str, context: dict) -> dict:
    """Run all prompt validators, return first failure or success."""
    validators_dir = Path(__file__).parent.parent / "validators"
    validators_run = []

    for validator_name in PROMPT_VALIDATORS:
        module = load_validator(validator_name, validators_dir)
        if module and hasattr(module, "validate"):
            validators_run.append(validator_name)
            # For prompt validators, we pass the prompt as tool_input
            result = module.validate({"prompt": prompt}, context)
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
            return  # No output = allow

        event = json.loads(input_data)

        # Extract prompt - could be in different fields
        prompt = event.get("prompt", event.get("message", event.get("content", "")))
        session_id = event.get("session_id")
        context = {
            "session_id": session_id,
            "hook_event_name": event.get("hook_event_name", "UserPromptSubmit"),
        }

        # Get emitter
        emitter = _get_emitter(session_id)

        # Run validators
        result = run_validators(prompt, context)
        decision = "block" if not result.get("safe", True) else "allow"

        # Emit security decision
        if emitter:
            emitter.security_decision(
                tool_name="UserPromptSubmit",
                decision=decision,
                reason=result.get("reason", ""),
                validators=result.get("validators_run", []),
            )

        # Only output when blocking - no output means allow
        if decision == "block":
            print(
                json.dumps(
                    {
                        "decision": "block",
                        "reason": result.get("reason", "Blocked by prompt validator"),
                    }
                )
            )

    except Exception:
        pass  # Fail open - no output means allow


if __name__ == "__main__":
    main()
