"""
Analytics Middleware Entry Points

This package contains middleware entry points for the agentic-primitives hook system.
These scripts are called by the Rust-based hook system and communicate via stdin/stdout.

Modules:
- event_normalizer: Normalizes hook input events to provider-agnostic format
- event_publisher: Publishes normalized events to configured backend
"""

