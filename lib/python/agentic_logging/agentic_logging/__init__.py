"""Centralized logging system optimized for AI agents and human developers.

This package provides a unified logging interface that outputs structured JSON
for AI agents and human-readable formatted logs for developers. It supports
per-component log level configuration and session tracking.

Quick Start:
    from agentic_logging import get_logger

    logger = get_logger(__name__)
    logger.info("Hello world")

Configuration via environment variables:
    LOG_LEVEL - System-wide log level (default: WARNING)
    LOG_FILE - Path to log file (default: ./logs/agentic.jsonl)
    LOG_CONSOLE_FORMAT - Console format: human or json (default: human)
    LOG_LEVEL_{COMPONENT} - Per-component log level override

Example:
    export LOG_LEVEL=INFO
    export LOG_LEVEL_HOOKS_CORE_HOOKS_COLLECTOR=DEBUG
    export LOG_CONSOLE_FORMAT=json
"""

from agentic_logging.config import LogConfig
from agentic_logging.formatters import HumanFormatter, JSONFormatter
from agentic_logging.logger import get_logger, setup_logging

__version__ = "0.1.0"

__all__ = [
    "get_logger",
    "setup_logging",
    "LogConfig",
    "JSONFormatter",
    "HumanFormatter",
]
