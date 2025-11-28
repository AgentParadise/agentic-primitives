"""Pytest configuration and shared fixtures for analytics tests"""

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Get path to test fixtures directory"""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def claude_hooks_dir(fixtures_dir: Path) -> Path:
    """Get path to Claude hook event fixtures"""
    return fixtures_dir / "claude_hooks"


@pytest.fixture
def normalized_events_dir(fixtures_dir: Path) -> Path:
    """Get path to normalized event fixtures"""
    return fixtures_dir / "normalized_events"


def load_json_fixture(path: Path) -> dict[str, Any]:
    """Load a JSON fixture file"""
    with open(path) as f:
        return json.load(f)  # type: ignore[no-any-return]


@pytest.fixture
def claude_pre_tool_use_fixture(claude_hooks_dir: Path) -> dict[str, Any]:
    """Load Claude PreToolUse event fixture"""
    return load_json_fixture(claude_hooks_dir / "pre_tool_use.json")


@pytest.fixture
def claude_post_tool_use_fixture(claude_hooks_dir: Path) -> dict[str, Any]:
    """Load Claude PostToolUse event fixture"""
    return load_json_fixture(claude_hooks_dir / "post_tool_use.json")


@pytest.fixture
def claude_user_prompt_submit_fixture(claude_hooks_dir: Path) -> dict[str, Any]:
    """Load Claude UserPromptSubmit event fixture"""
    return load_json_fixture(claude_hooks_dir / "user_prompt_submit.json")


@pytest.fixture
def claude_session_start_fixture(claude_hooks_dir: Path) -> dict[str, Any]:
    """Load Claude SessionStart event fixture"""
    return load_json_fixture(claude_hooks_dir / "session_start.json")


@pytest.fixture
def claude_session_end_fixture(claude_hooks_dir: Path) -> dict[str, Any]:
    """Load Claude SessionEnd event fixture"""
    return load_json_fixture(claude_hooks_dir / "session_end.json")


@pytest.fixture
def normalized_tool_execution_started(normalized_events_dir: Path) -> dict[str, Any]:
    """Load normalized tool_execution_started event fixture"""
    return load_json_fixture(normalized_events_dir / "tool_execution_started.json")


@pytest.fixture
def normalized_session_started(normalized_events_dir: Path) -> dict[str, Any]:
    """Load normalized session_started event fixture"""
    return load_json_fixture(normalized_events_dir / "session_started.json")
