#!/usr/bin/env python3
"""
Tests for the plugin-doctor plugin.

Covers:
- freshness.py pure functions: state I/O, cadence gating, semver
  comparison, and context-message formatting.
- session-start.py handler: end-to-end via subprocess with env-var
  path overrides, matching the run_handler() pattern in test_hooks.py.
"""

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
PLUGIN_DOCTOR = PROJECT_ROOT / "plugins" / "plugin-doctor"
PLUGIN_DOCTOR_LIB = PLUGIN_DOCTOR / "hooks" / "lib"
PLUGIN_DOCTOR_HANDLERS = PLUGIN_DOCTOR / "hooks" / "handlers"


def load_freshness():
    """Load freshness.py directly, bypassing package/import-path setup."""
    module_path = PLUGIN_DOCTOR_LIB / "freshness.py"
    spec = importlib.util.spec_from_file_location("plugin_doctor_freshness", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_session_start(env_overrides: dict) -> dict:
    """Run session-start.py as a subprocess with path overrides.

    PLUGIN_DOCTOR_SKIP_REFRESH defaults to "1" so tests never shell out
    to the real `claude` CLI or touch the network.
    """
    handler_path = PLUGIN_DOCTOR_HANDLERS / "session-start.py"
    env = dict(os.environ)
    env.update(env_overrides)
    env.setdefault("PLUGIN_DOCTOR_SKIP_REFRESH", "1")

    result = subprocess.run(
        [sys.executable, str(handler_path)],
        input=json.dumps({"session_id": "test"}).encode(),
        capture_output=True,
        env=env,
        timeout=5,
    )

    stdout = result.stdout.decode().strip()
    if not stdout:
        return {}
    return json.loads(stdout)


# ============================================================================
# Task 1: State I/O and cadence gating
# ============================================================================


class TestStateIO:
    def test_read_state_missing_file_returns_empty_dict(self, tmp_path):
        freshness = load_freshness()
        result = freshness.read_state(tmp_path / "does-not-exist" / "state.json")
        assert result == {}

    def test_read_state_malformed_json_returns_empty_dict(self, tmp_path):
        freshness = load_freshness()
        state_path = tmp_path / "state.json"
        state_path.write_text("{not valid json")
        assert freshness.read_state(state_path) == {}

    def test_write_state_then_read_state_roundtrips(self, tmp_path):
        freshness = load_freshness()
        state_path = tmp_path / "nested" / "state.json"
        freshness.write_state(state_path, {"last_checked_at": "2026-07-16T00:00:00+00:00"})
        assert freshness.read_state(state_path) == {
            "last_checked_at": "2026-07-16T00:00:00+00:00"
        }

    def test_read_state_non_dict_json_array_returns_empty_dict(self, tmp_path):
        freshness = load_freshness()
        state_path = tmp_path / "state.json"
        state_path.write_text("[1, 2, 3]")
        assert freshness.read_state(state_path) == {}

    def test_read_state_non_dict_json_null_returns_empty_dict(self, tmp_path):
        freshness = load_freshness()
        state_path = tmp_path / "state.json"
        state_path.write_text("null")
        assert freshness.read_state(state_path) == {}


class TestIsCheckDue:
    def test_missing_last_checked_at_is_due(self):
        freshness = load_freshness()
        now = datetime(2026, 7, 16, tzinfo=timezone.utc)
        assert freshness.is_check_due(None, now) is True

    def test_malformed_last_checked_at_is_due(self):
        freshness = load_freshness()
        now = datetime(2026, 7, 16, tzinfo=timezone.utc)
        assert freshness.is_check_due("not-a-date", now) is True

    def test_recent_check_is_not_due(self):
        freshness = load_freshness()
        now = datetime(2026, 7, 16, tzinfo=timezone.utc)
        last = (now - timedelta(days=3)).isoformat()
        assert freshness.is_check_due(last, now) is False

    def test_check_exactly_at_interval_is_due(self):
        freshness = load_freshness()
        now = datetime(2026, 7, 16, tzinfo=timezone.utc)
        last = (now - timedelta(days=7)).isoformat()
        assert freshness.is_check_due(last, now) is True

    def test_check_older_than_interval_is_due(self):
        freshness = load_freshness()
        now = datetime(2026, 7, 16, tzinfo=timezone.utc)
        last = (now - timedelta(days=10)).isoformat()
        assert freshness.is_check_due(last, now) is True

    def test_non_string_last_checked_at_int_is_due(self):
        freshness = load_freshness()
        now = datetime(2026, 7, 16, tzinfo=timezone.utc)
        assert freshness.is_check_due(12345, now) is True

    def test_non_string_last_checked_at_list_is_due(self):
        freshness = load_freshness()
        now = datetime(2026, 7, 16, tzinfo=timezone.utc)
        assert freshness.is_check_due([1, 2, 3], now) is True
