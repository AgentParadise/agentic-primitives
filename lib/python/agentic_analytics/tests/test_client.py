"""Tests for analytics client."""

import json
import os
from pathlib import Path
from unittest.mock import patch

from agentic_analytics.client import AnalyticsClient, log_decision
from agentic_analytics.models import HookDecision


class TestAnalyticsClient:
    """Tests for AnalyticsClient class."""

    def test_default_output_path(self) -> None:
        """Test default output path is set correctly."""
        client = AnalyticsClient()

        assert client.output_path == Path(".agentic/analytics/events.jsonl")
        assert client.api_endpoint is None

    def test_custom_output_path(self, tmp_path: Path) -> None:
        """Test custom output path."""
        output = tmp_path / "custom" / "events.jsonl"
        client = AnalyticsClient(output_path=output)

        assert client.output_path == output

    def test_api_endpoint(self) -> None:
        """Test API endpoint configuration."""
        client = AnalyticsClient(
            api_endpoint="https://api.example.com/events",
            api_key="secret-key",
        )

        assert client.api_endpoint == "https://api.example.com/events"
        assert client.api_key == "secret-key"

    def test_from_env(self) -> None:
        """Test creating client from environment variables."""
        with patch.dict(
            os.environ,
            {
                "ANALYTICS_OUTPUT_PATH": "/tmp/test.jsonl",
                "ANALYTICS_API_ENDPOINT": "https://api.test.com",
                "ANALYTICS_API_KEY": "test-key",
            },
        ):
            client = AnalyticsClient.from_env()

            assert client.output_path == Path("/tmp/test.jsonl")
            assert client.api_endpoint == "https://api.test.com"
            assert client.api_key == "test-key"

    def test_from_env_defaults(self) -> None:
        """Test from_env with no environment variables."""
        with patch.dict(os.environ, {}, clear=True):
            client = AnalyticsClient.from_env()

            assert client.output_path == Path(".agentic/analytics/events.jsonl")
            assert client.api_endpoint is None

    def test_log_writes_to_file(self, tmp_path: Path) -> None:
        """Test logging decision writes to JSONL file."""
        output = tmp_path / "events.jsonl"
        client = AnalyticsClient(output_path=output)

        decision = HookDecision(
            hook_id="test-hook",
            event_type="PreToolUse",
            decision="allow",
            session_id="sess-123",
            tool_name="Bash",
        )

        client.log(decision)

        assert output.exists()
        with open(output) as f:
            event = json.loads(f.read().strip())

        assert event["hook_id"] == "test-hook"
        assert event["event_type"] == "PreToolUse"
        assert event["decision"] == "allow"
        assert event["session_id"] == "sess-123"
        assert event["tool_name"] == "Bash"
        assert "timestamp" in event

    def test_log_appends_multiple_events(self, tmp_path: Path) -> None:
        """Test multiple logs append to same file."""
        output = tmp_path / "events.jsonl"
        client = AnalyticsClient(output_path=output)

        for i in range(3):
            decision = HookDecision(
                hook_id=f"hook-{i}",
                event_type="PreToolUse",
                decision="allow",
                session_id=f"sess-{i}",
            )
            client.log(decision)

        with open(output) as f:
            lines = f.readlines()

        assert len(lines) == 3
        for i, line in enumerate(lines):
            event = json.loads(line)
            assert event["hook_id"] == f"hook-{i}"

    def test_log_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test log creates parent directories if needed."""
        output = tmp_path / "deep" / "nested" / "path" / "events.jsonl"
        client = AnalyticsClient(output_path=output)

        decision = HookDecision(
            hook_id="test",
            event_type="SessionStart",
            decision="allow",
            session_id="sess",
        )

        client.log(decision)

        assert output.exists()

    def test_log_is_fail_safe(self, tmp_path: Path) -> None:
        """Test log doesn't raise on write errors."""
        # Use an invalid path (directory instead of file)
        output = tmp_path / "directory"
        output.mkdir()
        client = AnalyticsClient(output_path=output)

        decision = HookDecision(
            hook_id="test",
            event_type="SessionStart",
            decision="allow",
            session_id="sess",
        )

        # Should not raise
        client.log(decision)

    def test_log_includes_timestamp(self, tmp_path: Path) -> None:
        """Test logged events include ISO timestamp."""
        output = tmp_path / "events.jsonl"
        client = AnalyticsClient(output_path=output)

        decision = HookDecision(
            hook_id="test",
            event_type="SessionStart",
            decision="allow",
            session_id="sess",
        )

        client.log(decision)

        with open(output) as f:
            event = json.loads(f.read().strip())

        # Should be ISO format with timezone
        assert "timestamp" in event
        assert "T" in event["timestamp"]
        assert "+" in event["timestamp"] or "Z" in event["timestamp"]

    def test_log_block_decision(self, tmp_path: Path) -> None:
        """Test logging a block decision with reason."""
        output = tmp_path / "events.jsonl"
        client = AnalyticsClient(output_path=output)

        decision = HookDecision(
            hook_id="bash-validator",
            event_type="PreToolUse",
            decision="block",
            session_id="sess-456",
            tool_name="Bash",
            reason="Dangerous command: rm -rf /",
            metadata={"command": "rm -rf /"},
        )

        client.log(decision)

        with open(output) as f:
            event = json.loads(f.read().strip())

        assert event["decision"] == "block"
        assert event["reason"] == "Dangerous command: rm -rf /"
        assert event["metadata"]["command"] == "rm -rf /"


class TestLogDecisionFunction:
    """Tests for log_decision convenience function."""

    def test_log_decision_uses_env(self, tmp_path: Path) -> None:
        """Test log_decision function uses environment config."""
        output = tmp_path / "func_events.jsonl"

        with patch.dict(os.environ, {"ANALYTICS_OUTPUT_PATH": str(output)}):
            decision = HookDecision(
                hook_id="func-test",
                event_type="SessionEnd",
                decision="allow",
                session_id="sess",
            )

            log_decision(decision)

        assert output.exists()
        with open(output) as f:
            event = json.loads(f.read().strip())

        assert event["hook_id"] == "func-test"


class TestAPIBackend:
    """Tests for API backend (mocked)."""

    def test_api_fallback_to_file_on_error(self, tmp_path: Path) -> None:
        """Test API failures fall back to file backend."""
        output = tmp_path / "fallback.jsonl"
        client = AnalyticsClient(
            output_path=output,
            api_endpoint="https://nonexistent.example.com/events",
        )

        decision = HookDecision(
            hook_id="api-test",
            event_type="PreToolUse",
            decision="allow",
            session_id="sess",
        )

        # Should not raise, should fall back to file
        client.log(decision)

        # File should have the event as fallback
        assert output.exists()
        with open(output) as f:
            event = json.loads(f.read().strip())
        assert event["hook_id"] == "api-test"
