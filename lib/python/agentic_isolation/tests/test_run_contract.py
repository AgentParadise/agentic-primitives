"""Tests for AgentRunSpec/AgentRunResult contract (Plan 1b Task 2).

Covers: AgentRunSpec (recipe + task + credentials + limits) validation,
AgentRunCredentials rejecting unknown harness keys, AgentRunResult required
fields, and the AgentRunEvent discriminated union.
"""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agentic_isolation.agent_run_events import (
    AgentRunEvent,
    AgentRunEventEnvelope,
    SessionEndEvent,
    TokenUsageEvent,
    ToolEndEvent,
    ToolStartEvent,
)
from agentic_isolation.agent_run_result import AgentRunOutcome, AgentRunResult
from agentic_isolation.agent_run_spec import (
    AgentRunCredentials,
    AgentRunSpec,
    ClaudeCredentials,
    CodexCredentials,
    ObservabilityExporter,
)
from agentic_isolation.recipe import AgentRecipe

RECIPE: dict[str, Any] = {
    "name": "quick-fix",
    "agent": "claude",
    "model": {
        "name": "anthropic/claude-opus-4-8",
        "effort": "low",
    },
}


class TestRunSpec:
    def test_full_agent_run_spec_validates(self) -> None:
        spec = AgentRunSpec.model_validate(
            {
                "recipe": RECIPE,
                "task": "Fix the failing test in test_foo.py",
                "input_artifacts": ["/tmp/input.txt"],
                "credentials": {"claude": {"oauth_token": "sk-oauth-token"}},
                "observability": [{"name": "otel", "config": {"endpoint": "http://x"}}],
                "limits": {"timeout_s": 300.0, "token_budget": 100000},
            }
        )

        assert isinstance(spec.recipe, AgentRecipe)
        assert spec.task == "Fix the failing test in test_foo.py"
        assert spec.input_artifacts == (Path("/tmp/input.txt"),)
        assert spec.credentials.claude is not None
        assert spec.credentials.claude.oauth_token == "sk-oauth-token"
        assert spec.limits is not None
        assert spec.limits.timeout_s == 300.0
        assert spec.limits.token_budget == 100000

    def test_minimal_agent_run_spec_defaults(self) -> None:
        spec = AgentRunSpec.model_validate(
            {
                "recipe": RECIPE,
                "task": "Do the thing",
                "credentials": {},
            }
        )

        assert spec.input_artifacts == ()
        assert spec.observability == ()
        assert spec.limits is None
        assert spec.credentials.claude is None
        assert spec.credentials.codex is None

    def test_agent_run_spec_is_frozen(self) -> None:
        spec = AgentRunSpec.model_validate({"recipe": RECIPE, "task": "task", "credentials": {}})
        with pytest.raises(ValidationError):
            spec.task = "renamed"  # type: ignore[misc]

    def test_unknown_top_level_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentRunSpec.model_validate(
                {
                    "recipe": RECIPE,
                    "task": "task",
                    "credentials": {},
                    "temperature": 0.7,
                }
            )


class TestRunCredentials:
    def test_claude_credentials(self) -> None:
        creds = AgentRunCredentials.model_validate({"claude": {"oauth_token": "tok"}})
        assert creds.claude == ClaudeCredentials(oauth_token="tok")
        assert creds.codex is None

    def test_codex_credentials(self) -> None:
        creds = AgentRunCredentials.model_validate({"codex": {"auth_json": "{}"}})
        assert creds.codex == CodexCredentials(auth_json="{}")
        assert creds.claude is None

    def test_both_credentials(self) -> None:
        creds = AgentRunCredentials.model_validate(
            {
                "claude": {"oauth_token": "tok"},
                "codex": {"auth_json": "{}"},
            }
        )
        assert creds.claude is not None
        assert creds.codex is not None

    def test_unknown_harness_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentRunCredentials.model_validate({"gemini": {"api_key": "x"}})

    def test_empty_credentials_allowed(self) -> None:
        creds = AgentRunCredentials.model_validate({})
        assert creds.claude is None
        assert creds.codex is None

    def test_claude_credentials_frozen_and_forbid_extra(self) -> None:
        creds = ClaudeCredentials(oauth_token="tok")
        with pytest.raises(ValidationError):
            creds.oauth_token = "other"  # type: ignore[misc]
        with pytest.raises(ValidationError):
            ClaudeCredentials.model_validate({"oauth_token": "tok", "extra": "nope"})

    def test_codex_credentials_missing_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CodexCredentials.model_validate({})


class TestObservabilityExporter:
    def test_minimal_exporter(self) -> None:
        exporter = ObservabilityExporter.model_validate({"name": "otel"})
        assert exporter.name == "otel"
        assert exporter.config == {}

    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ObservabilityExporter.model_validate({"name": "otel", "endpoint": "x"})


class TestRunResult:
    def test_requires_result_and_session_log(self) -> None:
        with pytest.raises(ValidationError):
            AgentRunResult.model_validate({})

    def test_valid_agent_run_result(self) -> None:
        result = AgentRunResult.model_validate(
            {
                "result": {"success": True, "summary": "Fixed the test"},
                "output_artifacts": ["/tmp/output.txt"],
                "session_log": "session-log-contents",
            }
        )
        assert result.result == AgentRunOutcome(success=True, summary="Fixed the test")
        assert result.output_artifacts == (Path("/tmp/output.txt"),)
        assert result.session_log == "session-log-contents"
        assert result.observability is None

    def test_agent_run_result_is_frozen(self) -> None:
        result = AgentRunResult.model_validate(
            {
                "result": {"success": False, "summary": "failed"},
                "session_log": "log",
            }
        )
        with pytest.raises(ValidationError):
            result.session_log = "other"  # type: ignore[misc]

    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentRunResult.model_validate(
                {
                    "result": {"success": True, "summary": "ok"},
                    "session_log": "log",
                    "extra": "nope",
                }
            )


class TestRunEvents:
    def test_tool_start_event(self) -> None:
        event: AgentRunEvent = ToolStartEvent.model_validate(
            {"type": "tool_start", "tool_name": "bash", "tool_use_id": "t1"}
        )
        assert isinstance(event, ToolStartEvent)
        assert event.tool_name == "bash"

    def test_tool_end_event(self) -> None:
        event: AgentRunEvent = ToolEndEvent.model_validate(
            {
                "type": "tool_end",
                "tool_name": "bash",
                "tool_use_id": "t1",
                "success": True,
            }
        )
        assert isinstance(event, ToolEndEvent)
        assert event.success is True

    def test_token_usage_event(self) -> None:
        event: AgentRunEvent = TokenUsageEvent.model_validate(
            {
                "type": "token_usage",
                "input_tokens": 100,
                "output_tokens": 50,
            }
        )
        assert isinstance(event, TokenUsageEvent)
        assert event.input_tokens == 100

    def test_session_end_event(self) -> None:
        event: AgentRunEvent = SessionEndEvent.model_validate(
            {"type": "session_end", "success": True}
        )
        assert isinstance(event, SessionEndEvent)

    def test_discriminated_union_dispatches_on_type(self) -> None:
        envelope = AgentRunEventEnvelope.model_validate(
            {"event": {"type": "tool_start", "tool_name": "bash", "tool_use_id": "t1"}}
        )
        assert isinstance(envelope.event, ToolStartEvent)

        envelope2 = AgentRunEventEnvelope.model_validate(
            {"event": {"type": "session_end", "success": False}}
        )
        assert isinstance(envelope2.event, SessionEndEvent)

    def test_unknown_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentRunEventEnvelope.model_validate({"event": {"type": "bogus_event"}})

    def test_event_variants_are_frozen_and_forbid_extra(self) -> None:
        event = SessionEndEvent(type="session_end", success=True)
        with pytest.raises(ValidationError):
            event.success = False  # type: ignore[misc]
        with pytest.raises(ValidationError):
            SessionEndEvent.model_validate({"type": "session_end", "success": True, "extra": 1})
