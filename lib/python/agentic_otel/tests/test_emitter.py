"""Tests for HookOTelEmitter."""

from unittest.mock import MagicMock, patch

import pytest

from agentic_otel.config import OTelConfig
from agentic_otel.semantic import AgentSemanticConventions as Sem


@pytest.fixture
def config() -> OTelConfig:
    """Create a test config."""
    return OTelConfig(
        endpoint="http://test-collector:4317",
        resource_attributes={"test": "value"},
    )


class TestHookOTelEmitterInit:
    """Tests for HookOTelEmitter initialization."""

    def test_initializes_otel(self, config: OTelConfig) -> None:
        """Test that emitter initializes OTel SDK."""
        with patch("agentic_otel.emitter.initialize_otel") as mock_init:
            with patch("agentic_otel.emitter.get_tracer") as mock_get_tracer:
                mock_get_tracer.return_value = MagicMock()

                from agentic_otel.emitter import HookOTelEmitter

                _emitter = HookOTelEmitter(config)

                mock_init.assert_called_once_with(config)

    def test_gets_tracer(self, config: OTelConfig) -> None:
        """Test that emitter gets a tracer."""
        with patch("agentic_otel.emitter.initialize_otel"):
            with patch("agentic_otel.emitter.get_tracer") as mock_get_tracer:
                mock_get_tracer.return_value = MagicMock()

                from agentic_otel.emitter import HookOTelEmitter

                _emitter = HookOTelEmitter(config)

                mock_get_tracer.assert_called_once_with("agentic.hooks")


class TestStartToolSpan:
    """Tests for start_tool_span context manager."""

    def test_creates_span_with_attributes(self, config: OTelConfig) -> None:
        """Test that span is created with correct attributes."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        with patch("agentic_otel.emitter.initialize_otel"):
            with patch("agentic_otel.emitter.get_tracer", return_value=mock_tracer):
                with patch("agentic_otel.emitter.trace.use_span"):
                    from agentic_otel.emitter import HookOTelEmitter

                    emitter = HookOTelEmitter(config)

                    with emitter.start_tool_span("Bash", "toolu_123", {"command": "ls -la"}):
                        pass

                    mock_tracer.start_span.assert_called_once()
                    call_kwargs = mock_tracer.start_span.call_args
                    assert call_kwargs.kwargs["name"] == "tool.Bash"
                    assert call_kwargs.kwargs["attributes"][Sem.TOOL_NAME] == "Bash"
                    assert call_kwargs.kwargs["attributes"][Sem.TOOL_USE_ID] == "toolu_123"

    def test_sets_success_on_normal_exit(self, config: OTelConfig) -> None:
        """Test that success is set when context exits normally."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        with patch("agentic_otel.emitter.initialize_otel"):
            with patch("agentic_otel.emitter.get_tracer", return_value=mock_tracer):
                with patch("agentic_otel.emitter.trace.use_span"):
                    from agentic_otel.emitter import HookOTelEmitter

                    emitter = HookOTelEmitter(config)

                    with emitter.start_tool_span("Bash", "toolu_123", {}):
                        pass

                    mock_span.set_attribute.assert_any_call(Sem.TOOL_SUCCESS, True)

    def test_sets_failure_on_exception(self, config: OTelConfig) -> None:
        """Test that failure is set when exception occurs."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        with patch("agentic_otel.emitter.initialize_otel"):
            with patch("agentic_otel.emitter.get_tracer", return_value=mock_tracer):
                with patch("agentic_otel.emitter.trace.use_span"):
                    from agentic_otel.emitter import HookOTelEmitter

                    emitter = HookOTelEmitter(config)

                    with pytest.raises(ValueError):
                        with emitter.start_tool_span("Bash", "toolu_123", {}):
                            raise ValueError("Test error")

                    mock_span.set_attribute.assert_any_call(Sem.TOOL_SUCCESS, False)
                    mock_span.record_exception.assert_called_once()

    def test_records_duration(self, config: OTelConfig) -> None:
        """Test that duration is recorded."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        with patch("agentic_otel.emitter.initialize_otel"):
            with patch("agentic_otel.emitter.get_tracer", return_value=mock_tracer):
                with patch("agentic_otel.emitter.trace.use_span"):
                    from agentic_otel.emitter import HookOTelEmitter

                    emitter = HookOTelEmitter(config)

                    with emitter.start_tool_span("Bash", "toolu_123", {}):
                        pass

                    # Check that duration was set (we can't check the exact value)
                    duration_calls = [
                        call
                        for call in mock_span.set_attribute.call_args_list
                        if call[0][0] == Sem.TOOL_DURATION_MS
                    ]
                    assert len(duration_calls) == 1

    def test_truncates_long_input(self, config: OTelConfig) -> None:
        """Test that long inputs are truncated."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        with patch("agentic_otel.emitter.initialize_otel"):
            with patch("agentic_otel.emitter.get_tracer", return_value=mock_tracer):
                with patch("agentic_otel.emitter.trace.use_span"):
                    from agentic_otel.emitter import HookOTelEmitter

                    emitter = HookOTelEmitter(config)
                    long_input = {"data": "x" * 2000}

                    with emitter.start_tool_span(
                        "Bash", "toolu_123", long_input, max_input_length=100
                    ):
                        pass

                    call_kwargs = mock_tracer.start_span.call_args
                    input_str = call_kwargs.kwargs["attributes"][Sem.TOOL_INPUT]
                    assert len(input_str) <= 100


class TestEmitSecurityEvent:
    """Tests for emit_security_event method."""

    def test_adds_event_to_current_span(self, config: OTelConfig) -> None:
        """Test that event is added to current span."""
        mock_current_span = MagicMock()
        mock_current_span.is_recording.return_value = True

        with patch("agentic_otel.emitter.initialize_otel"):
            with patch("agentic_otel.emitter.get_tracer", return_value=MagicMock()):
                with patch(
                    "agentic_otel.emitter.trace.get_current_span",
                    return_value=mock_current_span,
                ):
                    from agentic_otel.emitter import HookOTelEmitter

                    emitter = HookOTelEmitter(config)

                    emitter.emit_security_event(
                        hook_type="pre_tool_use",
                        decision="block",
                        tool_name="Bash",
                        tool_use_id="toolu_123",
                        reason="Dangerous command",
                        validators=["bash_validator"],
                    )

                    mock_current_span.add_event.assert_called_once()
                    call_kwargs = mock_current_span.add_event.call_args
                    assert call_kwargs.kwargs["name"] == Sem.EVENT_SECURITY_DECISION
                    assert call_kwargs.kwargs["attributes"][Sem.HOOK_DECISION] == "block"
                    assert call_kwargs.kwargs["attributes"][Sem.HOOK_REASON] == "Dangerous command"


class TestRecordToolOutput:
    """Tests for record_tool_output method."""

    def test_sets_output_attributes(self, config: OTelConfig) -> None:
        """Test that output attributes are set."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        with patch("agentic_otel.emitter.initialize_otel"):
            with patch("agentic_otel.emitter.get_tracer", return_value=mock_tracer):
                with patch("agentic_otel.emitter.trace.use_span"):
                    from agentic_otel.emitter import HookOTelEmitter

                    emitter = HookOTelEmitter(config)

                    with emitter.start_tool_span("Bash", "toolu_123", {}) as span:
                        emitter.record_tool_output(span, "file1.txt\nfile2.txt", success=True)

                    mock_span.set_attribute.assert_any_call(
                        Sem.TOOL_OUTPUT_PREVIEW, "file1.txt\nfile2.txt"
                    )

    def test_truncates_long_output(self, config: OTelConfig) -> None:
        """Test that long outputs are truncated."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        with patch("agentic_otel.emitter.initialize_otel"):
            with patch("agentic_otel.emitter.get_tracer", return_value=mock_tracer):
                with patch("agentic_otel.emitter.trace.use_span"):
                    from agentic_otel.emitter import HookOTelEmitter

                    emitter = HookOTelEmitter(config)
                    long_output = "x" * 1000

                    with emitter.start_tool_span("Bash", "toolu_123", {}) as span:
                        emitter.record_tool_output(span, long_output, max_output_length=100)

                    output_calls = [
                        call
                        for call in mock_span.set_attribute.call_args_list
                        if call[0][0] == Sem.TOOL_OUTPUT_PREVIEW
                    ]
                    assert len(output_calls) >= 1
                    assert len(output_calls[-1][0][1]) <= 100
