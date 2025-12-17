"""OTel configuration for Claude CLI and hook scripts.

This module provides configuration that can be:
1. Converted to environment variables for Claude CLI
2. Used to initialize OTel SDK in hook scripts
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class OTelConfig:
    """OTel configuration for Claude CLI and agent hooks.

    Platform-agnostic - doesn't know about workflows/phases.
    Caller injects custom resource attributes for correlation.

    Example:
        >>> config = OTelConfig(
        ...     endpoint="http://collector:4317",
        ...     resource_attributes={"deployment.environment": "prod"}
        ... )
        >>> env = config.to_env()
        >>> # Pass env to subprocess or container
    """

    # Required
    endpoint: str

    # OTel standard configuration
    service_name: str = "agentic-agent"
    protocol: Literal["grpc", "http/protobuf"] = "grpc"
    metrics_exporter: str = "otlp"
    logs_exporter: str = "otlp"
    traces_exporter: str = "otlp"

    # Custom resource attributes (caller provides)
    # These propagate to all signals automatically
    resource_attributes: dict[str, str] = field(default_factory=dict)

    # Metrics cardinality control (Claude CLI specific)
    include_tool_name: bool = True
    include_model_name: bool = True

    # Batch processing
    batch_timeout_ms: int = 1000
    batch_max_size: int = 512

    def to_env(self) -> dict[str, str]:
        """Convert to environment variables for Claude CLI.

        Returns a dict that can be passed to subprocess or container.
        Claude CLI reads these to configure its native OTel emission.

        Example:
            >>> config = OTelConfig(endpoint="http://collector:4317")
            >>> env = config.to_env()
            >>> env["CLAUDE_CODE_ENABLE_TELEMETRY"]
            '1'
        """
        env: dict[str, str] = {
            # Enable Claude Code telemetry
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
            # OTel exporter configuration
            "OTEL_EXPORTER_OTLP_ENDPOINT": self.endpoint,
            "OTEL_EXPORTER_OTLP_PROTOCOL": self.protocol,
            # Exporter types
            "OTEL_METRICS_EXPORTER": self.metrics_exporter,
            "OTEL_LOGS_EXPORTER": self.logs_exporter,
            "OTEL_TRACES_EXPORTER": self.traces_exporter,
            # Service identification
            "OTEL_SERVICE_NAME": self.service_name,
        }

        # Cardinality control for Claude CLI metrics
        if not self.include_tool_name:
            env["CLAUDE_CODE_OTEL_TOOL_NAME_ENABLED"] = "false"
        if not self.include_model_name:
            env["CLAUDE_CODE_OTEL_MODEL_NAME_ENABLED"] = "false"

        # Resource attributes - key for platform correlation
        if self.resource_attributes:
            attrs = ",".join(f"{k}={v}" for k, v in self.resource_attributes.items())
            env["OTEL_RESOURCE_ATTRIBUTES"] = attrs

        return env

    def to_sdk_resource_attributes(self) -> dict[str, str]:
        """Get resource attributes for OTel SDK initialization.

        Use this when initializing OTel SDK in hook scripts.
        Includes service name plus any custom attributes.
        """
        attrs = {"service.name": self.service_name}
        attrs.update(self.resource_attributes)
        return attrs
