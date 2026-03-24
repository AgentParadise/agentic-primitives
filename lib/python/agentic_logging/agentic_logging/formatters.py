"""Custom formatters for agentic logging system.

Provides both JSON (for AI agents and file storage) and human-readable
(for developer console) output formats.
"""

import logging
import os
import sys
from typing import Any

from pythonjsonlogger import jsonlogger  # type: ignore[import-untyped]


class JSONFormatter(jsonlogger.JsonFormatter):  # type: ignore[name-defined, misc]
    """JSON formatter for structured logging.

    Extends python-json-logger to include standard fields:
    - timestamp: ISO 8601 format
    - level: Log level name
    - component: Logger name (module path)
    - session_id: Session identifier (if available)
    - message: Log message
    - Any extra fields from logger.log(..., extra={})
    """

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        """Add standard fields to the JSON log record.

        Args:
            log_record: Dictionary that will be serialized to JSON
            record: Python logging.LogRecord instance
            message_dict: Dictionary from getMessage() parsing
        """
        super().add_fields(log_record, record, message_dict)

        # Add standard fields
        log_record["timestamp"] = self.formatTime(record, self.datefmt)
        log_record["level"] = record.levelname
        log_record["component"] = record.name
        log_record["message"] = record.getMessage()

        # Add session_id if present (added via extra parameter)
        if hasattr(record, "session_id"):
            log_record["session_id"] = record.session_id

        # Add exception info if present
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)


# Standard LogRecord instance attributes that should never appear as extra fields.
# logging.LogRecord.__dict__ is the *class* dict and does not contain these —
# they are set as instance attributes in LogRecord.__init__ — so we maintain an
# explicit exclusion set rather than relying on class-dict membership checks.
_STDLIB_LOG_RECORD_FIELDS = frozenset(
    {
        "name",
        "msg",
        "args",
        "created",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "exc_info",
        "exc_text",
        "thread",
        "threadName",
        "taskName",
        "message",
        "asctime",
    }
)


class HumanFormatter(logging.Formatter):
    """Human-readable formatter with minimal color and structure.

    Format:
        [HH:MM:SS.mmm] EMOJI LEVEL  component
          Message
          ├─ key: value
          └─ key: value

    Uses emoji indicators for quick visual scanning:
    - 🔍 DEBUG
    - ℹ️  INFO
    - ⚠️  WARNING
    - ❌ ERROR
    - 🚨 CRITICAL
    """

    # Level to emoji mapping
    LEVEL_EMOJI = {
        "DEBUG": "🔍",
        "INFO": "ℹ️ ",
        "WARNING": "⚠️ ",
        "ERROR": "❌",
        "CRITICAL": "🚨",
    }

    # ANSI color codes (used only if terminal supports it)
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",  # Reset
        "DIM": "\033[2m",  # Dim
    }

    def __init__(self, use_color: bool = True) -> None:
        """Initialize formatter.

        Args:
            use_color: Whether to use ANSI color codes
        """
        super().__init__()
        self.use_color = use_color and self._supports_color()

    @staticmethod
    def _supports_color() -> bool:
        """Check if the terminal supports color.

        Returns:
            True if color is supported, False otherwise
        """
        # Check if output is a TTY and not Windows (or has ANSICON)
        if not hasattr(sys.stderr, "isatty"):
            return False
        if not sys.stderr.isatty():
            return False
        # Windows check
        if sys.platform == "win32":
            return os.environ.get("ANSICON") is not None
        return True

    def _format_header(self, record: logging.LogRecord) -> str:
        emoji = self.LEVEL_EMOJI.get(record.levelname, "  ")
        timestamp = self.formatTime(record, "%H:%M:%S")
        if hasattr(record, "msecs"):
            timestamp = f"{timestamp}.{int(record.msecs):03d}"
        level = record.levelname.ljust(8)

        if self.use_color:
            color = self.COLORS.get(record.levelname, "")
            reset = self.COLORS["RESET"]
            dim = self.COLORS["DIM"]
            return (
                f"{dim}[{timestamp}]{reset} {emoji} {color}{level}{reset} {dim}{record.name}{reset}"
            )
        return f"[{timestamp}] {emoji} {level} {record.name}"

    def _format_extras(self, record: logging.LogRecord) -> list[str]:
        extra_fields = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _STDLIB_LOG_RECORD_FIELDS and k != "session_id"
        }
        if hasattr(record, "session_id"):
            extra_fields = {"session_id": record.session_id, **extra_fields}

        if not extra_fields:
            return []

        lines: list[str] = []
        items = list(extra_fields.items())
        dim = self.COLORS.get("DIM", "") if self.use_color else ""
        reset = self.COLORS.get("RESET", "") if self.use_color else ""

        for i, (key, value) in enumerate(items):
            prefix = "├─" if i < len(items) - 1 else "└─"
            if self.use_color:
                lines.append(f"  {dim}{prefix} {key}: {value}{reset}")
            else:
                lines.append(f"  {prefix} {key}: {value}")
        return lines

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record for human consumption.

        Args:
            record: Python logging.LogRecord instance

        Returns:
            Formatted string ready for console output
        """
        lines = [self._format_header(record), f"  {record.getMessage()}"]
        lines.extend(self._format_extras(record))

        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            for line in exc_text.split("\n"):
                lines.append(f"  {line}")

        return "\n".join(lines)
