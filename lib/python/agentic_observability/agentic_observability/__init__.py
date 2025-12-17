"""agentic-observability: Observability protocol for AI agent operations.

This library provides the core ObservabilityPort protocol that all agent
executors MUST depend on, ensuring consistent observability across the system.

Quick Start:
    from agentic_observability import ObservabilityPort, NullObservability

    # In production: use a real implementation (e.g., TimescaleObservability)
    # In tests: use NullObservability with AEF_ENVIRONMENT='test'

    class MyExecutor:
        def __init__(self, observability: ObservabilityPort) -> None:
            self._observability = observability  # Required!

Features:
    - Protocol-based interface for dependency injection
    - Enforces observability as a first-class requirement
    - NullObservability for tests (with safety guard)
    - Type hints for all operations
"""

from agentic_observability.exceptions import TestOnlyAdapterError
from agentic_observability.null import NullObservability
from agentic_observability.protocol import (
    ObservabilityPort,
    ObservationContext,
    ObservationType,
)

__all__ = [
    # Main Protocol
    "ObservabilityPort",
    # Types
    "ObservationType",
    "ObservationContext",
    # Test Implementation
    "NullObservability",
    # Exceptions
    "TestOnlyAdapterError",
]

__version__ = "0.1.0"
