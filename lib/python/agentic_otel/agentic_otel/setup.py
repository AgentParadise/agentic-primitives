"""OTel SDK initialization for hook scripts.

This module handles the one-time setup of OpenTelemetry SDK
for use in hook scripts that need to emit spans and events.
"""

from __future__ import annotations

import atexit
from typing import TYPE_CHECKING

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

if TYPE_CHECKING:
    from agentic_otel.config import OTelConfig

_initialized = False


def initialize_otel(config: OTelConfig) -> None:
    """Initialize OpenTelemetry SDK with the given configuration.

    This should be called once at hook script startup.
    Subsequent calls are no-ops.

    Args:
        config: OTel configuration with endpoint and resource attributes.

    Example:
        >>> from agentic_otel import OTelConfig
        >>> from agentic_otel.setup import initialize_otel
        >>>
        >>> config = OTelConfig(endpoint="http://collector:4317")
        >>> initialize_otel(config)
    """
    global _initialized
    if _initialized:
        return

    # Create resource with service name and custom attributes
    resource = Resource.create(config.to_sdk_resource_attributes())

    # Set up tracing
    tracer_provider = TracerProvider(resource=resource)
    span_exporter = OTLPSpanExporter(endpoint=config.endpoint)
    span_processor = BatchSpanProcessor(span_exporter)
    tracer_provider.add_span_processor(span_processor)
    trace.set_tracer_provider(tracer_provider)

    # Set up metrics
    metric_exporter = OTLPMetricExporter(endpoint=config.endpoint)
    metric_reader = PeriodicExportingMetricReader(
        exporter=metric_exporter,
        export_interval_millis=config.batch_timeout_ms,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # Ensure proper shutdown
    atexit.register(_shutdown, tracer_provider, meter_provider)

    _initialized = True


def _shutdown(tracer_provider: TracerProvider, meter_provider: MeterProvider) -> None:
    """Shutdown OTel providers gracefully."""
    tracer_provider.shutdown()
    meter_provider.shutdown()


def get_tracer(name: str = "agentic.hooks") -> trace.Tracer:
    """Get a tracer for creating spans.

    Args:
        name: Instrumentation scope name.

    Returns:
        An OTel Tracer instance.
    """
    return trace.get_tracer(name)


def get_meter(name: str = "agentic.hooks") -> metrics.Meter:
    """Get a meter for creating metrics.

    Args:
        name: Instrumentation scope name.

    Returns:
        An OTel Meter instance.
    """
    return metrics.get_meter(name)
