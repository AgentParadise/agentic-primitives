"""Tests for logger factory and setup."""

import logging
from pathlib import Path
from typing import Generator

import pytest

from agentic_logging.config import LogConfig
from agentic_logging.logger import (
    SessionFilter,
    clear_session_context,
    get_logger,
    set_session_context,
    setup_logging,
)


@pytest.fixture
def reset_logging() -> Generator[None, None, None]:
    """Reset logging configuration between tests."""
    # Clear all handlers and reset state
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.WARNING)
    
    # Reset module-level state
    import agentic_logging.logger
    agentic_logging.logger._setup_complete = False
    
    yield
    
    # Cleanup after test
    root_logger.handlers.clear()
    agentic_logging.logger._setup_complete = False


class TestSessionFilter:
    """Tests for SessionFilter class."""
    
    def test_filter_adds_session_id_to_record(self) -> None:
        """Test that session_id is added to log records."""
        session_filter = SessionFilter(session_id="test123")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        
        result = session_filter.filter(record)
        
        assert result is True
        assert hasattr(record, "session_id")
        assert record.session_id == "test123"  # type: ignore[attr-defined]
    
    def test_filter_uses_context_when_no_explicit_id(self) -> None:
        """Test that filter uses context when no explicit session_id."""
        set_session_context("context123")
        session_filter = SessionFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        
        result = session_filter.filter(record)
        
        assert result is True
        assert hasattr(record, "session_id")
        assert record.session_id == "context123"  # type: ignore[attr-defined]
        
        clear_session_context()
    
    def test_filter_returns_true_when_no_session(self) -> None:
        """Test that filter doesn't filter out records when no session."""
        clear_session_context()
        session_filter = SessionFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        
        result = session_filter.filter(record)
        
        assert result is True


class TestSetupLogging:
    """Tests for setup_logging function."""
    
    def test_setup_logging_with_defaults(
        self, reset_logging: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that setup_logging configures root logger."""
        log_file = tmp_path / "logs" / "test.jsonl"
        monkeypatch.setenv("LOG_FILE", str(log_file))
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        
        setup_logging()
        
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) == 2  # Console + file
        assert root_logger.level == logging.DEBUG  # Capture all
    
    def test_setup_logging_creates_log_directory(
        self, reset_logging: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that setup_logging creates log directory."""
        log_file = tmp_path / "logs" / "test.jsonl"
        monkeypatch.setenv("LOG_FILE", str(log_file))
        
        setup_logging()
        
        assert log_file.parent.exists()
    
    def test_setup_logging_only_runs_once(
        self, reset_logging: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that setup_logging doesn't duplicate handlers."""
        log_file = tmp_path / "logs" / "test.jsonl"
        monkeypatch.setenv("LOG_FILE", str(log_file))
        
        setup_logging()
        setup_logging()  # Call twice
        
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) == 2  # Still only 2 handlers
    
    def test_setup_logging_handles_file_creation_failure(
        self, reset_logging: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that setup_logging handles file creation failures gracefully."""
        # Use a path that will fail
        monkeypatch.setenv("LOG_FILE", "/root/impossible/path/test.jsonl")
        
        # Should not raise
        setup_logging()
        
        root_logger = logging.getLogger()
        # Should still have console handler
        assert len(root_logger.handlers) >= 1


class TestGetLogger:
    """Tests for get_logger function."""
    
    def test_get_logger_returns_logger(
        self, reset_logging: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that get_logger returns a logger."""
        log_file = tmp_path / "logs" / "test.jsonl"
        monkeypatch.setenv("LOG_FILE", str(log_file))
        
        logger = get_logger("test.module")
        
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"
    
    def test_get_logger_sets_up_logging_automatically(
        self, reset_logging: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that get_logger calls setup_logging if needed."""
        log_file = tmp_path / "logs" / "test.jsonl"
        monkeypatch.setenv("LOG_FILE", str(log_file))
        
        logger = get_logger("test.module")
        
        # Setup should have been called
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0
    
    def test_get_logger_with_session_id(
        self, reset_logging: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that get_logger adds session filter when session_id provided."""
        log_file = tmp_path / "logs" / "test.jsonl"
        monkeypatch.setenv("LOG_FILE", str(log_file))
        
        logger = get_logger("test.module", session_id="test123")
        
        # Check that SessionFilter was added
        session_filters = [f for f in logger.filters if isinstance(f, SessionFilter)]
        assert len(session_filters) == 1
        assert session_filters[0].session_id == "test123"
    
    def test_get_logger_component_level_override(
        self, reset_logging: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that component-specific log levels are applied."""
        log_file = tmp_path / "logs" / "test.jsonl"
        monkeypatch.setenv("LOG_FILE", str(log_file))
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        monkeypatch.setenv("LOG_LEVEL_TEST_MODULE", "DEBUG")
        
        logger = get_logger("test.module")
        
        assert logger.level == logging.DEBUG
    
    def test_get_logger_same_name_returns_same_instance(
        self, reset_logging: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that calling get_logger with same name returns same logger."""
        log_file = tmp_path / "logs" / "test.jsonl"
        monkeypatch.setenv("LOG_FILE", str(log_file))
        
        logger1 = get_logger("test.module")
        logger2 = get_logger("test.module")
        
        assert logger1 is logger2
    
    def test_get_logger_replaces_session_filter_on_new_session(
        self, reset_logging: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that new session_id replaces old SessionFilter."""
        log_file = tmp_path / "logs" / "test.jsonl"
        monkeypatch.setenv("LOG_FILE", str(log_file))
        
        logger = get_logger("test.module", session_id="session1")
        logger = get_logger("test.module", session_id="session2")
        
        # Should only have one SessionFilter with new session_id
        session_filters = [f for f in logger.filters if isinstance(f, SessionFilter)]
        assert len(session_filters) == 1
        assert session_filters[0].session_id == "session2"


class TestSessionContext:
    """Tests for session context management."""
    
    def test_set_session_context(self) -> None:
        """Test that session context can be set."""
        set_session_context("test123")
        
        # Create a filter that uses context
        session_filter = SessionFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        session_filter.filter(record)
        
        assert record.session_id == "test123"  # type: ignore[attr-defined]
        
        clear_session_context()
    
    def test_clear_session_context(self) -> None:
        """Test that session context can be cleared."""
        set_session_context("test123")
        clear_session_context()
        
        # Create a filter that uses context
        session_filter = SessionFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        session_filter.filter(record)
        
        # session_id should not be set
        assert not hasattr(record, "session_id")

