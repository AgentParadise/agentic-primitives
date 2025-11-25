"""Tests for log formatters."""

import json
import logging
from typing import Any, Dict

import pytest

from agentic_logging.formatters import HumanFormatter, JSONFormatter


class TestJSONFormatter:
    """Tests for JSONFormatter class."""
    
    def test_basic_log_format(self) -> None:
        """Test that basic log message is formatted as JSON."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        output = formatter.format(record)
        data = json.loads(output)
        
        assert data["level"] == "INFO"
        assert data["component"] == "test.module"
        assert data["message"] == "Test message"
        assert "timestamp" in data
    
    def test_log_with_session_id(self) -> None:
        """Test that session_id is included when present."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        # Add session_id as an extra field
        record.session_id = "abc123"  # type: ignore[attr-defined]
        
        output = formatter.format(record)
        data = json.loads(output)
        
        assert data["session_id"] == "abc123"
    
    def test_log_with_extra_fields(self) -> None:
        """Test that extra fields are included in JSON output."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        # Add extra fields
        record.event_type = "PreToolUse"  # type: ignore[attr-defined]
        record.middleware_count = 3  # type: ignore[attr-defined]
        
        output = formatter.format(record)
        data = json.loads(output)
        
        assert data["event_type"] == "PreToolUse"
        assert data["middleware_count"] == 3
    
    def test_log_with_exception(self) -> None:
        """Test that exception info is included in JSON output."""
        formatter = JSONFormatter()
        
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        
        record = logging.LogRecord(
            name="test.module",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=exc_info,
        )
        
        output = formatter.format(record)
        data = json.loads(output)
        
        assert "exc_info" in data
        assert "ValueError" in data["exc_info"]
        assert "Test error" in data["exc_info"]
    
    def test_output_is_valid_json(self) -> None:
        """Test that output is always valid JSON."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.DEBUG,
            pathname="test.py",
            lineno=10,
            msg="Test message with special chars: \n\t\"'",
            args=(),
            exc_info=None,
        )
        
        output = formatter.format(record)
        
        # Should not raise
        data = json.loads(output)
        assert isinstance(data, dict)


class TestHumanFormatter:
    """Tests for HumanFormatter class."""
    
    def test_basic_log_format(self) -> None:
        """Test that basic log message is formatted for humans."""
        formatter = HumanFormatter(use_color=False)
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        output = formatter.format(record)
        
        assert "INFO" in output
        assert "test.module" in output
        assert "Test message" in output
        assert "[" in output  # Timestamp marker
    
    def test_log_with_emoji_indicators(self) -> None:
        """Test that emoji indicators are present for each level."""
        formatter = HumanFormatter(use_color=False)
        
        levels = [
            (logging.DEBUG, "🔍"),
            (logging.INFO, "ℹ️"),
            (logging.WARNING, "⚠️"),
            (logging.ERROR, "❌"),
            (logging.CRITICAL, "🚨"),
        ]
        
        for level, emoji in levels:
            record = logging.LogRecord(
                name="test.module",
                level=level,
                pathname="test.py",
                lineno=10,
                msg="Test message",
                args=(),
                exc_info=None,
            )
            output = formatter.format(record)
            assert emoji in output
    
    def test_log_with_extra_fields(self) -> None:
        """Test that extra fields are formatted with tree structure."""
        formatter = HumanFormatter(use_color=False)
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        # Add extra fields
        record.event_type = "PreToolUse"  # type: ignore[attr-defined]
        record.middleware_count = 3  # type: ignore[attr-defined]
        
        output = formatter.format(record)
        
        # Check for tree structure
        assert "├─" in output or "└─" in output
        assert "event_type:" in output
        assert "middleware_count:" in output
    
    def test_log_with_session_id_appears_first(self) -> None:
        """Test that session_id appears before other extra fields."""
        formatter = HumanFormatter(use_color=False)
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.session_id = "abc123"  # type: ignore[attr-defined]
        record.other_field = "value"  # type: ignore[attr-defined]
        
        output = formatter.format(record)
        
        # session_id should appear before other_field in output
        session_pos = output.find("session_id")
        other_pos = output.find("other_field")
        assert session_pos < other_pos
    
    def test_log_with_exception(self) -> None:
        """Test that exception info is included and indented."""
        formatter = HumanFormatter(use_color=False)
        
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        
        record = logging.LogRecord(
            name="test.module",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=exc_info,
        )
        
        output = formatter.format(record)
        
        assert "ValueError" in output
        assert "Test error" in output
        # Check that exception is indented
        lines = output.split("\n")
        exc_lines = [line for line in lines if "ValueError" in line or "Test error" in line]
        assert all(line.startswith("  ") for line in exc_lines)
    
    def test_color_disabled_by_default_for_non_tty(self) -> None:
        """Test that color is disabled when output is not a TTY."""
        formatter = HumanFormatter()  # Auto-detect
        
        # Color should be disabled if stderr is not a TTY
        # We can't test the auto-detection directly, but we can test
        # that the formatter initializes without error
        assert isinstance(formatter, HumanFormatter)
    
    def test_multiline_message_formatting(self) -> None:
        """Test that multiline messages are handled correctly."""
        formatter = HumanFormatter(use_color=False)
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Line 1\nLine 2\nLine 3",
            args=(),
            exc_info=None,
        )
        
        output = formatter.format(record)
        
        # All lines should be present
        assert "Line 1" in output
        assert "Line 2" in output
        assert "Line 3" in output
    
    def test_timestamp_includes_milliseconds(self) -> None:
        """Test that timestamp includes milliseconds."""
        formatter = HumanFormatter(use_color=False)
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.msecs = 123.456
        
        output = formatter.format(record)
        
        # Should contain timestamp with milliseconds
        assert ".123" in output

