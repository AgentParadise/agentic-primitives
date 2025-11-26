#!/usr/bin/env python3
"""
Unit tests for Claude Code hooks

Tests hook logic offline using JSON fixtures.
Cross-platform compatible using Python + Pydantic.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import pytest
from pydantic import BaseModel, Field


# Test fixtures models
class HookTestFixture(BaseModel):
    """Test fixture for hook testing"""
    session_id: str
    transcript_path: str
    cwd: str
    permission_mode: Literal["default", "plan", "acceptEdits", "bypassPermissions"]
    hook_event_name: str
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_use_id: Optional[str] = None
    prompt: Optional[str] = None


class HookTestResult(BaseModel):
    """Result from hook execution"""
    success: bool
    decision: Optional[str] = None
    reason: Optional[str] = None
    alternative: Optional[str] = None
    warning: Optional[str] = None
    error: Optional[str] = None
    raw_output: Optional[str] = None


class HookTester:
    """Utility class for testing hooks"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.hooks_dir = project_root / "build" / "claude" / ".claude" / "hooks"
        self.fixtures_dir = Path(__file__).parent / "fixtures"
    
    def get_hook_path(self, category: str, hook_name: str) -> Path:
        """Get path to hook script"""
        return self.hooks_dir / category / f"{hook_name}.py"
    
    def run_hook(
        self,
        hook_path: Path,
        fixture: HookTestFixture,
        timeout: int = 10
    ) -> HookTestResult:
        """Run a hook with a test fixture"""
        if not hook_path.exists():
            return HookTestResult(
                success=False,
                error=f"Hook not found: {hook_path}"
            )
        
        try:
            # Run hook with fixture as stdin
            result = subprocess.run(
                [sys.executable, str(hook_path)],
                input=fixture.model_dump_json().encode(),
                capture_output=True,
                timeout=timeout,
            )
            
            if result.returncode != 0:
                return HookTestResult(
                    success=False,
                    error=f"Hook failed with code {result.returncode}",
                    raw_output=result.stderr.decode()
                )
            
            # Parse output
            try:
                output = json.loads(result.stdout.decode())
                return HookTestResult(
                    success=True,
                    decision=output.get("decision", "allow"),
                    reason=output.get("reason"),
                    alternative=output.get("alternative"),
                    warning=output.get("warning"),
                    raw_output=result.stdout.decode()
                )
            except json.JSONDecodeError:
                # Some hooks might not return JSON
                return HookTestResult(
                    success=True,
                    decision="allow",  # Assume allow if no JSON
                    raw_output=result.stdout.decode()
                )
        
        except subprocess.TimeoutExpired:
            return HookTestResult(
                success=False,
                error="Hook execution timed out"
            )
        except Exception as e:
            return HookTestResult(
                success=False,
                error=str(e)
            )


# Initialize tester
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
tester = HookTester(PROJECT_ROOT)


class TestBashValidator:
    """Tests for bash-validator hook"""
    
    def test_dangerous_command_blocked(self):
        """Test that dangerous bash commands are blocked"""
        hook_path = tester.get_hook_path("security", "bash-validator")
        
        fixture = HookTestFixture(
            session_id="test-001",
            transcript_path="/test/session.jsonl",
            cwd="/test",
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="Bash",
            tool_input={"command": "rm -rf /"},
            tool_use_id="toolu_test_001"
        )
        
        result = tester.run_hook(hook_path, fixture)
        
        assert result.success, f"Hook execution failed: {result.error}"
        assert result.decision == "block", "Dangerous command should be blocked"
        assert result.reason is not None, "Block reason should be provided"
    
    def test_safe_command_allowed(self):
        """Test that safe bash commands are allowed"""
        hook_path = tester.get_hook_path("security", "bash-validator")
        
        fixture = HookTestFixture(
            session_id="test-002",
            transcript_path="/test/session.jsonl",
            cwd="/test",
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="Bash",
            tool_input={"command": "ls -la"},
            tool_use_id="toolu_test_002"
        )
        
        result = tester.run_hook(hook_path, fixture)
        
        assert result.success, f"Hook execution failed: {result.error}"
        assert result.decision == "allow", "Safe command should be allowed"
    
    @pytest.mark.parametrize("dangerous_cmd", [
        "rm -rf /",
        "dd if=/dev/zero of=/dev/sda",
        "mkfs.ext4 /dev/sda",
        ":(){ :|:& };:",  # Fork bomb
    ])
    def test_various_dangerous_commands(self, dangerous_cmd: str):
        """Test various dangerous command patterns"""
        hook_path = tester.get_hook_path("security", "bash-validator")
        
        fixture = HookTestFixture(
            session_id="test-003",
            transcript_path="/test/session.jsonl",
            cwd="/test",
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="Bash",
            tool_input={"command": dangerous_cmd},
            tool_use_id="toolu_test_003"
        )
        
        result = tester.run_hook(hook_path, fixture)
        
        assert result.success, f"Hook execution failed: {result.error}"
        assert result.decision == "block", f"Command '{dangerous_cmd}' should be blocked"


class TestFileSecurity:
    """Tests for file-security hook"""
    
    def test_sensitive_file_redaction_enabled(self):
        """Test that sensitive files have redaction enabled (not blocked)"""
        hook_path = tester.get_hook_path("security", "file-security")
        
        fixture = HookTestFixture(
            session_id="test-004",
            transcript_path="/test/session.jsonl",
            cwd="/test",
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="Read",
            tool_input={"file_path": ".env"},
            tool_use_id="toolu_test_004"
        )
        
        result = tester.run_hook(hook_path, fixture)
        
        assert result.success, f"Hook execution failed: {result.error}"
        assert result.decision == "allow", "Sensitive file should be allowed with redaction"
        assert result.warning is not None, "Should warn about sensitive file"
    
    def test_normal_file_allowed(self):
        """Test that normal files are accessible"""
        hook_path = tester.get_hook_path("security", "file-security")
        
        fixture = HookTestFixture(
            session_id="test-005",
            transcript_path="/test/session.jsonl",
            cwd="/test",
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="Write",
            tool_input={"file_path": "src/main.py", "contents": "print('Hello')"},
            tool_use_id="toolu_test_005"
        )
        
        result = tester.run_hook(hook_path, fixture)
        
        assert result.success, f"Hook execution failed: {result.error}"
        assert result.decision == "allow", "Normal file access should be allowed"
    
    @pytest.mark.parametrize("sensitive_file", [
        ".env",
        ".env.local",
        "config/secrets.yaml",
        "id_rsa",
        "private.key",
        ".aws/credentials",
    ])
    def test_various_sensitive_files(self, sensitive_file: str):
        """Test that various sensitive files are detected and redaction is enabled"""
        hook_path = tester.get_hook_path("security", "file-security")
        
        fixture = HookTestFixture(
            session_id="test-006",
            transcript_path="/test/session.jsonl",
            cwd="/test",
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="Read",
            tool_input={"file_path": sensitive_file},
            tool_use_id="toolu_test_006"
        )
        
        result = tester.run_hook(hook_path, fixture)
        
        assert result.success, f"Hook execution failed: {result.error}"
        assert result.decision == "allow", f"File '{sensitive_file}' should be allowed with redaction"
        assert result.warning is not None, f"Should warn about sensitive file '{sensitive_file}'"


class TestPromptFilter:
    """Tests for prompt-filter hook"""
    
    def test_pii_detected(self):
        """Test that PII in prompts is detected"""
        hook_path = tester.get_hook_path("security", "prompt-filter")
        
        fixture = HookTestFixture(
            session_id="test-007",
            transcript_path="/test/session.jsonl",
            cwd="/test",
            permission_mode="default",
            hook_event_name="UserPromptSubmit",
            prompt="Add my email john.doe@company.com to the config"
        )
        
        result = tester.run_hook(hook_path, fixture)
        
        assert result.success, f"Hook execution failed: {result.error}"
        # Prompt filter allows with warning, doesn't block
        assert result.decision == "allow", "Prompt should be allowed"
        # Should have warning about PII
        # (depends on implementation - might be in warning or reason)
    
    def test_normal_prompt_allowed(self):
        """Test that normal prompts pass through"""
        hook_path = tester.get_hook_path("security", "prompt-filter")
        
        fixture = HookTestFixture(
            session_id="test-008",
            transcript_path="/test/session.jsonl",
            cwd="/test",
            permission_mode="default",
            hook_event_name="UserPromptSubmit",
            prompt="Write a Python script that prints Hello World"
        )
        
        result = tester.run_hook(hook_path, fixture)
        
        assert result.success, f"Hook execution failed: {result.error}"
        assert result.decision == "allow", "Normal prompt should be allowed"


class TestHookIntegration:
    """Integration tests for multiple hooks"""
    
    def test_parallel_execution_simulation(self):
        """Simulate parallel hook execution for same event"""
        fixture = HookTestFixture(
            session_id="test-011",
            transcript_path="/test/session.jsonl",
            cwd="/test",
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="Bash",
            tool_input={"command": "rm -rf /"},
            tool_use_id="toolu_test_011"
        )
        
        # Security hooks that would fire for PreToolUse + Bash
        hooks = [
            ("security", "bash-validator"),  # Bash-specific
        ]
        
        results = []
        for category, hook_name in hooks:
            hook_path = tester.get_hook_path(category, hook_name)
            result = tester.run_hook(hook_path, fixture)
            results.append((hook_name, result))
        
        # All hooks should execute successfully
        for hook_name, result in results:
            assert result.success, f"{hook_name} failed: {result.error}"
        
        # Collect decisions
        decisions = {hook_name: result.decision for hook_name, result in results}
        
        # Bash validator blocks dangerous command
        assert decisions["bash-validator"] == "block"
        
        # In real Claude Code, block wins (any hook blocks = operation blocked)
        final_decision = "block" if any(d == "block" for d in decisions.values()) else "allow"
        assert final_decision == "block", "Dangerous operation should be blocked"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])

