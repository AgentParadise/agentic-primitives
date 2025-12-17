"""Exceptions for agentic-observability.

This module defines exceptions used by the observability package.
"""

from __future__ import annotations

import os


class TestOnlyAdapterError(Exception):
    """Raised when a test-only adapter is used outside test environment.

    This is a Poka-Yoke safety guard to prevent:
    - False positives in production (thinking observability works)
    - Data loss (in-memory implementations lose data on restart)
    - Silent failures (forgetting to configure real observability)

    The error message is designed to be helpful and guide the developer
    to the correct solution.
    """

    def __init__(self, adapter_name: str) -> None:
        env = os.environ.get("AEF_ENVIRONMENT", "not set")
        super().__init__(
            f"{adapter_name} can only be used when AEF_ENVIRONMENT='test'. "
            f"Current value: '{env}'. "
            "This adapter is for testing only and would not persist observations. "
            "Use TimescaleObservability for production/development."
        )
