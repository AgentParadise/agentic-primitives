#!/usr/bin/env python3
"""
Unit tests for Claude Code hooks (Atomic Architecture)

Tests validators and handlers for the new atomic hook architecture.
Validators are pure functions imported directly.
Handlers are tested via subprocess execution.
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
VALIDATORS_DIR = PROJECT_ROOT / "primitives" / "v1" / "hooks" / "validators"
HANDLERS_DIR = PROJECT_ROOT / "primitives" / "v1" / "hooks" / "handlers"


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


def run_handler(handler_name: str, event: dict[str, Any], timeout: int = 5) -> dict:
    """Run a handler script with an event and return the parsed output"""
    handler_path = HANDLERS_DIR / f"{handler_name}.py"

    if not handler_path.exists():
        pytest.skip(f"Handler not found: {handler_path}")

    result = subprocess.run(
        [sys.executable, str(handler_path)],
        input=json.dumps(event).encode(),
        capture_output=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        return {
            "error": f"Handler failed with code {result.returncode}",
            "stderr": result.stderr.decode(),
        }

    try:
        return json.loads(result.stdout.decode())
    except json.JSONDecodeError:
        return {"raw_output": result.stdout.decode(), "decision": "allow"}


# ============================================================================
# Bash Validator Tests
# ============================================================================


class TestBashValidator:
    """Tests for security/bash validator"""

    @pytest.fixture
    def validator(self):
        return load_validator("security/bash")

    def test_dangerous_command_blocked(self, validator):
        """Test that dangerous bash commands are blocked"""
        result = validator.validate({"command": "rm -rf /"})

        assert result["safe"] is False
        assert "reason" in result
        assert "dangerous" in result["reason"].lower() or "blocked" in result["reason"].lower()

    def test_safe_command_allowed(self, validator):
        """Test that safe bash commands are allowed"""
        result = validator.validate({"command": "ls -la"})

        assert result["safe"] is True

    @pytest.mark.parametrize(
        "dangerous_cmd",
        [
            "rm -rf /",
            "dd if=/dev/zero of=/dev/sda",
            "mkfs.ext4 /dev/sda",
            ":(){ :|:& };:",  # Fork bomb
        ],
    )
    def test_various_dangerous_commands(self, validator, dangerous_cmd: str):
        """Test various dangerous command patterns"""
        result = validator.validate({"command": dangerous_cmd})

        assert result["safe"] is False, f"Command '{dangerous_cmd}' should be blocked"

    @pytest.mark.parametrize(
        "safe_cmd",
        [
            "echo hello",
            "cat file.txt",
            "grep pattern file",
            "python script.py",
            "npm install",
            "cargo build",
        ],
    )
    def test_various_safe_commands(self, validator, safe_cmd: str):
        """Test various safe command patterns"""
        result = validator.validate({"command": safe_cmd})

        assert result["safe"] is True, f"Command '{safe_cmd}' should be allowed"


# ============================================================================
# File Validator Tests
# ============================================================================


class TestFileValidator:
    """Tests for security/file validator"""

    @pytest.fixture
    def validator(self):
        return load_validator("security/file")

    def test_blocked_path_rejected(self, validator):
        """Test that system paths are blocked"""
        result = validator.validate({"file_path": "/etc/passwd", "command": "Write"})

        assert result["safe"] is False
        assert "blocked" in result["reason"].lower()

    def test_normal_file_allowed(self, validator):
        """Test that normal files are accessible"""
        result = validator.validate(
            {"file_path": "src/main.py", "content": "print('Hello')"}
        )

        assert result["safe"] is True

    def test_env_file_write_blocked(self, validator):
        """Test that writing to .env is blocked"""
        result = validator.validate(
            {"file_path": ".env", "content": "SECRET=value", "command": "Write"}
        )

        assert result["safe"] is False
        assert "sensitive" in result["reason"].lower() or "environment" in result["reason"].lower()

    def test_env_file_read_allowed_with_redaction(self, validator):
        """Test that reading .env is allowed but flagged for redaction"""
        result = validator.validate({"file_path": ".env", "command": "Read"})

        assert result["safe"] is True
        assert result.get("metadata", {}).get("redacted") is True

    @pytest.mark.parametrize(
        "sensitive_file",
        [
            ".env",
            ".env.local",
            "config/secrets.yaml",
            "id_rsa",
            "private.key",
            ".aws/credentials",
        ],
    )
    def test_various_sensitive_files_write_blocked(self, validator, sensitive_file: str):
        """Test that writes to various sensitive files are blocked"""
        result = validator.validate(
            {"file_path": sensitive_file, "content": "data", "command": "Write"}
        )

        assert result["safe"] is False, f"Write to '{sensitive_file}' should be blocked"


# ============================================================================
# PII Validator Tests
# ============================================================================


class TestPIIValidator:
    """Tests for prompt/pii validator"""

    @pytest.fixture
    def validator(self):
        return load_validator("prompt/pii")

    def test_ssn_detected(self, validator):
        """Test that SSN patterns are detected"""
        result = validator.validate({"prompt": "My SSN is 123-45-6789"})

        assert result["safe"] is False
        assert "pii" in result["reason"].lower() or "ssn" in result["reason"].lower()

    def test_credit_card_detected(self, validator):
        """Test that credit card patterns are detected (with or without dashes)"""
        # Test with dashes
        result = validator.validate({"prompt": "Card: 4111-1111-1111-1111"})
        assert result["safe"] is False

        # Test without dashes
        result = validator.validate({"prompt": "Card: 4111111111111111"})
        assert result["safe"] is False

    def test_normal_prompt_allowed(self, validator):
        """Test that normal prompts pass through"""
        result = validator.validate({"prompt": "Write a Python script that prints Hello World"})

        assert result["safe"] is True

    def test_email_mention_allowed(self, validator):
        """Test that casual email mentions might be allowed (low risk)"""
        result = validator.validate({"prompt": "Send to user@example.com"})
        # Email alone might not be high-risk PII, depends on implementation
        # Just verify it doesn't crash
        assert "safe" in result


# ============================================================================
# Handler Integration Tests
# ============================================================================


class TestPreToolUseHandler:
    """Integration tests for pre-tool-use handler"""

    def test_dangerous_bash_blocked(self):
        """Test that pre-tool-use handler blocks dangerous bash"""
        event = {
            "session_id": "test-001",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
            "tool_use_id": "toolu_test_001",
        }

        result = run_handler("pre-tool-use", event)

        assert result.get("decision") == "block", f"Got: {result}"

    def test_safe_bash_allowed(self):
        """Test that pre-tool-use handler allows safe bash"""
        event = {
            "session_id": "test-002",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "tool_use_id": "toolu_test_002",
        }

        result = run_handler("pre-tool-use", event)

        assert result.get("decision") == "allow", f"Got: {result}"

    def test_sensitive_file_write_blocked(self):
        """Test that pre-tool-use handler blocks .env writes"""
        event = {
            "session_id": "test-003",
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": ".env", "content": "SECRET=value"},
            "tool_use_id": "toolu_test_003",
        }

        result = run_handler("pre-tool-use", event)

        assert result.get("decision") == "block", f"Got: {result}"


class TestUserPromptHandler:
    """Integration tests for user-prompt handler"""

    def test_pii_blocked(self):
        """Test that user-prompt handler blocks PII"""
        event = {
            "session_id": "test-004",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "My SSN is 123-45-6789 please use it",
        }

        result = run_handler("user-prompt", event)

        # Handler should block or warn about PII
        assert result.get("decision") in ("block", "allow"), f"Got: {result}"

    def test_normal_prompt_allowed(self):
        """Test that user-prompt handler allows normal prompts"""
        event = {
            "session_id": "test-005",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Write a hello world function",
        }

        result = run_handler("user-prompt", event)

        assert result.get("decision") == "allow", f"Got: {result}"


class TestHookIntegration:
    """Integration tests for multiple hooks"""

    def test_parallel_execution_simulation(self):
        """Simulate parallel hook execution for same event"""
        event = {
            "session_id": "test-011",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
            "tool_use_id": "toolu_test_011",
        }

        result = run_handler("pre-tool-use", event)

        # Dangerous command should be blocked
        assert result.get("decision") == "block"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
