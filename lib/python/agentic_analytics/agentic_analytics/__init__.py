"""Analytics client for agentic hooks.

A simple, DI-friendly client that hooks use to log their decisions
to a central audit trail.

Quick Start:
    from agentic_analytics import AnalyticsClient, HookDecision

    analytics = AnalyticsClient()
    analytics.log(HookDecision(
        hook_id="bash-validator",
        event_type="PreToolUse",
        decision="block",
        session_id="abc123",
        reason="Dangerous command",
    ))

Configuration:
    # File backend (default)
    analytics = AnalyticsClient()

    # Custom file path
    analytics = AnalyticsClient(output_path=Path("./custom/events.jsonl"))

    # API backend (for production)
    analytics = AnalyticsClient(api_endpoint="https://analytics.example.com/events")
"""

from agentic_analytics.client import AnalyticsClient
from agentic_analytics.models import HookDecision
from agentic_analytics.validation import (
    EventStats,
    ValidationResult,
    analyze_events,
    format_summary,
    load_events,
    validate,
)

__version__ = "0.1.0"

__all__ = [
    # Client
    "AnalyticsClient",
    "HookDecision",
    # Validation
    "EventStats",
    "ValidationResult",
    "load_events",
    "analyze_events",
    "validate",
    "format_summary",
]
