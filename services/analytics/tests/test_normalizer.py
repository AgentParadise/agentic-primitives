"""Tests for event normalization logic

Following TDD: write tests first, then implement EventNormalizer
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from analytics.models.events import (
    CompactContext,
    EventMetadata,
    NormalizedEvent,
    NotificationContext,
    SessionContext,
    StopContext,
    ToolExecutionContext,
    UserPromptContext,
)
from analytics.models.hook_input import HookInput

# Test fixtures path
FIXTURES_DIR = Path(__file__).parent / "fixtures"
CLAUDE_HOOKS_DIR = FIXTURES_DIR / "claude_hooks"


@pytest.fixture
def pre_tool_use_input() -> HookInput:
    """Load PreToolUse hook input fixture"""
    with open(CLAUDE_HOOKS_DIR / "pre_tool_use.json") as f:
        data = json.load(f)
    return HookInput(provider="claude", event="PreToolUse", data=data)


@pytest.fixture
def post_tool_use_input() -> HookInput:
    """Load PostToolUse hook input fixture"""
    with open(CLAUDE_HOOKS_DIR / "post_tool_use.json") as f:
        data = json.load(f)
    return HookInput(provider="claude", event="PostToolUse", data=data)


@pytest.fixture
def session_start_input() -> HookInput:
    """Load SessionStart hook input fixture"""
    with open(CLAUDE_HOOKS_DIR / "session_start.json") as f:
        data = json.load(f)
    return HookInput(provider="claude", event="SessionStart", data=data)


@pytest.fixture
def session_end_input() -> HookInput:
    """Load SessionEnd hook input fixture"""
    with open(CLAUDE_HOOKS_DIR / "session_end.json") as f:
        data = json.load(f)
    return HookInput(provider="claude", event="SessionEnd", data=data)


@pytest.fixture
def user_prompt_submit_input() -> HookInput:
    """Load UserPromptSubmit hook input fixture"""
    with open(CLAUDE_HOOKS_DIR / "user_prompt_submit.json") as f:
        data = json.load(f)
    return HookInput(provider="claude", event="UserPromptSubmit", data=data)


@pytest.fixture
def notification_input() -> HookInput:
    """Load Notification hook input fixture"""
    with open(CLAUDE_HOOKS_DIR / "notification.json") as f:
        data = json.load(f)
    return HookInput(provider="claude", event="Notification", data=data)


@pytest.fixture
def stop_input() -> HookInput:
    """Load Stop hook input fixture"""
    with open(CLAUDE_HOOKS_DIR / "stop.json") as f:
        data = json.load(f)
    return HookInput(provider="claude", event="Stop", data=data)


@pytest.fixture
def pre_compact_input() -> HookInput:
    """Load PreCompact hook input fixture"""
    with open(CLAUDE_HOOKS_DIR / "pre_compact.json") as f:
        data = json.load(f)
    return HookInput(provider="claude", event="PreCompact", data=data)


@pytest.mark.unit
class TestEventNormalizerBasics:
    """Test basic EventNormalizer functionality"""

    def test_normalizer_imports(self) -> None:
        """Test that EventNormalizer can be imported"""
        # This will fail until we implement it
        from analytics.normalizer import EventNormalizer  # noqa: F401

    def test_normalizer_instantiation(self) -> None:
        """Test that EventNormalizer can be instantiated"""
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        assert normalizer is not None

    def test_normalizer_has_normalize_method(self) -> None:
        """Test that EventNormalizer has normalize method"""
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        assert hasattr(normalizer, "normalize")
        assert callable(normalizer.normalize)


@pytest.mark.unit
class TestEventNormalizerToolEvents:
    """Test normalization of tool-related events"""

    def test_normalize_pre_tool_use(self, pre_tool_use_input: HookInput) -> None:
        """Test normalization of PreToolUse event"""
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        event = normalizer.normalize(pre_tool_use_input)

        # Validate model
        assert isinstance(event, NormalizedEvent)

        # Check event type mapping
        assert event.event_type == "tool_execution_started"
        assert event.provider == "claude"
        assert event.session_id == "abc123-def456-ghi789"

        # Check timestamp is recent and ISO 8601 format
        assert isinstance(event.timestamp, datetime)
        assert event.timestamp.tzinfo is not None

        # Check context
        assert isinstance(event.context, ToolExecutionContext)
        assert event.context.tool_name == "Write"
        assert event.context.tool_input == {
            "file_path": "src/main.py",
            "contents": "print('Hello, World!')\n",
        }
        assert event.context.tool_use_id == "toolu_01ABC123DEF456"
        assert event.context.tool_response is None

        # Check metadata
        assert isinstance(event.metadata, EventMetadata)
        assert event.metadata.hook_event_name == "PreToolUse"
        assert (
            event.metadata.transcript_path
            == "/Users/dev/.claude/projects/test-project/00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl"
        )
        assert event.metadata.permission_mode == "default"

        # Check cwd
        assert event.cwd == "/Users/dev/agentic-primitives"

    def test_normalize_post_tool_use(self, post_tool_use_input: HookInput) -> None:
        """Test normalization of PostToolUse event"""
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        event = normalizer.normalize(post_tool_use_input)

        assert event.event_type == "tool_execution_completed"
        assert isinstance(event.context, ToolExecutionContext)
        assert event.context.tool_name == "Write"
        assert event.context.tool_response is not None
        assert event.context.tool_response == {"file_path": "src/main.py", "success": True}


@pytest.mark.unit
class TestEventNormalizerSessionEvents:
    """Test normalization of session-related events"""

    def test_normalize_session_start(self, session_start_input: HookInput) -> None:
        """Test normalization of SessionStart event"""
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        event = normalizer.normalize(session_start_input)

        assert event.event_type == "session_started"
        assert event.provider == "claude"
        assert event.session_id == "abc123-def456-ghi789"

        # Check context
        assert isinstance(event.context, SessionContext)
        assert event.context.source == "startup"
        assert event.context.reason is None

        # Check metadata
        assert event.metadata.hook_event_name == "SessionStart"

    def test_normalize_session_end(self, session_end_input: HookInput) -> None:
        """Test normalization of SessionEnd event"""
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        event = normalizer.normalize(session_end_input)

        assert event.event_type == "session_completed"
        assert isinstance(event.context, SessionContext)
        assert event.context.reason == "exit"
        assert event.context.source is None


@pytest.mark.unit
class TestEventNormalizerUserEvents:
    """Test normalization of user interaction events"""

    def test_normalize_user_prompt_submit(
        self, user_prompt_submit_input: HookInput
    ) -> None:
        """Test normalization of UserPromptSubmit event"""
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        event = normalizer.normalize(user_prompt_submit_input)

        assert event.event_type == "user_prompt_submitted"
        assert isinstance(event.context, UserPromptContext)
        assert event.context.prompt == "Write a Python script that prints Hello World"
        assert event.context.prompt_length == len("Write a Python script that prints Hello World")

    def test_normalize_notification(self, notification_input: HookInput) -> None:
        """Test normalization of Notification event"""
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        event = normalizer.normalize(notification_input)

        assert event.event_type == "system_notification"
        assert isinstance(event.context, NotificationContext)
        assert event.context.notification_type == "permission_prompt"
        assert "permission" in event.context.message.lower()


@pytest.mark.unit
class TestEventNormalizerStopEvents:
    """Test normalization of stop events"""

    def test_normalize_stop(self, stop_input: HookInput) -> None:
        """Test normalization of Stop event"""
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        event = normalizer.normalize(stop_input)

        assert event.event_type == "agent_stopped"
        assert isinstance(event.context, StopContext)
        assert event.context.stop_hook_active is False


@pytest.mark.unit
class TestEventNormalizerCompactEvents:
    """Test normalization of compaction events"""

    def test_normalize_pre_compact(self, pre_compact_input: HookInput) -> None:
        """Test normalization of PreCompact event"""
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        event = normalizer.normalize(pre_compact_input)

        assert event.event_type == "context_compacted"
        assert isinstance(event.context, CompactContext)
        assert event.context.trigger == "auto"


@pytest.mark.unit
class TestEventNormalizerEdgeCases:
    """Test edge cases and error handling"""

    def test_missing_optional_fields(self) -> None:
        """Test normalization with minimal required fields only"""
        from analytics.normalizer import EventNormalizer

        # Create minimal SessionStart event
        minimal_input = HookInput(
            provider="claude",
            event="SessionStart",
            data={
                "session_id": "test-session",
                "hook_event_name": "SessionStart",
                "transcript_path": "/path/to/transcript.jsonl",
                "cwd": "/tmp",
                "permission_mode": "default",
                "source": "startup",
            },
        )

        normalizer = EventNormalizer()
        event = normalizer.normalize(minimal_input)

        assert event.event_type == "session_started"
        assert event.session_id == "test-session"

    def test_timestamp_is_utc(self, session_start_input: HookInput) -> None:
        """Test that generated timestamp is in UTC"""
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        event = normalizer.normalize(session_start_input)

        # Timestamp should be timezone-aware and in UTC
        assert event.timestamp.tzinfo == UTC

    def test_timestamp_is_iso8601_serializable(
        self, session_start_input: HookInput
    ) -> None:
        """Test that timestamp can be serialized to ISO 8601"""
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        event = normalizer.normalize(session_start_input)

        # Should be serializable to JSON
        timestamp_str = event.timestamp.isoformat()
        assert "T" in timestamp_str
        assert timestamp_str.endswith("+00:00") or timestamp_str.endswith("Z")

    def test_malformed_input_raises_validation_error(self) -> None:
        """Test that malformed input raises ValidationError"""
        from pydantic import ValidationError

        from analytics.normalizer import EventNormalizer

        # Missing required fields
        bad_input = HookInput(
            provider="claude",
            event="PreToolUse",
            data={"session_id": "test"},  # Missing many required fields
        )

        normalizer = EventNormalizer()
        with pytest.raises(ValidationError):
            normalizer.normalize(bad_input)

    def test_unknown_provider_still_works(self) -> None:
        """Test that unknown provider names are accepted (provider-agnostic)"""
        from analytics.normalizer import EventNormalizer

        # Use a made-up provider name
        future_provider_input = HookInput(
            provider="gemini",  # Not implemented yet
            event="SessionStart",
            data={
                "session_id": "gemini-session-123",
                "hook_event_name": "SessionStart",
                "transcript_path": "/path/to/transcript.jsonl",
                "cwd": "/tmp",
                "permission_mode": "default",
                "source": "startup",
            },
        )

        normalizer = EventNormalizer()
        event = normalizer.normalize(future_provider_input)

        # Should normalize successfully
        assert event.provider == "gemini"
        assert event.event_type == "session_started"

    def test_preserves_raw_event_in_metadata(
        self, pre_tool_use_input: HookInput
    ) -> None:
        """Test that raw event data is preserved in metadata"""
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        event = normalizer.normalize(pre_tool_use_input)

        # Raw event should be preserved
        assert event.metadata.raw_event is not None
        assert isinstance(event.metadata.raw_event, dict)
        assert event.metadata.raw_event["hook_event_name"] == "PreToolUse"


@pytest.mark.unit
class TestEventNormalizerValidation:
    """Test that normalized events validate against Pydantic models"""

    def test_normalized_event_validates(self, pre_tool_use_input: HookInput) -> None:
        """Test that normalized event is a valid NormalizedEvent"""
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        event = normalizer.normalize(pre_tool_use_input)

        # Should be able to serialize and deserialize
        event_dict = event.model_dump()
        reconstructed = NormalizedEvent.model_validate(event_dict)

        assert reconstructed.event_type == event.event_type
        assert reconstructed.session_id == event.session_id

    def test_normalized_event_json_serializable(
        self, pre_tool_use_input: HookInput
    ) -> None:
        """Test that normalized event can be serialized to JSON"""
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        event = normalizer.normalize(pre_tool_use_input)

        # Should be JSON serializable
        json_str = event.model_dump_json()
        assert isinstance(json_str, str)
        assert "tool_execution_started" in json_str

        # Should be deserializable
        reconstructed = NormalizedEvent.model_validate_json(json_str)
        assert reconstructed.event_type == event.event_type


@pytest.mark.unit
class TestEventNormalizerAllEventTypes:
    """Test that all 10 hook event types are handled"""

    def test_all_event_types_covered(self) -> None:
        """Test that normalizer handles all 10 Claude hook event types"""
        from analytics.models.events import HOOK_EVENT_TO_ANALYTICS_EVENT
        from analytics.normalizer import EventNormalizer

        EventNormalizer()

        # All hook event types from the spec
        all_hook_events = [
            "SessionStart",
            "SessionEnd",
            "UserPromptSubmit",
            "PreToolUse",
            "PostToolUse",
            "PermissionRequest",
            "Stop",
            "SubagentStop",
            "Notification",
            "PreCompact",
        ]

        # Verify all are in mapping
        for hook_event in all_hook_events:
            assert hook_event in HOOK_EVENT_TO_ANALYTICS_EVENT

        # Verify mapping count
        assert len(HOOK_EVENT_TO_ANALYTICS_EVENT) == 10

    def test_unknown_event_type_raises_value_error(self) -> None:
        """Test that unknown event type raises ValueError"""
        from analytics.normalizer import EventNormalizer

        # Create input with unknown event type
        unknown_input = HookInput(
            provider="claude",
            event="UnknownEvent",
            data={
                "session_id": "test-session",
                "hook_event_name": "UnknownEvent",
                "transcript_path": "/path/to/transcript.jsonl",
                "cwd": "/tmp",
                "permission_mode": "default",
            },
        )

        normalizer = EventNormalizer()
        with pytest.raises(ValueError, match="Unknown hook event type: UnknownEvent"):
            normalizer.normalize(unknown_input)


@pytest.mark.unit
class TestEventNormalizerExtensibility:
    """Test normalizer extensibility features"""

    def test_register_custom_adapter(self) -> None:
        """Test registering a custom provider adapter"""
        from analytics.adapters.claude import ClaudeAdapter
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()

        # Register a custom adapter (reuse Claude adapter for testing)
        custom_adapter = ClaudeAdapter()
        normalizer.register_adapter("gemini", custom_adapter)

        # Verify adapter is registered
        assert "gemini" in normalizer.get_supported_providers()

    def test_get_supported_providers(self) -> None:
        """Test getting list of supported providers"""
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        providers = normalizer.get_supported_providers()

        # Should include default providers
        assert "claude" in providers
        assert "openai" in providers
        assert len(providers) == 2

    def test_register_adapter_case_insensitive(self) -> None:
        """Test that provider names are case-insensitive"""
        from analytics.adapters.claude import ClaudeAdapter
        from analytics.normalizer import EventNormalizer

        normalizer = EventNormalizer()
        custom_adapter = ClaudeAdapter()

        # Register with mixed case
        normalizer.register_adapter("Gemini", custom_adapter)

        # Should be stored as lowercase
        assert "gemini" in normalizer.get_supported_providers()

