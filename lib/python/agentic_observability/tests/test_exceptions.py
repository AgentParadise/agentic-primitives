"""Tests for exceptions module."""

import os

from agentic_observability import TestOnlyAdapterError


class TestTestOnlyAdapterError:
    """Tests for TestOnlyAdapterError."""

    def test_message_includes_adapter_name(self):
        """Error message should include the adapter name."""
        error = TestOnlyAdapterError("MyTestAdapter")
        assert "MyTestAdapter" in str(error)

    def test_message_includes_requirement(self):
        """Error message should explain the requirement."""
        error = TestOnlyAdapterError("MyTestAdapter")
        assert "AEF_ENVIRONMENT='test'" in str(error)

    def test_message_includes_current_value(self):
        """Error message should show current environment value."""
        os.environ["AEF_ENVIRONMENT"] = "production"
        error = TestOnlyAdapterError("MyTestAdapter")
        assert "production" in str(error)

    def test_message_handles_unset(self):
        """Error message should handle unset environment variable."""
        os.environ.pop("AEF_ENVIRONMENT", None)
        error = TestOnlyAdapterError("MyTestAdapter")
        assert "not set" in str(error)
