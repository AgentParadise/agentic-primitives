"""Analytics client for logging hook decisions.

Provides a simple, DI-friendly client that hooks use to log their decisions.
Supports both file and API backends for flexibility.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_analytics.models import HookDecision


class AnalyticsClient:
    """Simple analytics client for hook decision logging.

    This client is designed to be:
    - Fast: Synchronous file writes are <1ms
    - Fail-safe: Never blocks hook execution on errors
    - DI-friendly: Easy to inject different backends for testing

    Backends:
    - File (default): Appends to JSONL file
    - API (future): POSTs to central analytics server

    Example:
        # Default file backend
        analytics = AnalyticsClient()
        analytics.log(decision)

        # Custom file path
        analytics = AnalyticsClient(output_path=Path("./logs/events.jsonl"))

        # API backend (for production)
        analytics = AnalyticsClient(api_endpoint="https://api.example.com/events")

        # From environment variables
        analytics = AnalyticsClient.from_env()
    """

    def __init__(
        self,
        output_path: Path | None = None,
        api_endpoint: str | None = None,
        api_key: str | None = None,
    ) -> None:
        """Initialize analytics client.

        Args:
            output_path: Path to JSONL file for file backend.
                         Default: .agentic/analytics/events.jsonl
            api_endpoint: URL for API backend (optional, for future use)
            api_key: API key for authentication (optional)
        """
        self.output_path = output_path or Path(".agentic/analytics/events.jsonl")
        self.api_endpoint = api_endpoint
        self.api_key = api_key

    @classmethod
    def from_env(cls) -> "AnalyticsClient":
        """Create client from environment variables.

        Environment Variables:
            ANALYTICS_OUTPUT_PATH: Path to JSONL file
            ANALYTICS_API_ENDPOINT: URL for API backend
            ANALYTICS_API_KEY: API key for authentication

        Returns:
            Configured AnalyticsClient instance
        """
        output_path = os.getenv("ANALYTICS_OUTPUT_PATH")
        api_endpoint = os.getenv("ANALYTICS_API_ENDPOINT")
        api_key = os.getenv("ANALYTICS_API_KEY")

        return cls(
            output_path=Path(output_path) if output_path else None,
            api_endpoint=api_endpoint,
            api_key=api_key,
        )

    def log(self, decision: HookDecision) -> None:
        """Log a hook decision to the audit trail.

        This method is synchronous and fail-safe. If logging fails,
        it silently continues to avoid blocking hook execution.

        Args:
            decision: The hook decision to log
        """
        event = self._build_event(decision)

        # Try API first if configured
        if self.api_endpoint:
            self._write_api(event)
        else:
            self._write_file(event)

    def _build_event(self, decision: HookDecision) -> dict[str, Any]:
        """Build event dictionary with timestamp."""
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            **decision.to_dict(),
        }

    def _write_file(self, event: dict[str, Any]) -> None:
        """Write event to JSONL file.

        Fail-safe: errors are silently ignored to avoid blocking hooks.
        """
        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.output_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception:
            # Fail-safe: never block hook execution
            pass

    def _write_api(self, event: dict[str, Any]) -> None:
        """Write event to API endpoint.

        Fail-safe: errors are silently ignored to avoid blocking hooks.
        Uses synchronous requests to keep latency predictable.
        """
        try:
            import httpx

            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            # Synchronous with short timeout to avoid blocking
            with httpx.Client(timeout=2.0) as client:
                client.post(
                    self.api_endpoint,  # type: ignore[arg-type]
                    json=event,
                    headers=headers,
                )
        except Exception:
            # Fail-safe: if API fails, try file as fallback
            self._write_file(event)


# Convenience function for simple usage
def log_decision(decision: HookDecision) -> None:
    """Log a hook decision using default client.

    Convenience function for simple cases where DI isn't needed.

    Args:
        decision: The hook decision to log
    """
    client = AnalyticsClient.from_env()
    client.log(decision)
