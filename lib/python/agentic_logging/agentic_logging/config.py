"""Configuration management for agentic logging system.

This module handles environment variable parsing and provides default values
for the logging system. It supports both system-wide and per-component log levels.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class LogConfig:
    """Configuration for the agentic logging system.
    
    All configuration is read from environment variables, allowing zero-code
    configuration changes for different environments.
    
    Attributes:
        level: System-wide log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to the JSONL log file
        console_format: Console output format ('human' or 'json')
        max_bytes: Maximum size of log file before rotation (bytes)
        backup_count: Number of backup files to keep
    """
    
    level: str
    log_file: Path
    console_format: str
    max_bytes: int
    backup_count: int
    
    @classmethod
    def from_env(cls) -> "LogConfig":
        """Create LogConfig from environment variables with sensible defaults.
        
        Environment Variables:
            LOG_LEVEL: System-wide log level (default: WARNING)
            LOG_FILE: Path to log file (default: ./logs/agentic.jsonl)
            LOG_CONSOLE_FORMAT: Console format (default: human)
            LOG_MAX_BYTES: Max file size before rotation (default: 10485760 = 10MB)
            LOG_BACKUP_COUNT: Number of backups to keep (default: 5)
        
        Returns:
            LogConfig instance with values from environment or defaults
        """
        level = os.getenv("LOG_LEVEL", "WARNING").upper()
        log_file = Path(os.getenv("LOG_FILE", "./logs/agentic.jsonl"))
        console_format = os.getenv("LOG_CONSOLE_FORMAT", "human").lower()
        max_bytes = int(os.getenv("LOG_MAX_BYTES", "10485760"))
        backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))
        
        # Validate log level
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in valid_levels:
            # Fail-safe: default to WARNING if invalid
            level = "WARNING"
        
        # Validate console format
        if console_format not in {"human", "json"}:
            # Fail-safe: default to human if invalid
            console_format = "human"
        
        return cls(
            level=level,
            log_file=log_file,
            console_format=console_format,
            max_bytes=max_bytes,
            backup_count=backup_count,
        )
    
    @staticmethod
    def get_component_level(component_name: str) -> Optional[str]:
        """Get the log level for a specific component.
        
        Checks for environment variable LOG_LEVEL_{COMPONENT} where component
        name is normalized: dots replaced with underscores, converted to uppercase.
        
        Examples:
            hooks.core.hooks_collector -> LOG_LEVEL_HOOKS_CORE_HOOKS_COLLECTOR
            analytics.publishers.file -> LOG_LEVEL_ANALYTICS_PUBLISHERS_FILE
        
        Args:
            component_name: Python module name (usually from __name__)
        
        Returns:
            Log level string if configured, None otherwise
        """
        # Normalize component name: replace dots with underscores, uppercase
        normalized = component_name.replace(".", "_").upper()
        env_var = f"LOG_LEVEL_{normalized}"
        
        level = os.getenv(env_var)
        if level:
            level = level.upper()
            # Validate it's a real log level
            valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
            if level in valid_levels:
                return level
        
        return None
    
    def ensure_log_directory(self) -> None:
        """Create log directory if it doesn't exist.
        
        Fails silently if directory creation fails (fail-safe design).
        """
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError):
            # Fail-safe: if we can't create the directory, logging will fall back
            # to console only
            pass

