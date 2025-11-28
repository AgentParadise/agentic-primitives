"""Tests for the validation module."""

import json
from pathlib import Path

import pytest

from agentic_analytics.validation import (
    EventStats,
    ValidationResult,
    analyze_events,
    format_summary,
    load_events,
    validate,
)


@pytest.fixture
def sample_events() -> list[dict]:
    """Sample events for testing."""
    return [
        {
            "hook_id": "bash-validator",
            "event_type": "PreToolUse",
            "decision": "allow",
            "session_id": "sess-001",
            "tool_name": "Bash",
        },
        {
            "hook_id": "bash-validator",
            "event_type": "PreToolUse",
            "decision": "block",
            "session_id": "sess-001",
            "tool_name": "Bash",
            "reason": "Dangerous command: rm -rf /",
            "metadata": {"command": "rm -rf /"},
        },
        {
            "hook_id": "file-security",
            "event_type": "PreToolUse",
            "decision": "allow",
            "session_id": "sess-001",
            "tool_name": "Read",
        },
        {
            "hook_id": "prompt-filter",
            "event_type": "UserPromptSubmit",
            "decision": "warn",
            "session_id": "sess-002",
            "reason": "PII detected",
        },
    ]


@pytest.fixture
def events_file(tmp_path: Path, sample_events: list[dict]) -> Path:
    """Create a temp JSONL file with sample events."""
    file_path = tmp_path / "events.jsonl"
    with open(file_path, "w") as f:
        for event in sample_events:
            f.write(json.dumps(event) + "\n")
    return file_path


class TestLoadEvents:
    """Tests for load_events function."""

    def test_load_valid_events(self, events_file: Path, sample_events: list[dict]):
        """Load events from valid JSONL file."""
        events = load_events(events_file)
        assert len(events) == len(sample_events)
        assert events[0]["hook_id"] == "bash-validator"

    def test_load_empty_file(self, tmp_path: Path):
        """Load from empty file returns empty list."""
        empty_file = tmp_path / "empty.jsonl"
        empty_file.touch()
        events = load_events(empty_file)
        assert events == []

    def test_load_nonexistent_file(self, tmp_path: Path):
        """Load from nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            load_events(tmp_path / "nonexistent.jsonl")

    def test_load_invalid_json(self, tmp_path: Path):
        """Load file with invalid JSON raises error."""
        bad_file = tmp_path / "bad.jsonl"
        bad_file.write_text('{"valid": true}\n{invalid json}\n')
        with pytest.raises(json.JSONDecodeError) as exc_info:
            load_events(bad_file)
        assert "line 2" in str(exc_info.value)

    def test_load_skips_blank_lines(self, tmp_path: Path):
        """Blank lines are skipped."""
        file_path = tmp_path / "sparse.jsonl"
        file_path.write_text('{"a": 1}\n\n{"b": 2}\n   \n{"c": 3}\n')
        events = load_events(file_path)
        assert len(events) == 3


class TestAnalyzeEvents:
    """Tests for analyze_events function."""

    def test_analyze_counts_by_hook(self, sample_events: list[dict]):
        """Counts events by hook ID."""
        stats = analyze_events(sample_events)
        assert stats.by_hook["bash-validator"] == 2
        assert stats.by_hook["file-security"] == 1
        assert stats.by_hook["prompt-filter"] == 1

    def test_analyze_counts_by_decision(self, sample_events: list[dict]):
        """Counts events by decision type."""
        stats = analyze_events(sample_events)
        assert stats.by_decision["allow"] == 2
        assert stats.by_decision["block"] == 1
        assert stats.by_decision["warn"] == 1

    def test_analyze_tracks_sessions(self, sample_events: list[dict]):
        """Tracks unique session IDs."""
        stats = analyze_events(sample_events)
        assert stats.sessions == {"sess-001", "sess-002"}

    def test_analyze_collects_blocked(self, sample_events: list[dict]):
        """Collects blocked operations."""
        stats = analyze_events(sample_events)
        assert len(stats.blocked) == 1
        assert stats.blocked[0]["hook"] == "bash-validator"
        assert "rm -rf" in stats.blocked[0]["reason"]

    def test_analyze_collects_warnings(self, sample_events: list[dict]):
        """Collects warnings."""
        stats = analyze_events(sample_events)
        assert len(stats.warnings) == 1
        assert stats.warnings[0]["hook"] == "prompt-filter"

    def test_analyze_empty_list(self):
        """Analyze empty list returns zeroed stats."""
        stats = analyze_events([])
        assert stats.total == 0
        assert len(stats.hooks) == 0

    def test_analyze_tracks_event_types(self, sample_events: list[dict]):
        """Counts events by event type."""
        stats = analyze_events(sample_events)
        assert stats.by_event_type["PreToolUse"] == 3
        assert stats.by_event_type["UserPromptSubmit"] == 1


class TestValidate:
    """Tests for validate function."""

    def test_validate_passes_with_events(self, events_file: Path):
        """Validation passes when events exist."""
        result = validate(events_file, print_output=False)
        assert result.passed is True
        assert result.total_events == 4

    def test_validate_fails_missing_file(self, tmp_path: Path):
        """Validation fails when file doesn't exist."""
        result = validate(tmp_path / "nope.jsonl", print_output=False)
        assert result.passed is False
        assert "File not found" in result.errors[0]

    def test_validate_fails_min_events(self, events_file: Path):
        """Validation fails when min events not met."""
        result = validate(events_file, min_events=100, print_output=False)
        assert result.passed is False
        assert "at least 100" in result.errors[0]

    def test_validate_required_hooks_pass(self, events_file: Path):
        """Validation passes when required hooks present."""
        result = validate(
            events_file,
            required_hooks={"bash-validator", "file-security"},
            print_output=False,
        )
        assert result.passed is True
        assert len(result.missing_hooks) == 0

    def test_validate_required_hooks_fail(self, events_file: Path):
        """Validation fails when required hooks missing."""
        result = validate(
            events_file,
            required_hooks={"bash-validator", "nonexistent-hook"},
            print_output=False,
        )
        assert result.passed is False
        assert "nonexistent-hook" in result.missing_hooks

    def test_validate_empty_file(self, tmp_path: Path):
        """Validation fails on empty file."""
        empty = tmp_path / "empty.jsonl"
        empty.touch()
        result = validate(empty, print_output=False)
        assert result.passed is False
        assert "No events" in result.errors[0]


class TestFormatSummary:
    """Tests for format_summary function."""

    def test_format_includes_total(self, sample_events: list[dict]):
        """Summary includes total count."""
        stats = analyze_events(sample_events)
        output = format_summary(stats)
        assert "Total Events: 4" in output

    def test_format_includes_hooks(self, sample_events: list[dict]):
        """Summary includes hook names."""
        stats = analyze_events(sample_events)
        output = format_summary(stats)
        assert "bash-validator" in output
        assert "file-security" in output

    def test_format_includes_decisions(self, sample_events: list[dict]):
        """Summary includes decision counts."""
        stats = analyze_events(sample_events)
        output = format_summary(stats)
        assert "allow: 2" in output
        assert "block: 1" in output

    def test_format_includes_blocked_section(self, sample_events: list[dict]):
        """Summary includes blocked operations."""
        stats = analyze_events(sample_events)
        output = format_summary(stats)
        assert "Blocked Operations" in output
        assert "rm -rf" in output


class TestEventStats:
    """Tests for EventStats dataclass."""

    def test_default_values(self):
        """Default values are properly initialized."""
        stats = EventStats()
        assert stats.total == 0
        assert len(stats.hooks) == 0
        assert len(stats.blocked) == 0


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_passed_result(self):
        """Create a passed result."""
        result = ValidationResult(passed=True, total_events=10)
        assert result.passed is True
        assert len(result.errors) == 0

    def test_failed_result(self):
        """Create a failed result with errors."""
        result = ValidationResult(
            passed=False,
            total_events=0,
            errors=["No events found"],
        )
        assert result.passed is False
        assert len(result.errors) == 1
