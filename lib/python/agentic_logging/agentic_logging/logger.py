"""Logger factory and setup functions.

Provides the main interface for creating loggers with consistent configuration
across the entire system.
"""

import logging
import sys
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from typing import Optional

from agentic_logging.config import LogConfig
from agentic_logging.formatters import HumanFormatter, JSONFormatter

# Context variable for session tracking across async boundaries
_session_context: ContextVar[Optional[str]] = ContextVar("session_id", default=None)

# Track if logging has been set up globally
_setup_complete = False


class SessionFilter(logging.Filter):
    """Filter that adds session_id to all log records."""

    def __init__(self, session_id: Optional[str] = None) -> None:
        """Initialize filter with optional session ID.

        Args:
            session_id: Session ID to add to records, or None to use context
        """
        super().__init__()
        self.session_id = session_id

    def filter(self, record: logging.LogRecord) -> bool:
        """Add session_id to the log record.

        Args:
            record: Log record to modify

        Returns:
            Always True (never filters out records)
        """
        # Use explicit session_id or fall back to context
        session_id = self.session_id or _session_context.get()
        if session_id:
            record.session_id = session_id  # type: ignore[attr-defined]
        return True


def setup_logging(config: Optional[LogConfig] = None) -> None:
    """Set up global logging configuration.

    This should be called once at application startup. It configures the root
    logger with console and file handlers based on the provided config.

    Args:
        config: LogConfig instance, or None to load from environment
    """
    global _setup_complete

    if _setup_complete:
        # Already set up, don't duplicate handlers
        return

    if config is None:
        config = LogConfig.from_env()

    # Ensure log directory exists
    config.ensure_log_directory()

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all, filter at handler level

    # Clear any existing handlers (for testing)
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(getattr(logging, config.level))

    if config.console_format == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(HumanFormatter())

    root_logger.addHandler(console_handler)

    # File handler (with rotation)
    try:
        file_handler = RotatingFileHandler(
            config.log_file,
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)  # Log everything to file
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)
    except (OSError, PermissionError):
        # Fail-safe: if file handler fails, just use console
        # Log a warning to console
        console_handler.handle(
            logging.LogRecord(
                name="agentic_logging",
                level=logging.WARNING,
                pathname=__file__,
                lineno=0,
                msg=f"Could not create log file {config.log_file}, using console only",
                args=(),
                exc_info=None,
            )
        )

    _setup_complete = True


def get_logger(
    name: str,
    session_id: Optional[str] = None,
    config: Optional[LogConfig] = None,
) -> logging.Logger:
    """Get or create a logger with the specified name.

    This is the main entry point for creating loggers. It returns a standard
    Python logger configured according to the LogConfig settings, with optional
    per-component log level overrides.

    Args:
        name: Logger name (typically __name__ from the calling module)
        session_id: Optional session ID to include in all logs
        config: Optional LogConfig instance (loads from env if not provided)

    Returns:
        Configured logging.Logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("Processing started", extra={"user_id": 123})
    """
    # Ensure global logging is set up
    if not _setup_complete:
        setup_logging(config)

    # Get or create logger
    logger = logging.getLogger(name)

    # Check for component-specific log level
    component_level = LogConfig.get_component_level(name)
    if component_level:
        logger.setLevel(getattr(logging, component_level))

    # Add session filter if session_id provided
    if session_id:
        # Remove any existing SessionFilter for this logger
        logger.filters = [f for f in logger.filters if not isinstance(f, SessionFilter)]
        # Add new filter with session_id
        logger.addFilter(SessionFilter(session_id))

    return logger


def set_session_context(session_id: str) -> None:
    """Set the session ID for the current context.

    This is useful for async operations where session_id should be automatically
    included in all logs without explicitly passing it to each get_logger call.

    Args:
        session_id: Session ID to set in context
    """
    _session_context.set(session_id)


def clear_session_context() -> None:
    """Clear the session ID from the current context."""
    _session_context.set(None)
