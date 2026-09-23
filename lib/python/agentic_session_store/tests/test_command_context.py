"""Claude parent context preserves tool inputs and never grants permission."""

import json
import os
import subprocess

import pytest

from agentic_session_store.command_context import command_context


@pytest.mark.parametrize("nested", [False, True])
def test_opaque_parent_is_quoted_and_input_fields_survive(nested):
    parent = "id'; printf INJECTED; #"
    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "session_id": parent,
        "tool_input": {
            "command": 'printf "%s" "$AGENTIC_PARENT_NATIVE_ID"',
            "timeout": 3000,
        },
    }
    if nested:
        event["agent_id"] = parent
    result = command_context(
        json.dumps(event).encode(),
        {
            "AGENTIC_SESSION_STORE_PROVIDER": "local",
            "AGENTIC_SESSION_STORE_PARTITION": "run",
        },
    )
    output = result["hookSpecificOutput"]
    assert "permissionDecision" not in output
    assert output["updatedInput"]["timeout"] == 3000
    execution = subprocess.run(
        ["sh", "-c", output["updatedInput"]["command"]],
        capture_output=True,
        text=True,
        check=True,
        env=os.environ,
    )
    assert execution.stdout == ("agent-" + parent if nested else parent)
