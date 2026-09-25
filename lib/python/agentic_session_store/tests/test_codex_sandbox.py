"""Sandbox mode validation and fail-closed probe record parsing."""

import json

import pytest

from agentic_session_store.codex_sandbox import (
    DEFAULT_STATUS_PATH,
    CodexSandboxMode,
    parse_sandbox_mode,
    read_status,
    resolve_sandbox_mode,
    status_path,
)


@pytest.mark.parametrize("value", [None, "", "  "])
def test_default_mode_is_workspace_write(value):
    assert parse_sandbox_mode(value) is CodexSandboxMode.WORKSPACE_WRITE


@pytest.mark.parametrize("mode", list(CodexSandboxMode))
def test_allowed_modes_round_trip(mode):
    assert parse_sandbox_mode(mode.value) is mode


@pytest.mark.parametrize("value", ["danger-full-access", "external-sandbox"])
def test_sandbox_disabling_modes_are_refused_by_name(value):
    with pytest.raises(ValueError, match="disables the sandbox"):
        parse_sandbox_mode(value)


@pytest.mark.parametrize("value", ["full-auto", "WORKSPACE-WRITE", "none"])
def test_unknown_modes_are_refused(value):
    with pytest.raises(ValueError, match="Unknown Codex sandbox mode"):
        parse_sandbox_mode(value)


def test_cli_value_wins_over_environment():
    environment = {"AGENTIC_DELEGATE_CODEX_SANDBOX": "read-only"}
    assert resolve_sandbox_mode(None, environment) is CodexSandboxMode.READ_ONLY
    assert (
        resolve_sandbox_mode("workspace-write", environment)
        is CodexSandboxMode.WORKSPACE_WRITE
    )


def test_status_path_default_and_override(tmp_path):
    assert status_path({}) == DEFAULT_STATUS_PATH
    override = tmp_path / "s.json"
    assert status_path({"AGENTIC_CODEX_SANDBOX_STATUS": str(override)}) == override


def test_available_record(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps({"schema_version": 1, "available": True, "detail": "ok"})
    )
    status = read_status(path)
    assert status.available
    assert status.detail == "ok"


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"[]",
        b"{",
        b'{"schema_version": 1}',
        b'{"schema_version": 1, "available": 1}',
        b'{"schema_version": 2, "available": true}',
        b"\xff\xfe",
        b" " * (64 * 1024 + 1),
    ],
)
def test_malformed_records_fail_closed(tmp_path, content):
    path = tmp_path / "s.json"
    path.write_bytes(content)
    assert not read_status(path).available


def test_missing_record_fails_closed(tmp_path):
    status = read_status(tmp_path / "absent.json")
    assert not status.available
    assert "no sandbox probe record" in status.detail
