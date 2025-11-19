"""Tests for Pydantic models - 100% coverage required"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from analytics.models import (
    AnalyticsConfig,
    ClaudePostToolUseInput,
    ClaudePreToolUseInput,
    ClaudeSessionEndInput,
    ClaudeSessionStartInput,
    ClaudeUserPromptSubmitInput,
    CompactContext,
    EventMetadata,
    NormalizedEvent,
    SessionContext,
    ToolExecutionContext,
    UserPromptContext,
)


class TestClaudeHookInputModels:
    """Test Claude hook input models"""

    def test_claude_pre_tool_use_valid(self, claude_pre_tool_use_fixture: dict) -> None:
        """Test valid PreToolUse input"""
        model = ClaudePreToolUseInput.model_validate(claude_pre_tool_use_fixture)
        assert model.hook_event_name == "PreToolUse"
        assert model.tool_name == "Write"
        assert model.session_id == "abc123-def456-ghi789"
        assert "file_path" in model.tool_input

    def test_claude_post_tool_use_valid(self, claude_post_tool_use_fixture: dict) -> None:
        """Test valid PostToolUse input"""
        model = ClaudePostToolUseInput.model_validate(claude_post_tool_use_fixture)
        assert model.hook_event_name == "PostToolUse"
        assert model.tool_name == "Write"
        assert "tool_response" in model.model_dump()
        assert model.tool_response["success"] is True

    def test_claude_user_prompt_submit_valid(self, claude_user_prompt_submit_fixture: dict) -> None:
        """Test valid UserPromptSubmit input"""
        model = ClaudeUserPromptSubmitInput.model_validate(claude_user_prompt_submit_fixture)
        assert model.hook_event_name == "UserPromptSubmit"
        assert "Hello World" in model.prompt

    def test_claude_session_start_valid(self, claude_session_start_fixture: dict) -> None:
        """Test valid SessionStart input"""
        model = ClaudeSessionStartInput.model_validate(claude_session_start_fixture)
        assert model.hook_event_name == "SessionStart"
        assert model.source == "startup"

    def test_claude_session_end_valid(self, claude_session_end_fixture: dict) -> None:
        """Test valid SessionEnd input"""
        model = ClaudeSessionEndInput.model_validate(claude_session_end_fixture)
        assert model.hook_event_name == "SessionEnd"
        assert model.reason == "exit"

    def test_invalid_permission_mode(self, claude_pre_tool_use_fixture: dict) -> None:
        """Test invalid permission mode raises validation error"""
        invalid = claude_pre_tool_use_fixture.copy()
        invalid["permission_mode"] = "invalid_mode"
        with pytest.raises(ValidationError):
            ClaudePreToolUseInput.model_validate(invalid)

    def test_missing_required_field(self, claude_pre_tool_use_fixture: dict) -> None:
        """Test missing required field raises validation error"""
        invalid = claude_pre_tool_use_fixture.copy()
        del invalid["session_id"]
        with pytest.raises(ValidationError):
            ClaudePreToolUseInput.model_validate(invalid)


class TestHookInputConverter:
    """Test HookInput model and conversion methods"""

    def test_hook_input_to_claude_pre_tool_use(self, claude_pre_tool_use_fixture: dict) -> None:
        """Test converting HookInput to Claude PreToolUse"""
        from analytics.models.hook_input import HookInput

        hook_input = HookInput(
            provider="claude", event="PreToolUse", data=claude_pre_tool_use_fixture
        )
        claude_input = hook_input.to_claude_input()
        assert claude_input.hook_event_name == "PreToolUse"
        assert claude_input.tool_name == "Write"

    def test_hook_input_to_claude_post_tool_use(self, claude_post_tool_use_fixture: dict) -> None:
        """Test converting HookInput to Claude PostToolUse"""
        from analytics.models.hook_input import HookInput

        hook_input = HookInput(
            provider="claude", event="PostToolUse", data=claude_post_tool_use_fixture
        )
        claude_input = hook_input.to_claude_input()
        assert claude_input.hook_event_name == "PostToolUse"

    def test_hook_input_to_claude_user_prompt_submit(
        self, claude_user_prompt_submit_fixture: dict
    ) -> None:
        """Test converting HookInput to Claude UserPromptSubmit"""
        from analytics.models.hook_input import HookInput

        hook_input = HookInput(
            provider="claude",
            event="UserPromptSubmit",
            data=claude_user_prompt_submit_fixture,
        )
        claude_input = hook_input.to_claude_input()
        assert claude_input.hook_event_name == "UserPromptSubmit"

    def test_hook_input_to_claude_session_start(self, claude_session_start_fixture: dict) -> None:
        """Test converting HookInput to Claude SessionStart"""
        from analytics.models.hook_input import HookInput

        hook_input = HookInput(
            provider="claude", event="SessionStart", data=claude_session_start_fixture
        )
        claude_input = hook_input.to_claude_input()
        assert claude_input.hook_event_name == "SessionStart"

    def test_hook_input_to_claude_session_end(self, claude_session_end_fixture: dict) -> None:
        """Test converting HookInput to Claude SessionEnd"""
        from analytics.models.hook_input import HookInput

        hook_input = HookInput(
            provider="claude", event="SessionEnd", data=claude_session_end_fixture
        )
        claude_input = hook_input.to_claude_input()
        assert claude_input.hook_event_name == "SessionEnd"

    def test_hook_input_to_claude_notification(self, claude_hooks_dir: any) -> None:
        """Test converting HookInput to Claude Notification"""
        import json

        from analytics.models.hook_input import HookInput

        with open(claude_hooks_dir / "notification.json") as f:
            fixture = json.load(f)

        hook_input = HookInput(provider="claude", event="Notification", data=fixture)
        claude_input = hook_input.to_claude_input()
        assert claude_input.hook_event_name == "Notification"

    def test_hook_input_to_claude_stop(self, claude_hooks_dir: any) -> None:
        """Test converting HookInput to Claude Stop"""
        import json

        from analytics.models.hook_input import HookInput

        with open(claude_hooks_dir / "stop.json") as f:
            fixture = json.load(f)

        hook_input = HookInput(provider="claude", event="Stop", data=fixture)
        claude_input = hook_input.to_claude_input()
        assert claude_input.hook_event_name == "Stop"

    def test_hook_input_to_claude_pre_compact(self, claude_hooks_dir: any) -> None:
        """Test converting HookInput to Claude PreCompact"""
        import json

        from analytics.models.hook_input import HookInput

        with open(claude_hooks_dir / "pre_compact.json") as f:
            fixture = json.load(f)

        hook_input = HookInput(provider="claude", event="PreCompact", data=fixture)
        claude_input = hook_input.to_claude_input()
        assert claude_input.hook_event_name == "PreCompact"

    def test_hook_input_unknown_event(self) -> None:
        """Test unknown event type raises ValueError"""
        from analytics.models.hook_input import HookInput

        hook_input = HookInput(
            provider="claude",
            event="UnknownEvent",
            data={
                "session_id": "test",
                "transcript_path": "/path",
                "cwd": "/cwd",
                "permission_mode": "default",
                "hook_event_name": "UnknownEvent",
            },
        )
        with pytest.raises(ValueError, match="Unknown Claude hook event"):
            hook_input.to_claude_input()

    def test_hook_input_adds_hook_event_name(self, claude_pre_tool_use_fixture: dict) -> None:
        """Test that hook_event_name is added if missing"""
        from analytics.models.hook_input import HookInput

        data = claude_pre_tool_use_fixture.copy()
        del data["hook_event_name"]

        hook_input = HookInput(provider="claude", event="PreToolUse", data=data)
        claude_input = hook_input.to_claude_input()
        assert claude_input.hook_event_name == "PreToolUse"


class TestNormalizedEventModels:
    """Test normalized event models"""

    def test_normalized_event_valid(self, normalized_tool_execution_started: dict) -> None:
        """Test valid normalized event"""
        model = NormalizedEvent.model_validate(normalized_tool_execution_started)
        assert model.event_type == "tool_execution_started"
        assert model.provider == "claude"
        assert model.session_id == "abc123-def456-ghi789"
        assert isinstance(model.timestamp, datetime)

    def test_normalized_event_serialization(self, normalized_tool_execution_started: dict) -> None:
        """Test normalized event serialization"""
        model = NormalizedEvent.model_validate(normalized_tool_execution_started)
        json_str = model.model_dump_json()
        assert "tool_execution_started" in json_str
        assert "abc123-def456-ghi789" in json_str

    def test_tool_execution_context(self) -> None:
        """Test ToolExecutionContext model"""
        context = ToolExecutionContext(
            tool_name="Write",
            tool_input={"file_path": "test.py"},
            tool_use_id="test_id",
        )
        assert context.tool_name == "Write"
        assert context.tool_response is None

    def test_user_prompt_context(self) -> None:
        """Test UserPromptContext model"""
        context = UserPromptContext(prompt="Test prompt", prompt_length=11)
        assert context.prompt == "Test prompt"
        assert context.prompt_length == 11

    def test_session_context(self) -> None:
        """Test SessionContext model"""
        context = SessionContext(source="startup")
        assert context.source == "startup"
        assert context.reason is None

    def test_compact_context(self) -> None:
        """Test CompactContext model"""
        context = CompactContext(trigger="manual", custom_instructions="test")
        assert context.trigger == "manual"
        assert context.custom_instructions == "test"

    def test_event_metadata(self) -> None:
        """Test EventMetadata model"""
        metadata = EventMetadata(hook_event_name="PreToolUse")
        assert metadata.hook_event_name == "PreToolUse"
        assert metadata.transcript_path is None


class TestAnalyticsConfig:
    """Test analytics configuration model"""

    def test_config_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test configuration with defaults"""
        monkeypatch.delenv("ANALYTICS_PROVIDER", raising=False)
        config = AnalyticsConfig()
        assert config.provider == "unknown"  # Provider is set by hook caller
        assert config.publisher_backend == "file"
        assert config.api_timeout == 30
        assert config.retry_attempts == 3

    def test_config_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test configuration loaded from environment variables"""
        monkeypatch.setenv("ANALYTICS_PROVIDER", "openai")
        monkeypatch.setenv("ANALYTICS_PUBLISHER_BACKEND", "api")
        monkeypatch.setenv("ANALYTICS_API_ENDPOINT", "https://api.example.com")
        monkeypatch.setenv("ANALYTICS_API_TIMEOUT", "60")

        config = AnalyticsConfig()
        assert config.provider == "openai"
        assert config.publisher_backend == "api"
        assert config.api_endpoint == "https://api.example.com"
        assert config.api_timeout == 60

    def test_validate_backend_config_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """Test backend validation for file backend"""
        output_path = tmp_path / "analytics.jsonl"
        monkeypatch.setenv("ANALYTICS_OUTPUT_PATH", str(output_path))

        config = AnalyticsConfig()
        config.validate_backend_config()  # Should not raise

    def test_validate_backend_config_file_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test backend validation fails when file backend missing output_path"""
        monkeypatch.delenv("ANALYTICS_OUTPUT_PATH", raising=False)
        config = AnalyticsConfig(publisher_backend="file")

        with pytest.raises(ValueError, match="output_path is required"):
            config.validate_backend_config()

    def test_validate_backend_config_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test backend validation for API backend"""
        monkeypatch.setenv("ANALYTICS_API_ENDPOINT", "https://api.example.com")
        config = AnalyticsConfig(publisher_backend="api")
        config.validate_backend_config()  # Should not raise

    def test_validate_backend_config_api_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test backend validation fails when API backend missing endpoint"""
        monkeypatch.delenv("ANALYTICS_API_ENDPOINT", raising=False)
        config = AnalyticsConfig(publisher_backend="api")

        with pytest.raises(ValueError, match="api_endpoint is required"):
            config.validate_backend_config()

    def test_get_output_path_resolved(self, monkeypatch: pytest.MonkeyPatch, tmp_path: any) -> None:
        """Test output path resolution and directory creation"""
        output_path = tmp_path / "subdir" / "analytics.jsonl"
        monkeypatch.setenv("ANALYTICS_OUTPUT_PATH", str(output_path))

        config = AnalyticsConfig()
        resolved = config.get_output_path_resolved()

        assert resolved.parent.exists()
        assert str(resolved) == str(output_path)

    def test_get_output_path_not_set(self) -> None:
        """Test get_output_path_resolved fails when output_path not set"""
        config = AnalyticsConfig()
        config.output_path = None

        with pytest.raises(ValueError, match="output_path is not configured"):
            config.get_output_path_resolved()
