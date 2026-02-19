"""Consumer contract tests for AEF's usage of agentic-primitives.

These tests verify that the public API surface consumed by AEF remains
stable across agentic-primitives releases. Each test corresponds to an
actual import or usage pattern found in the AEF codebase.

If any test here breaks, it means a change in agentic-primitives would
break the downstream AEF consumer.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# agentic_logging
# ---------------------------------------------------------------------------


class TestAEFLoggingContract:
    """Contract: AEF imports get_logger, setup_logging, LogConfig."""

    def test_import_get_logger(self) -> None:
        from agentic_logging import get_logger

        assert callable(get_logger)

    def test_import_setup_logging(self) -> None:
        from agentic_logging import setup_logging

        assert callable(setup_logging)

    def test_import_log_config(self) -> None:
        from agentic_logging import LogConfig

        assert LogConfig is not None


# ---------------------------------------------------------------------------
# agentic_events
# ---------------------------------------------------------------------------


class TestAEFEventsContract:
    """Contract: AEF imports EventEmitter, parse_jsonl_line, enrich_event,
    EventType, Recording, SessionPlayer, load_recording,
    RecordingMetadata, BatchBuffer.
    """

    # -- Import availability --------------------------------------------------

    def test_import_event_emitter(self) -> None:
        from agentic_events import EventEmitter

        assert EventEmitter is not None

    def test_import_parse_jsonl_line(self) -> None:
        from agentic_events import parse_jsonl_line

        assert callable(parse_jsonl_line)

    def test_import_enrich_event(self) -> None:
        from agentic_events import enrich_event

        assert callable(enrich_event)

    def test_import_event_type(self) -> None:
        from agentic_events import EventType

        assert EventType is not None

    def test_import_recording(self) -> None:
        from agentic_events import Recording

        assert Recording is not None

    def test_import_session_player(self) -> None:
        from agentic_events import SessionPlayer

        assert SessionPlayer is not None

    def test_import_load_recording(self) -> None:
        from agentic_events import load_recording

        assert callable(load_recording)

    def test_import_recording_metadata(self) -> None:
        from agentic_events import RecordingMetadata

        assert RecordingMetadata is not None

    def test_import_batch_buffer(self) -> None:
        from agentic_events import BatchBuffer

        assert BatchBuffer is not None

    # -- Enum value stability -------------------------------------------------

    def test_event_type_session_values(self) -> None:
        from agentic_events import EventType

        assert EventType.SESSION_STARTED == "session_started"
        assert EventType.SESSION_COMPLETED == "session_completed"

    def test_event_type_tool_values(self) -> None:
        from agentic_events import EventType

        assert EventType.TOOL_EXECUTION_STARTED == "tool_execution_started"
        assert EventType.TOOL_EXECUTION_COMPLETED == "tool_execution_completed"

    def test_recording_enum_values(self) -> None:
        from agentic_events import Recording

        assert Recording.SIMPLE_BASH == "simple-bash"
        assert Recording.MULTI_TOOL == "multi-tool"

    # -- Constructor compatibility --------------------------------------------

    def test_event_emitter_constructor(self) -> None:
        from agentic_events import EventEmitter

        buf = io.StringIO()
        emitter = EventEmitter(session_id="test-123", provider="claude", output=buf)
        assert emitter.session_id == "test-123"
        assert emitter.provider == "claude"

    def test_batch_buffer_constructor(self) -> None:
        from agentic_events import BatchBuffer

        buffer = BatchBuffer(flush_size=100, flush_interval=0.5)
        assert buffer.size == 0

    # -- Functional contracts -------------------------------------------------

    def test_parse_jsonl_line_valid(self) -> None:
        from agentic_events import parse_jsonl_line

        line = json.dumps({"event_type": "test", "timestamp": "2025-01-01T00:00:00Z"})
        result = parse_jsonl_line(line)
        assert result is not None
        assert result["event_type"] == "test"

    def test_parse_jsonl_line_invalid(self) -> None:
        from agentic_events import parse_jsonl_line

        result = parse_jsonl_line("not valid json {{{")
        assert result is None

    def test_enrich_event_adds_fields(self) -> None:
        from agentic_events import enrich_event

        event = {"event_type": "test"}
        enriched = enrich_event(event, execution_id="exec-1", phase_id="phase-1")
        assert enriched["execution_id"] == "exec-1"
        assert enriched["phase_id"] == "phase-1"

    # -- Dataclass field stability --------------------------------------------

    def test_recording_metadata_fields(self) -> None:
        from agentic_events import RecordingMetadata

        meta = RecordingMetadata(
            version=1,
            event_schema_version=1,
            cli_version="1.0.0",
            model="claude-sonnet-4-5-20250929",
            provider="claude",
            task="test task",
            recorded_at=datetime.now(UTC),
            duration_ms=1000,
            event_count=10,
            session_id="sess-1",
        )
        assert meta.version == 1
        assert meta.event_count == 10
        assert meta.session_id == "sess-1"


# ---------------------------------------------------------------------------
# agentic_isolation
# ---------------------------------------------------------------------------


class TestAEFIsolationContract:
    """Contract: AEF imports AgenticWorkspace, WorkspaceConfig, SecurityConfig,
    WorkspaceDockerProvider, SessionOutputStream, EventParser, EventType,
    ObservabilityEvent, SessionSummary, TokenUsage.
    """

    # -- Import availability --------------------------------------------------

    def test_import_agentic_workspace(self) -> None:
        from agentic_isolation import AgenticWorkspace

        assert AgenticWorkspace is not None

    def test_import_workspace_config(self) -> None:
        from agentic_isolation import WorkspaceConfig

        assert WorkspaceConfig is not None

    def test_import_security_config(self) -> None:
        from agentic_isolation import SecurityConfig

        assert SecurityConfig is not None

    def test_import_workspace_docker_provider(self) -> None:
        from agentic_isolation import WorkspaceDockerProvider

        assert WorkspaceDockerProvider is not None

    def test_import_session_output_stream(self) -> None:
        from agentic_isolation import SessionOutputStream

        assert SessionOutputStream is not None

    def test_import_event_parser(self) -> None:
        from agentic_isolation import EventParser

        assert EventParser is not None

    def test_import_event_type(self) -> None:
        from agentic_isolation import EventType

        assert EventType is not None

    def test_import_observability_event(self) -> None:
        from agentic_isolation import ObservabilityEvent

        assert ObservabilityEvent is not None

    def test_import_session_summary(self) -> None:
        from agentic_isolation import SessionSummary

        assert SessionSummary is not None

    def test_import_token_usage(self) -> None:
        from agentic_isolation import TokenUsage

        assert TokenUsage is not None

    # -- SecurityConfig classmethods ------------------------------------------

    def test_security_config_production(self) -> None:
        from agentic_isolation import SecurityConfig

        prod = SecurityConfig.production()
        assert prod.cap_drop_all is True
        assert prod.no_new_privileges is True
        assert prod.read_only_root is True

    def test_security_config_development(self) -> None:
        from agentic_isolation import SecurityConfig

        dev = SecurityConfig.development()
        assert dev.read_only_root is False
        assert dev.use_gvisor is False

    # -- Enum stability -------------------------------------------------------

    def test_isolation_event_type_values(self) -> None:
        from agentic_isolation import EventType

        assert EventType.SESSION_STARTED == "session_started"
        assert EventType.SESSION_COMPLETED == "session_completed"
        assert EventType.TOOL_EXECUTION_STARTED == "tool_execution_started"
        assert EventType.TOOL_EXECUTION_COMPLETED == "tool_execution_completed"

    # -- SessionSummary fields + to_dict() ------------------------------------

    def test_session_summary_fields_and_to_dict(self) -> None:
        from agentic_isolation import SessionSummary

        summary = SessionSummary(
            session_id="sess-1",
            started_at=datetime.now(UTC),
            event_count=5,
            tool_calls={"Bash": 3, "Read": 2},
            num_turns=2,
            total_input_tokens=1000,
            total_output_tokens=500,
        )
        assert summary.session_id == "sess-1"
        assert summary.event_count == 5
        assert summary.total_tool_calls == 5

        d = summary.to_dict()
        assert d["session_id"] == "sess-1"
        assert d["event_count"] == 5
