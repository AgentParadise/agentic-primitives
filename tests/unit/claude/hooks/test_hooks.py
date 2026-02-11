#!/usr/bin/env python3
"""
Comprehensive tests for Claude Code hook handlers (Plugin Architecture).

Covers:
- sdlc handlers: pre-tool-use, user-prompt (security + PII validation)
- workspace handlers: all 8 observability handlers (never block)
- Error paths: malformed JSON, empty input, missing fields
- Output format validation: hookSpecificOutput, decision fields
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


# ============================================================================
# Test Infrastructure
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
SDLC_PLUGIN = PROJECT_ROOT / "plugins" / "sdlc"
WORKSPACE_PLUGIN = PROJECT_ROOT / "plugins" / "workspace"
VALIDATORS_DIR = SDLC_PLUGIN / "hooks" / "validators"
SDLC_HANDLERS = SDLC_PLUGIN / "hooks" / "handlers"
WORKSPACE_HANDLERS = WORKSPACE_PLUGIN / "hooks" / "handlers"


def load_validator(name: str):
    """Load a validator module by name (e.g., 'security/bash' or 'prompt/pii')"""
    parts = name.split("/")
    if len(parts) == 2:
        module_path = VALIDATORS_DIR / parts[0] / f"{parts[1]}.py"
    else:
        module_path = VALIDATORS_DIR / f"{name}.py"

    if not module_path.exists():
        pytest.skip(f"Validator not found: {module_path}")

    spec = importlib.util.spec_from_file_location(name.replace("/", "_"), module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_handler(
    handler_name: str,
    event: dict[str, Any] | str | None = None,
    timeout: int = 5,
    handler_dir: Path = SDLC_HANDLERS,
) -> dict:
    """Run a handler script with an event and return the parsed output.

    Claude Code hook output contract:
    - No stdout output = allow (implicit)
    - JSON stdout with block/deny = block

    Args:
        handler_name: Name of handler file (without .py)
        event: Dict (JSON-serialized), raw string, or None for empty input
        timeout: Subprocess timeout
        handler_dir: Directory containing the handler
    """
    handler_path = handler_dir / f"{handler_name}.py"

    if not handler_path.exists():
        pytest.skip(f"Handler not found: {handler_path}")

    # Prepare input
    if event is None:
        input_bytes = b""
    elif isinstance(event, str):
        input_bytes = event.encode()
    else:
        input_bytes = json.dumps(event).encode()

    result = subprocess.run(
        [sys.executable, str(handler_path)],
        input=input_bytes,
        capture_output=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        return {
            "error": f"Handler failed with code {result.returncode}",
            "stderr": result.stderr.decode(),
        }

    stdout = result.stdout.decode().strip()
    if not stdout:
        # No output = implicit allow (Claude Code convention)
        return {"_allowed": True}

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"_raw_output": stdout, "_allowed": True}


def is_allowed(result: dict) -> bool:
    """Check if a hook result indicates allow (no output or no block decision)."""
    if result.get("_allowed"):
        return True
    # Check hookSpecificOutput (PreToolUse format)
    hso = result.get("hookSpecificOutput", {})
    if hso.get("permissionDecision") == "deny":
        return False
    # Check top-level decision (UserPromptSubmit/Stop format)
    if result.get("decision") == "block":
        return False
    return True


def is_blocked(result: dict) -> bool:
    """Check if a hook result indicates block/deny."""
    return not is_allowed(result)


# ============================================================================
# Validator Unit Tests (quick smoke tests — comprehensive tests in test_redaction.py)
# ============================================================================


class TestBashValidator:
    """Smoke tests for security/bash validator"""

    @pytest.fixture
    def validator(self):
        return load_validator("security/bash")

    def test_dangerous_command_blocked(self, validator):
        result = validator.validate({"command": "rm -rf /"})
        assert result["safe"] is False

    def test_safe_command_allowed(self, validator):
        result = validator.validate({"command": "ls -la"})
        assert result["safe"] is True


class TestFileValidator:
    """Smoke tests for security/file validator"""

    @pytest.fixture
    def validator(self):
        return load_validator("security/file")

    def test_blocked_path_rejected(self, validator):
        result = validator.validate({"file_path": "/etc/passwd", "command": "Write"})
        assert result["safe"] is False

    def test_normal_file_allowed(self, validator):
        result = validator.validate({"file_path": "src/main.py", "content": "print('Hello')"})
        assert result["safe"] is True


class TestPIIValidator:
    """Smoke tests for prompt/pii validator"""

    @pytest.fixture
    def validator(self):
        return load_validator("prompt/pii")

    def test_ssn_detected(self, validator):
        result = validator.validate({"prompt": "My SSN is 123-45-6789"})
        assert result["safe"] is False

    def test_normal_prompt_allowed(self, validator):
        result = validator.validate({"prompt": "Write a Python script"})
        assert result["safe"] is True


# ============================================================================
# SDLC PreToolUse Handler Tests
# ============================================================================


class TestPreToolUseHandler:
    """Comprehensive tests for sdlc pre-tool-use handler"""

    def test_dangerous_bash_blocked(self):
        event = {
            "session_id": "test-001",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
            "tool_use_id": "toolu_test_001",
        }
        result = run_handler("pre-tool-use", event, handler_dir=SDLC_HANDLERS)
        assert is_blocked(result), f"Expected block, got: {result}"

    def test_safe_bash_allowed(self):
        event = {
            "session_id": "test-002",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "tool_use_id": "toolu_test_002",
        }
        result = run_handler("pre-tool-use", event, handler_dir=SDLC_HANDLERS)
        assert is_allowed(result), f"Expected allow, got: {result}"

    def test_sensitive_file_write_blocked(self):
        event = {
            "session_id": "test-003",
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": ".env", "content": "SECRET=value"},
            "tool_use_id": "toolu_test_003",
        }
        result = run_handler("pre-tool-use", event, handler_dir=SDLC_HANDLERS)
        assert is_blocked(result), f"Expected block, got: {result}"

    def test_block_output_format(self):
        """Blocked result should have correct hookSpecificOutput structure"""
        event = {
            "session_id": "test-fmt",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
            "tool_use_id": "toolu_fmt",
        }
        result = run_handler("pre-tool-use", event, handler_dir=SDLC_HANDLERS)
        assert "hookSpecificOutput" in result
        hso = result["hookSpecificOutput"]
        assert hso["permissionDecision"] == "deny"
        assert "permissionDecisionReason" in hso
        assert len(hso["permissionDecisionReason"]) > 0

    def test_unknown_tool_allowed(self):
        """Tools not in TOOL_VALIDATORS should be implicitly allowed"""
        event = {
            "session_id": "test-unk",
            "tool_name": "UnknownTool",
            "tool_input": {"data": "anything"},
            "tool_use_id": "toolu_unk",
        }
        result = run_handler("pre-tool-use", event, handler_dir=SDLC_HANDLERS)
        assert is_allowed(result)

    def test_empty_input_allows(self):
        """Empty stdin should result in implicit allow"""
        result = run_handler("pre-tool-use", None, handler_dir=SDLC_HANDLERS)
        assert is_allowed(result)

    def test_malformed_json_allows(self):
        """Malformed JSON should fail open (implicit allow)"""
        result = run_handler("pre-tool-use", "{not valid json", handler_dir=SDLC_HANDLERS)
        assert is_allowed(result)

    def test_missing_tool_name_allows(self):
        """Missing tool_name field should be treated as unknown tool"""
        event = {"session_id": "test-missing", "tool_input": {"command": "rm -rf /"}}
        result = run_handler("pre-tool-use", event, handler_dir=SDLC_HANDLERS)
        assert is_allowed(result)

    def test_missing_tool_input_allows(self):
        """Missing tool_input should be safe (empty dict)"""
        event = {"session_id": "test-noinput", "tool_name": "Bash"}
        result = run_handler("pre-tool-use", event, handler_dir=SDLC_HANDLERS)
        assert is_allowed(result)

    def test_edit_tool_sensitive_file_blocked(self):
        """Edit tool should also check file validators"""
        event = {
            "session_id": "test-edit",
            "tool_name": "Edit",
            "tool_input": {"file_path": ".env", "content": "SECRET=x"},
            "tool_use_id": "toolu_edit",
        }
        result = run_handler("pre-tool-use", event, handler_dir=SDLC_HANDLERS)
        assert is_blocked(result)

    def test_read_tool_sensitive_file_blocked(self):
        """Read tool on sensitive file currently blocks (handler doesn't pass tool_name to validator context)"""
        event = {
            "session_id": "test-read",
            "tool_name": "Read",
            "tool_input": {"file_path": ".env"},
            "tool_use_id": "toolu_read",
        }
        result = run_handler("pre-tool-use", event, handler_dir=SDLC_HANDLERS)
        # NOTE: The file validator supports Read vs Write differentiation via context["tool_name"],
        # but the pre-tool-use handler doesn't currently pass tool_name in the context dict.
        # This means .env reads are blocked just like writes. Future improvement: pass tool_name in context.
        assert is_blocked(result)


# ============================================================================
# SDLC UserPromptSubmit Handler Tests
# ============================================================================


class TestUserPromptHandler:
    """Comprehensive tests for sdlc user-prompt handler (PII validation)"""

    def test_pii_ssn_blocked(self):
        event = {
            "session_id": "test-004",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "My SSN is 123-45-6789 please use it",
        }
        result = run_handler("user-prompt", event, handler_dir=SDLC_HANDLERS)
        assert is_blocked(result), f"SSN should be blocked, got: {result}"

    def test_pii_credit_card_blocked(self):
        event = {
            "session_id": "test-cc",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "My card is 4111111111111111",
        }
        result = run_handler("user-prompt", event, handler_dir=SDLC_HANDLERS)
        assert is_blocked(result), f"Credit card should be blocked, got: {result}"

    def test_normal_prompt_allowed(self):
        event = {
            "session_id": "test-005",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Write a hello world function",
        }
        result = run_handler("user-prompt", event, handler_dir=SDLC_HANDLERS)
        assert is_allowed(result), f"Expected allow, got: {result}"

    def test_block_output_format(self):
        """Blocked result should have decision and reason"""
        event = {
            "session_id": "test-fmt",
            "prompt": "My SSN is 123-45-6789",
        }
        result = run_handler("user-prompt", event, handler_dir=SDLC_HANDLERS)
        assert result.get("decision") == "block"
        assert "reason" in result
        assert len(result["reason"]) > 0

    def test_empty_input_allows(self):
        result = run_handler("user-prompt", None, handler_dir=SDLC_HANDLERS)
        assert is_allowed(result)

    def test_malformed_json_allows(self):
        result = run_handler("user-prompt", "not json{{{", handler_dir=SDLC_HANDLERS)
        assert is_allowed(result)

    def test_missing_prompt_allows(self):
        """Missing prompt field should be treated as empty prompt"""
        event = {"session_id": "test-noprompt"}
        result = run_handler("user-prompt", event, handler_dir=SDLC_HANDLERS)
        assert is_allowed(result)

    def test_prompt_from_message_field(self):
        """Should extract prompt from 'message' field as fallback"""
        event = {
            "session_id": "test-msg",
            "message": "My SSN is 123-45-6789",
        }
        result = run_handler("user-prompt", event, handler_dir=SDLC_HANDLERS)
        assert is_blocked(result), "Should detect PII in 'message' field"

    def test_prompt_from_content_field(self):
        """Should extract prompt from 'content' field as fallback"""
        event = {
            "session_id": "test-content",
            "content": "My SSN is 123-45-6789",
        }
        result = run_handler("user-prompt", event, handler_dir=SDLC_HANDLERS)
        assert is_blocked(result), "Should detect PII in 'content' field"

    def test_medium_risk_pii_allows(self):
        """Medium-risk PII (e.g., phone) should be allowed"""
        event = {
            "session_id": "test-phone",
            "prompt": "Call (555) 123-4567",
        }
        result = run_handler("user-prompt", event, handler_dir=SDLC_HANDLERS)
        assert is_allowed(result)


# ============================================================================
# Workspace Handler Tests — Never Block Contract
# ============================================================================


class TestWorkspaceUserPrompt:
    """Workspace user-prompt handler — observability only"""

    def test_never_blocks_even_with_pii(self):
        event = {
            "session_id": "test-ws-001",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "My SSN is 123-45-6789",
        }
        result = run_handler("user-prompt", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_empty_input_allows(self):
        result = run_handler("user-prompt", None, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_malformed_json_allows(self):
        result = run_handler("user-prompt", "broken{json", handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_normal_prompt_allows(self):
        event = {"session_id": "ws-normal", "prompt": "Hello world"}
        result = run_handler("user-prompt", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_missing_prompt_field_allows(self):
        event = {"session_id": "ws-noprompt"}
        result = run_handler("user-prompt", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)


class TestWorkspacePostToolUse:
    """Workspace post-tool-use handler — observability only"""

    def test_never_blocks(self):
        event = {
            "session_id": "test-ws-002",
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_response": {"output": "hello"},
            "tool_use_id": "toolu_ws_002",
        }
        result = run_handler("post-tool-use", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_error_response_allows(self):
        """Even error responses should not block"""
        event = {
            "session_id": "ws-err",
            "tool_name": "Bash",
            "tool_response": {"is_error": True, "error": "command failed"},
            "tool_use_id": "toolu_err",
        }
        result = run_handler("post-tool-use", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_empty_input_allows(self):
        result = run_handler("post-tool-use", None, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_malformed_json_allows(self):
        result = run_handler("post-tool-use", "not json", handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_string_response_allows(self):
        """String tool_response should be handled"""
        event = {
            "session_id": "ws-str",
            "tool_name": "Read",
            "tool_response": "file contents here",
            "tool_use_id": "toolu_str",
        }
        result = run_handler("post-tool-use", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)


class TestWorkspaceNotification:
    """Workspace notification handler — observability only"""

    def test_never_blocks(self):
        event = {
            "session_id": "ws-notif",
            "hook_event_name": "Notification",
            "message": "Build completed",
            "level": "info",
        }
        result = run_handler("notification", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_empty_input_allows(self):
        result = run_handler("notification", None, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_malformed_json_allows(self):
        result = run_handler("notification", "{{bad", handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_notification_field_fallback(self):
        """Should handle 'notification' field as alt to 'message'"""
        event = {
            "session_id": "ws-notif-alt",
            "notification": "Task done",
        }
        result = run_handler("notification", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_missing_fields_allows(self):
        event = {"session_id": "ws-notif-empty"}
        result = run_handler("notification", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)


class TestWorkspaceStop:
    """Workspace stop handler — observability only"""

    def test_never_blocks(self):
        event = {
            "session_id": "ws-stop",
            "hook_event_name": "Stop",
            "reason": "user_stopped",
        }
        result = run_handler("stop", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_empty_input_allows(self):
        result = run_handler("stop", None, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_malformed_json_allows(self):
        result = run_handler("stop", "broken", handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_missing_reason_allows(self):
        event = {"session_id": "ws-stop-noreason"}
        result = run_handler("stop", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)


class TestWorkspaceSubagentStop:
    """Workspace subagent-stop handler — observability only"""

    def test_never_blocks(self):
        event = {
            "session_id": "ws-sub",
            "hook_event_name": "SubagentStop",
            "subagent_id": "agent-001",
            "reason": "completed",
        }
        result = run_handler("subagent-stop", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_empty_input_allows(self):
        result = run_handler("subagent-stop", None, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_malformed_json_allows(self):
        result = run_handler("subagent-stop", "{nope", handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_missing_fields_allows(self):
        event = {"session_id": "ws-sub-empty"}
        result = run_handler("subagent-stop", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)


class TestWorkspaceSessionStart:
    """Workspace session-start handler — observability only"""

    def test_never_blocks(self):
        event = {
            "session_id": "ws-start",
            "hook_event_name": "SessionStart",
            "matcher": "startup",
            "transcript_path": "/tmp/transcript.jsonl",
            "cwd": "/home/user/project",
            "permission_mode": "default",
        }
        result = run_handler("session-start", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_empty_input_allows(self):
        result = run_handler("session-start", None, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_malformed_json_allows(self):
        result = run_handler("session-start", "bad json", handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_missing_fields_allows(self):
        event = {"session_id": "ws-start-minimal"}
        result = run_handler("session-start", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)


class TestWorkspaceSessionEnd:
    """Workspace session-end handler — observability only"""

    def test_never_blocks(self):
        event = {
            "session_id": "ws-end",
            "hook_event_name": "SessionEnd",
            "reason": "normal",
            "duration_ms": 12345,
        }
        result = run_handler("session-end", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_empty_input_allows(self):
        result = run_handler("session-end", None, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_malformed_json_allows(self):
        result = run_handler("session-end", "nope{", handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_missing_fields_allows(self):
        event = {"session_id": "ws-end-minimal"}
        result = run_handler("session-end", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)


class TestWorkspacePreCompact:
    """Workspace pre-compact handler — observability only"""

    def test_never_blocks(self):
        event = {
            "session_id": "ws-compact",
            "hook_event_name": "PreCompact",
            "before_tokens": 100000,
            "after_tokens": 50000,
        }
        result = run_handler("pre-compact", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_empty_input_allows(self):
        result = run_handler("pre-compact", None, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_malformed_json_allows(self):
        result = run_handler("pre-compact", "{{bad", handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_alt_field_names_allows(self):
        """Should handle current_tokens/target_tokens field names"""
        event = {
            "session_id": "ws-compact-alt",
            "current_tokens": 80000,
            "target_tokens": 40000,
        }
        result = run_handler("pre-compact", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_zero_tokens_allows(self):
        event = {
            "session_id": "ws-compact-zero",
            "before_tokens": 0,
            "after_tokens": 0,
        }
        result = run_handler("pre-compact", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)

    def test_missing_fields_allows(self):
        event = {"session_id": "ws-compact-empty"}
        result = run_handler("pre-compact", event, handler_dir=WORKSPACE_HANDLERS)
        assert is_allowed(result)


# ============================================================================
# Integration Tests
# ============================================================================


class TestHookIntegration:
    """Integration tests for hook interactions"""

    def test_parallel_execution_simulation(self):
        """Simulate parallel hook execution for same event"""
        event = {
            "session_id": "test-011",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
            "tool_use_id": "toolu_test_011",
        }
        result = run_handler("pre-tool-use", event, handler_dir=SDLC_HANDLERS)
        assert is_blocked(result)

    def test_both_user_prompt_handlers(self):
        """Both sdlc and workspace fire for UserPromptSubmit — sdlc blocks, workspace allows"""
        event = {
            "session_id": "test-both",
            "prompt": "My SSN is 123-45-6789",
        }
        sdlc_result = run_handler("user-prompt", event, handler_dir=SDLC_HANDLERS)
        ws_result = run_handler("user-prompt", event, handler_dir=WORKSPACE_HANDLERS)

        assert is_blocked(sdlc_result), "SDLC should block PII"
        assert is_allowed(ws_result), "Workspace should never block"

    def test_all_workspace_handlers_never_block(self):
        """Verify the never-block contract across all workspace handlers"""
        handlers_and_events = [
            ("user-prompt", {"session_id": "x", "prompt": "SSN 123-45-6789"}),
            ("post-tool-use", {"session_id": "x", "tool_name": "Bash", "tool_response": {}}),
            ("notification", {"session_id": "x", "message": "test"}),
            ("stop", {"session_id": "x", "reason": "test"}),
            ("subagent-stop", {"session_id": "x", "subagent_id": "a1"}),
            ("session-start", {"session_id": "x"}),
            ("session-end", {"session_id": "x"}),
            ("pre-compact", {"session_id": "x", "before_tokens": 100}),
        ]
        for handler_name, event in handlers_and_events:
            result = run_handler(handler_name, event, handler_dir=WORKSPACE_HANDLERS)
            assert is_allowed(result), f"Workspace {handler_name} should never block"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
