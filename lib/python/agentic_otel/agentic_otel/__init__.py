"""OpenTelemetry configuration and emission for AI agents.

This package provides OTel-first observability:
- OTelConfig: Configuration for Claude CLI's native OTel support
- AgentSemanticConventions: Standardized attribute names
- HookOTelEmitter: Emit spans and events from hook scripts
"""

from agentic_otel.config import OTelConfig
from agentic_otel.emitter import HookOTelEmitter
from agentic_otel.semantic import AgentSemanticConventions

__all__ = [
    "OTelConfig",
    "HookOTelEmitter",
    "AgentSemanticConventions",
]

__version__ = "0.1.0"
