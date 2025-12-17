"""Simple OTLP Receiver for capturing OTel signals.

This module provides an inline OTLP gRPC receiver that captures
OTel signals and emits them to a callback for display.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent import futures
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import grpc
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2, logs_service_pb2_grpc
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2, metrics_service_pb2_grpc
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc

from .display import DisplayEvent, EventType


@dataclass
class OTelSignal:
    """Parsed OTel signal."""

    signal_type: str  # "trace", "metric", "log"
    name: str
    value: str
    attributes: dict[str, Any]
    timestamp: datetime


class TraceServicer(trace_service_pb2_grpc.TraceServiceServicer):
    """gRPC servicer for trace signals."""

    def __init__(self, callback: Callable[[OTelSignal], None]):
        self.callback = callback

    def Export(
        self,
        request: trace_service_pb2.ExportTraceServiceRequest,
        context: grpc.ServicerContext,
    ) -> trace_service_pb2.ExportTraceServiceResponse:
        """Handle incoming trace export."""
        for resource_spans in request.resource_spans:
            # Extract resource attributes
            resource_attrs = {}
            if resource_spans.resource:
                for attr in resource_spans.resource.attributes:
                    resource_attrs[attr.key] = self._get_attr_value(attr.value)

            for scope_spans in resource_spans.scope_spans:
                for span in scope_spans.spans:
                    # Parse span
                    attrs = dict(resource_attrs)
                    for attr in span.attributes:
                        attrs[attr.key] = self._get_attr_value(attr.value)

                    signal = OTelSignal(
                        signal_type="trace",
                        name=span.name,
                        value=f"status={span.status.code}",
                        attributes=attrs,
                        timestamp=datetime.now(),
                    )
                    self.callback(signal)

        return trace_service_pb2.ExportTraceServiceResponse()

    def _get_attr_value(self, value: Any) -> Any:
        """Extract value from AnyValue proto."""
        if value.HasField("string_value"):
            return value.string_value
        elif value.HasField("int_value"):
            return value.int_value
        elif value.HasField("double_value"):
            return value.double_value
        elif value.HasField("bool_value"):
            return value.bool_value
        return str(value)


class MetricsServicer(metrics_service_pb2_grpc.MetricsServiceServicer):
    """gRPC servicer for metrics signals."""

    def __init__(self, callback: Callable[[OTelSignal], None]):
        self.callback = callback

    def Export(
        self,
        request: metrics_service_pb2.ExportMetricsServiceRequest,
        context: grpc.ServicerContext,
    ) -> metrics_service_pb2.ExportMetricsServiceResponse:
        """Handle incoming metrics export."""
        for resource_metrics in request.resource_metrics:
            # Extract resource attributes
            resource_attrs = {}
            if resource_metrics.resource:
                for attr in resource_metrics.resource.attributes:
                    resource_attrs[attr.key] = self._get_attr_value(attr.value)

            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    # Get metric value based on type
                    value = self._extract_metric_value(metric)

                    signal = OTelSignal(
                        signal_type="metric",
                        name=metric.name,
                        value=str(value),
                        attributes=resource_attrs,
                        timestamp=datetime.now(),
                    )
                    self.callback(signal)

        return metrics_service_pb2.ExportMetricsServiceResponse()

    def _extract_metric_value(self, metric: Any) -> Any:
        """Extract value from metric based on its type."""
        if metric.HasField("gauge"):
            if metric.gauge.data_points:
                dp = metric.gauge.data_points[0]
                if dp.HasField("as_int"):
                    return dp.as_int
                return dp.as_double
        elif metric.HasField("sum"):
            if metric.sum.data_points:
                dp = metric.sum.data_points[0]
                if dp.HasField("as_int"):
                    return dp.as_int
                return dp.as_double
        elif metric.HasField("histogram") and metric.histogram.data_points:
            return metric.histogram.data_points[0].count
        return "N/A"

    def _get_attr_value(self, value: Any) -> Any:
        """Extract value from AnyValue proto."""
        if value.HasField("string_value"):
            return value.string_value
        elif value.HasField("int_value"):
            return value.int_value
        elif value.HasField("double_value"):
            return value.double_value
        elif value.HasField("bool_value"):
            return value.bool_value
        return str(value)


class LogsServicer(logs_service_pb2_grpc.LogsServiceServicer):
    """gRPC servicer for log signals."""

    def __init__(self, callback: Callable[[OTelSignal], None]):
        self.callback = callback

    def Export(
        self,
        request: logs_service_pb2.ExportLogsServiceRequest,
        context: grpc.ServicerContext,
    ) -> logs_service_pb2.ExportLogsServiceResponse:
        """Handle incoming logs export."""
        for resource_logs in request.resource_logs:
            # Extract resource attributes
            resource_attrs = {}
            if resource_logs.resource:
                for attr in resource_logs.resource.attributes:
                    resource_attrs[attr.key] = self._get_attr_value(attr.value)

            for scope_logs in resource_logs.scope_logs:
                for log_record in scope_logs.log_records:
                    # Parse log record
                    attrs = dict(resource_attrs)
                    for attr in log_record.attributes:
                        attrs[attr.key] = self._get_attr_value(attr.value)

                    # Get log body
                    body = ""
                    if log_record.body.HasField("string_value"):
                        body = log_record.body.string_value

                    signal = OTelSignal(
                        signal_type="log",
                        name=f"severity={log_record.severity_text or log_record.severity_number}",
                        value=body,
                        attributes=attrs,
                        timestamp=datetime.now(),
                    )
                    self.callback(signal)

        return logs_service_pb2.ExportLogsServiceResponse()

    def _get_attr_value(self, value: Any) -> Any:
        """Extract value from AnyValue proto."""
        if value.HasField("string_value"):
            return value.string_value
        elif value.HasField("int_value"):
            return value.int_value
        elif value.HasField("double_value"):
            return value.double_value
        elif value.HasField("bool_value"):
            return value.bool_value
        return str(value)


class OTLPReceiver:
    """Inline OTLP gRPC receiver.

    Starts a gRPC server that receives OTLP signals and emits
    them to a callback for display.

    Example:
        >>> def on_signal(signal):
        ...     print(f"{signal.signal_type}: {signal.name} = {signal.value}")
        >>>
        >>> receiver = OTLPReceiver(on_signal, port=4317)
        >>> receiver.start()
        >>> # ... run agent ...
        >>> receiver.stop()
    """

    def __init__(
        self,
        callback: Callable[[OTelSignal], None],
        port: int = 4317,
        max_workers: int = 4,
    ):
        """Initialize receiver.

        Args:
            callback: Function to call with each signal
            port: Port to listen on
            max_workers: Max gRPC worker threads
        """
        self.callback = callback
        self.port = port
        self.max_workers = max_workers
        self._server: grpc.Server | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the gRPC server in a background thread."""
        self._server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=self.max_workers)
        )

        # Add servicers
        trace_service_pb2_grpc.add_TraceServiceServicer_to_server(
            TraceServicer(self.callback), self._server
        )
        metrics_service_pb2_grpc.add_MetricsServiceServicer_to_server(
            MetricsServicer(self.callback), self._server
        )
        logs_service_pb2_grpc.add_LogsServiceServicer_to_server(
            LogsServicer(self.callback), self._server
        )

        self._server.add_insecure_port(f"[::]:{self.port}")
        self._server.start()

    def stop(self, grace: float = 0.5) -> None:
        """Stop the gRPC server.

        Args:
            grace: Grace period in seconds
        """
        if self._server:
            self._server.stop(grace)
            self._server = None

    def __enter__(self) -> OTLPReceiver:
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.stop()


def signal_to_display_event(signal: OTelSignal) -> DisplayEvent:
    """Convert OTelSignal to DisplayEvent.

    Args:
        signal: OTel signal

    Returns:
        DisplayEvent for Rich display
    """
    # Determine event type
    event_type = EventType.LOG
    if signal.signal_type == "trace":
        # Check for tool-related spans
        name_lower = signal.name.lower()
        if "tool" in name_lower:
            if "start" in name_lower or "begin" in name_lower:
                event_type = EventType.TOOL_START
            else:
                event_type = EventType.TOOL_END
        elif "security" in name_lower or "block" in name_lower:
            event_type = EventType.SECURITY
        else:
            event_type = EventType.TRACE
    elif signal.signal_type == "metric":
        event_type = EventType.METRIC

    return DisplayEvent(
        timestamp=signal.timestamp,
        event_type=event_type,
        name=signal.name,
        value=signal.value,
        attributes=signal.attributes,
    )


def create_receiver_callback(
    display_callback: Callable[[DisplayEvent], None],
) -> Callable[[OTelSignal], None]:
    """Create a receiver callback that converts signals to display events.

    Args:
        display_callback: Function to call with DisplayEvent

    Returns:
        Callback for OTLPReceiver
    """
    def callback(signal: OTelSignal) -> None:
        event = signal_to_display_event(signal)
        display_callback(event)

    return callback
