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
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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


class _FixtureGitHubHandler(BaseHTTPRequestHandler):
    """Serves canned GitHub commits-API responses for a single test.

    Subclassed per-test via start_fixture_server() with a `responses`
    dict mapping the "sha" query param value (e.g. "sdlc/v1.5.0") to
    (status_code, json_body). A sha with no matching entry gets a 404,
    matching GitHub's real behavior for a nonexistent ref.
    """

    responses: dict = {}

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        sha = query.get("sha", [None])[0]
        if sha in self.responses:
            status, body = self.responses[sha]
        else:
            status, body = 404, {"message": "Not Found"}
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format, *args):
        pass  # silence default request logging to stderr


def start_fixture_server(responses: dict) -> tuple[str, HTTPServer]:
    """Start a background HTTP server for one test.

    Returns (base_url, server). Caller must call server.shutdown() (and
    server.server_close(), which shutdown() triggers via the thread
    target) when done -- a `try/finally` around the test body is the
    simplest way to guarantee that.
    """
    handler_class = type("_Handler", (_FixtureGitHubHandler,), {"responses": responses})
    server = HTTPServer(("127.0.0.1", 0), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_port}", server


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


# ============================================================================
# Task 2: Semver comparison and context formatting
# ============================================================================


class TestParseSemver:
    def test_parses_standard_version(self):
        freshness = load_freshness()
        assert freshness.parse_semver("1.4.0") == (1, 4, 0)

    def test_parses_version_with_prerelease_suffix(self):
        freshness = load_freshness()
        assert freshness.parse_semver("1.4.0-beta") == (1, 4, 0)

    def test_returns_none_for_non_semver_string(self):
        freshness = load_freshness()
        assert freshness.parse_semver("unknown") is None

    def test_returns_none_for_non_string_input(self):
        freshness = load_freshness()
        assert freshness.parse_semver(None) is None


class TestGetInstalledVersions:
    def test_missing_cache_root_returns_empty_dict(self, tmp_path):
        freshness = load_freshness()
        assert freshness.get_installed_versions(tmp_path / "nope") == {}

    def test_reads_single_version_per_plugin(self, tmp_path):
        freshness = load_freshness()
        (tmp_path / "sdlc" / "1.4.0").mkdir(parents=True)
        (tmp_path / "meta" / "1.3.0").mkdir(parents=True)
        assert freshness.get_installed_versions(tmp_path) == {
            "sdlc": "1.4.0",
            "meta": "1.3.0",
        }

    def test_picks_highest_version_when_multiple_present(self, tmp_path):
        freshness = load_freshness()
        (tmp_path / "sdlc" / "1.3.0").mkdir(parents=True)
        (tmp_path / "sdlc" / "1.4.0").mkdir(parents=True)
        assert freshness.get_installed_versions(tmp_path) == {"sdlc": "1.4.0"}

    def test_skips_non_semver_version_directories(self, tmp_path):
        freshness = load_freshness()
        (tmp_path / "sdlc" / "unknown").mkdir(parents=True)
        assert freshness.get_installed_versions(tmp_path) == {}

    def test_semver_ordering_1_10_0_beats_1_9_0(self, tmp_path):
        """Regression test for Finding 2: verify 1.10.0 > 1.9.0 by semver, not string.
        String comparison would incorrectly pick '1.9.0' (lexicographically), but
        tuple comparison (semver) correctly picks '1.10.0'."""
        freshness = load_freshness()
        (tmp_path / "sdlc" / "1.9.0").mkdir(parents=True)
        (tmp_path / "sdlc" / "1.10.0").mkdir(parents=True)
        assert freshness.get_installed_versions(tmp_path) == {"sdlc": "1.10.0"}


class TestGetCatalogVersions:
    def test_missing_marketplace_root_returns_empty_dict(self, tmp_path):
        freshness = load_freshness()
        assert freshness.get_catalog_versions(tmp_path / "nope") == {}

    def test_reads_version_from_plugin_json(self, tmp_path):
        freshness = load_freshness()
        manifest_dir = tmp_path / "sdlc" / ".claude-plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "sdlc", "version": "1.5.0"})
        )
        assert freshness.get_catalog_versions(tmp_path) == {"sdlc": "1.5.0"}

    def test_skips_plugin_missing_manifest(self, tmp_path):
        freshness = load_freshness()
        (tmp_path / "sdlc").mkdir(parents=True)
        assert freshness.get_catalog_versions(tmp_path) == {}

    def test_skips_malformed_manifest(self, tmp_path):
        freshness = load_freshness()
        manifest_dir = tmp_path / "sdlc" / ".claude-plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text("{not valid json")
        assert freshness.get_catalog_versions(tmp_path) == {}

    def test_skips_valid_json_array_manifest_but_reads_other_plugins(self, tmp_path):
        """Regression test for Finding 1: non-dict valid JSON should not crash
        or blank out the entire catalog. A structurally valid but wrong-shape
        manifest (e.g., []) must not raise AttributeError when calling .get()."""
        freshness = load_freshness()
        # Create first plugin with valid JSON array (wrong shape, should be skipped)
        bad_manifest_dir = tmp_path / "bad-plugin" / ".claude-plugin"
        bad_manifest_dir.mkdir(parents=True)
        (bad_manifest_dir / "plugin.json").write_text("[]")
        # Create second plugin with valid manifest
        good_manifest_dir = tmp_path / "good-plugin" / ".claude-plugin"
        good_manifest_dir.mkdir(parents=True)
        (good_manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "good-plugin", "version": "1.5.0"})
        )
        # Should return only the good plugin and NOT raise
        assert freshness.get_catalog_versions(tmp_path) == {"good-plugin": "1.5.0"}

    def test_skips_valid_json_null_manifest_but_reads_other_plugins(self, tmp_path):
        """Regression test for Finding 1 with null: non-dict valid JSON should not
        crash. A manifest containing just `null` must not raise AttributeError."""
        freshness = load_freshness()
        # Create first plugin with valid JSON null (wrong shape)
        bad_manifest_dir = tmp_path / "null-plugin" / ".claude-plugin"
        bad_manifest_dir.mkdir(parents=True)
        (bad_manifest_dir / "plugin.json").write_text("null")
        # Create second plugin with valid manifest
        good_manifest_dir = tmp_path / "good-plugin" / ".claude-plugin"
        good_manifest_dir.mkdir(parents=True)
        (good_manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "good-plugin", "version": "2.0.0"})
        )
        # Should return only the good plugin and NOT raise
        assert freshness.get_catalog_versions(tmp_path) == {"good-plugin": "2.0.0"}


class TestDiffOutdated:
    def test_flags_plugin_behind_catalog(self):
        freshness = load_freshness()
        outdated = freshness.diff_outdated({"sdlc": "1.4.0"}, {"sdlc": "1.5.0"})
        assert outdated == {"sdlc": ("1.4.0", "1.5.0")}

    def test_up_to_date_plugin_not_flagged(self):
        freshness = load_freshness()
        assert freshness.diff_outdated({"sdlc": "1.4.0"}, {"sdlc": "1.4.0"}) == {}

    def test_plugin_missing_from_catalog_not_flagged(self):
        freshness = load_freshness()
        assert freshness.diff_outdated({"local-only": "0.1.0"}, {}) == {}

    def test_unparsable_versions_not_flagged(self):
        freshness = load_freshness()
        assert freshness.diff_outdated({"sdlc": "unknown"}, {"sdlc": "1.5.0"}) == {}

    def test_semver_ordering_1_9_0_lt_1_10_0_flagged_outdated(self):
        """Regression test for Finding 2: 1.9.0 should be flagged as outdated
        when catalog is 1.10.0. Tuple comparison (semver) correctly handles this;
        string comparison would incorrectly say 1.9.0 >= 1.10.0 lexicographically."""
        freshness = load_freshness()
        outdated = freshness.diff_outdated({"sdlc": "1.9.0"}, {"sdlc": "1.10.0"})
        assert outdated == {"sdlc": ("1.9.0", "1.10.0")}

    def test_semver_ordering_1_10_0_not_outdated_vs_1_9_0(self):
        """Regression test for Finding 2: 1.10.0 should NOT be flagged as outdated
        when catalog is 1.9.0. Verifies the comparison direction is correct."""
        freshness = load_freshness()
        outdated = freshness.diff_outdated({"sdlc": "1.10.0"}, {"sdlc": "1.9.0"})
        assert outdated == {}


class TestFormatContext:
    def test_lists_each_outdated_plugin_with_versions(self):
        freshness = load_freshness()
        message = freshness.format_context({"sdlc": ("1.4.0", "1.5.0")})
        assert "sdlc: 1.4.0 -> 1.5.0" in message

    def test_instructs_claude_to_ask_before_updating(self):
        freshness = load_freshness()
        message = freshness.format_context({"sdlc": ("1.4.0", "1.5.0")})
        assert "ask" in message.lower()
        assert (
            "never run a plugin update without the user explicitly agreeing"
            in message.lower()
        )


# ============================================================================
# Release-age gate: is_release_old_enough (pure function)
# ============================================================================


class TestIsReleaseOldEnough:
    def test_none_input_is_not_old_enough(self):
        freshness = load_freshness()
        now = datetime(2026, 7, 17, tzinfo=timezone.utc)
        assert freshness.is_release_old_enough(None, now) is False

    def test_unparseable_date_is_not_old_enough(self):
        freshness = load_freshness()
        now = datetime(2026, 7, 17, tzinfo=timezone.utc)
        assert freshness.is_release_old_enough("not-a-date", now) is False

    def test_recent_commit_is_not_old_enough(self):
        freshness = load_freshness()
        now = datetime(2026, 7, 17, tzinfo=timezone.utc)
        commit_date = (now - timedelta(hours=10)).isoformat().replace("+00:00", "Z")
        assert freshness.is_release_old_enough(commit_date, now) is False

    def test_commit_exactly_48_hours_old_is_old_enough(self):
        freshness = load_freshness()
        now = datetime(2026, 7, 17, tzinfo=timezone.utc)
        commit_date = (now - timedelta(hours=48)).isoformat().replace("+00:00", "Z")
        assert freshness.is_release_old_enough(commit_date, now) is True

    def test_commit_older_than_48_hours_is_old_enough(self):
        freshness = load_freshness()
        now = datetime(2026, 7, 17, tzinfo=timezone.utc)
        commit_date = (now - timedelta(hours=72)).isoformat().replace("+00:00", "Z")
        assert freshness.is_release_old_enough(commit_date, now) is True

    def test_custom_min_age_hours(self):
        freshness = load_freshness()
        now = datetime(2026, 7, 17, tzinfo=timezone.utc)
        commit_date = (now - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        assert freshness.is_release_old_enough(commit_date, now, min_age_hours=1) is True


# ============================================================================
# Task 3: session-start.py handler (end-to-end via subprocess)
# ============================================================================


class TestSessionStartHandler:
    def test_no_context_when_all_plugins_up_to_date(self, tmp_path):
        cache_root = tmp_path / "cache"
        (cache_root / "sdlc" / "1.4.0").mkdir(parents=True)
        marketplace_root = tmp_path / "marketplace"
        manifest_dir = marketplace_root / "sdlc" / ".claude-plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text(json.dumps({"version": "1.4.0"}))
        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps({"last_checked_at": datetime.now(timezone.utc).isoformat()})
        )

        result = run_session_start(
            {
                "PLUGIN_DOCTOR_CACHE_DIR": str(cache_root),
                "PLUGIN_DOCTOR_MARKETPLACE_DIR": str(marketplace_root),
                "PLUGIN_DOCTOR_STATE_PATH": str(state_path),
            }
        )
        assert result == {}

    def test_outdated_plugin_old_enough_release_is_surfaced(self, tmp_path):
        cache_root = tmp_path / "cache"
        (cache_root / "sdlc" / "1.4.0").mkdir(parents=True)
        marketplace_root = tmp_path / "marketplace"
        manifest_dir = marketplace_root / "sdlc" / ".claude-plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text(json.dumps({"version": "1.5.0"}))
        state_path = tmp_path / "state.json"  # missing -> due

        old_commit_date = (
            (datetime.now(timezone.utc) - timedelta(hours=72))
            .isoformat()
            .replace("+00:00", "Z")
        )
        base_url, server = start_fixture_server(
            {"sdlc/v1.5.0": (200, [{"commit": {"committer": {"date": old_commit_date}}}])}
        )
        try:
            result = run_session_start(
                {
                    "PLUGIN_DOCTOR_CACHE_DIR": str(cache_root),
                    "PLUGIN_DOCTOR_MARKETPLACE_DIR": str(marketplace_root),
                    "PLUGIN_DOCTOR_STATE_PATH": str(state_path),
                    "PLUGIN_DOCTOR_GITHUB_API_BASE": base_url,
                }
            )
        finally:
            server.shutdown()

        assert result["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert (
            "sdlc: 1.4.0 -> 1.5.0" in result["hookSpecificOutput"]["additionalContext"]
        )
        written = json.loads(state_path.read_text())
        assert written["release_ages"]["sdlc"] == {"version": "1.5.0", "old_enough": True}

    def test_outdated_plugin_too_recent_release_is_suppressed(self, tmp_path):
        cache_root = tmp_path / "cache"
        (cache_root / "sdlc" / "1.4.0").mkdir(parents=True)
        marketplace_root = tmp_path / "marketplace"
        manifest_dir = marketplace_root / "sdlc" / ".claude-plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text(json.dumps({"version": "1.5.0"}))
        state_path = tmp_path / "state.json"

        recent_commit_date = (
            (datetime.now(timezone.utc) - timedelta(hours=5))
            .isoformat()
            .replace("+00:00", "Z")
        )
        base_url, server = start_fixture_server(
            {
                "sdlc/v1.5.0": (
                    200,
                    [{"commit": {"committer": {"date": recent_commit_date}}}],
                )
            }
        )
        try:
            result = run_session_start(
                {
                    "PLUGIN_DOCTOR_CACHE_DIR": str(cache_root),
                    "PLUGIN_DOCTOR_MARKETPLACE_DIR": str(marketplace_root),
                    "PLUGIN_DOCTOR_STATE_PATH": str(state_path),
                    "PLUGIN_DOCTOR_GITHUB_API_BASE": base_url,
                }
            )
        finally:
            server.shutdown()

        assert result == {}
        written = json.loads(state_path.read_text())
        assert written["release_ages"]["sdlc"] == {"version": "1.5.0", "old_enough": False}

    def test_outdated_plugin_untagged_version_is_suppressed(self, tmp_path):
        cache_root = tmp_path / "cache"
        (cache_root / "sdlc" / "1.4.0").mkdir(parents=True)
        marketplace_root = tmp_path / "marketplace"
        manifest_dir = marketplace_root / "sdlc" / ".claude-plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text(json.dumps({"version": "1.5.0"}))
        state_path = tmp_path / "state.json"

        base_url, server = start_fixture_server({})  # no matching sha -> 404
        try:
            result = run_session_start(
                {
                    "PLUGIN_DOCTOR_CACHE_DIR": str(cache_root),
                    "PLUGIN_DOCTOR_MARKETPLACE_DIR": str(marketplace_root),
                    "PLUGIN_DOCTOR_STATE_PATH": str(state_path),
                    "PLUGIN_DOCTOR_GITHUB_API_BASE": base_url,
                }
            )
        finally:
            server.shutdown()

        assert result == {}
        written = json.loads(state_path.read_text())
        assert written["release_ages"]["sdlc"]["old_enough"] is False

    def test_outdated_plugin_unreachable_github_is_suppressed(self, tmp_path):
        cache_root = tmp_path / "cache"
        (cache_root / "sdlc" / "1.4.0").mkdir(parents=True)
        marketplace_root = tmp_path / "marketplace"
        manifest_dir = marketplace_root / "sdlc" / ".claude-plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text(json.dumps({"version": "1.5.0"}))
        state_path = tmp_path / "state.json"

        closed_server = HTTPServer(("127.0.0.1", 0), _FixtureGitHubHandler)
        unreachable_url = f"http://127.0.0.1:{closed_server.server_port}"
        closed_server.server_close()  # bound and closed -- nothing is listening

        result = run_session_start(
            {
                "PLUGIN_DOCTOR_CACHE_DIR": str(cache_root),
                "PLUGIN_DOCTOR_MARKETPLACE_DIR": str(marketplace_root),
                "PLUGIN_DOCTOR_STATE_PATH": str(state_path),
                "PLUGIN_DOCTOR_GITHUB_API_BASE": unreachable_url,
            }
        )
        assert result == {}

    def test_stale_release_ages_entry_for_old_version_is_not_reused(self, tmp_path):
        cache_root = tmp_path / "cache"
        (cache_root / "sdlc" / "1.4.0").mkdir(parents=True)
        marketplace_root = tmp_path / "marketplace"
        manifest_dir = marketplace_root / "sdlc" / ".claude-plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text(json.dumps({"version": "1.6.0"}))
        state_path = tmp_path / "state.json"
        # Recent last_checked_at -> NOT due, so no fresh age-check runs this
        # session. The cached entry is for 1.5.0, but the catalog now shows
        # 1.6.0 -- a version the cache never verified.
        state_path.write_text(
            json.dumps(
                {
                    "last_checked_at": datetime.now(timezone.utc).isoformat(),
                    "release_ages": {"sdlc": {"version": "1.5.0", "old_enough": True}},
                }
            )
        )

        result = run_session_start(
            {
                "PLUGIN_DOCTOR_CACHE_DIR": str(cache_root),
                "PLUGIN_DOCTOR_MARKETPLACE_DIR": str(marketplace_root),
                "PLUGIN_DOCTOR_STATE_PATH": str(state_path),
            }
        )
        assert result == {}

    def test_non_due_session_reuses_cached_release_ages_without_network_call(
        self, tmp_path
    ):
        cache_root = tmp_path / "cache"
        (cache_root / "sdlc" / "1.4.0").mkdir(parents=True)
        marketplace_root = tmp_path / "marketplace"
        manifest_dir = marketplace_root / "sdlc" / ".claude-plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text(json.dumps({"version": "1.5.0"}))
        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps(
                {
                    "last_checked_at": datetime.now(timezone.utc).isoformat(),  # NOT due
                    "release_ages": {"sdlc": {"version": "1.5.0", "old_enough": True}},
                }
            )
        )

        # Point at an unreachable GitHub API base. If the handler tried to
        # hit the network here, the fetch would fail and (per the fail-safe
        # rule) old_enough would come back False -- suppressing the result.
        # Asserting the cached True value is still honored proves the
        # handler never attempted a network call on this non-due session.
        closed_server = HTTPServer(("127.0.0.1", 0), _FixtureGitHubHandler)
        unreachable_url = f"http://127.0.0.1:{closed_server.server_port}"
        closed_server.server_close()

        result = run_session_start(
            {
                "PLUGIN_DOCTOR_CACHE_DIR": str(cache_root),
                "PLUGIN_DOCTOR_MARKETPLACE_DIR": str(marketplace_root),
                "PLUGIN_DOCTOR_STATE_PATH": str(state_path),
                "PLUGIN_DOCTOR_GITHUB_API_BASE": unreachable_url,
            }
        )
        assert result["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert (
            "sdlc: 1.4.0 -> 1.5.0" in result["hookSpecificOutput"]["additionalContext"]
        )

    def test_due_session_recomputes_release_ages_dropping_stale_entries(
        self, tmp_path
    ):
        # sdlc is now up to date, but state still has a stale release_ages
        # entry for it from a previous (now-resolved) outdated check.
        cache_root = tmp_path / "cache"
        (cache_root / "sdlc" / "1.5.0").mkdir(parents=True)
        marketplace_root = tmp_path / "marketplace"
        manifest_dir = marketplace_root / "sdlc" / ".claude-plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text(json.dumps({"version": "1.5.0"}))
        state_path = tmp_path / "state.json"
        old_timestamp = (
            datetime.now(timezone.utc) - timedelta(days=10)
        ).isoformat()  # due
        state_path.write_text(
            json.dumps(
                {
                    "last_checked_at": old_timestamp,
                    "release_ages": {"sdlc": {"version": "1.4.0", "old_enough": True}},
                }
            )
        )

        result = run_session_start(
            {
                "PLUGIN_DOCTOR_CACHE_DIR": str(cache_root),
                "PLUGIN_DOCTOR_MARKETPLACE_DIR": str(marketplace_root),
                "PLUGIN_DOCTOR_STATE_PATH": str(state_path),
            }
        )
        assert result == {}
        written = json.loads(state_path.read_text())
        assert written["release_ages"] == {}

    def test_writes_state_when_check_is_due(self, tmp_path):
        cache_root = tmp_path / "cache"
        cache_root.mkdir()
        marketplace_root = tmp_path / "marketplace"
        marketplace_root.mkdir()
        state_path = tmp_path / "state.json"  # does not exist yet -> due

        run_session_start(
            {
                "PLUGIN_DOCTOR_CACHE_DIR": str(cache_root),
                "PLUGIN_DOCTOR_MARKETPLACE_DIR": str(marketplace_root),
                "PLUGIN_DOCTOR_STATE_PATH": str(state_path),
            }
        )
        assert state_path.exists()
        assert "last_checked_at" in json.loads(state_path.read_text())

    def test_does_not_touch_state_when_check_not_due(self, tmp_path):
        cache_root = tmp_path / "cache"
        cache_root.mkdir()
        marketplace_root = tmp_path / "marketplace"
        marketplace_root.mkdir()
        state_path = tmp_path / "state.json"
        original = {"last_checked_at": datetime.now(timezone.utc).isoformat()}
        state_path.write_text(json.dumps(original))

        run_session_start(
            {
                "PLUGIN_DOCTOR_CACHE_DIR": str(cache_root),
                "PLUGIN_DOCTOR_MARKETPLACE_DIR": str(marketplace_root),
                "PLUGIN_DOCTOR_STATE_PATH": str(state_path),
            }
        )
        assert json.loads(state_path.read_text()) == original

    def test_missing_cache_and_marketplace_dirs_no_crash(self, tmp_path):
        result = run_session_start(
            {
                "PLUGIN_DOCTOR_CACHE_DIR": str(tmp_path / "no-cache"),
                "PLUGIN_DOCTOR_MARKETPLACE_DIR": str(tmp_path / "no-marketplace"),
                "PLUGIN_DOCTOR_STATE_PATH": str(tmp_path / "state.json"),
            }
        )
        assert result == {}

    def test_refresh_subprocess_is_actually_invoked_when_due(self, tmp_path):
        """Prove _refresh_marketplace() really calls subprocess.run(["claude", ...])
        by putting a fake `claude` executable on PATH and checking it ran."""
        fake_bin_dir = tmp_path / "fake-bin"
        fake_bin_dir.mkdir()
        marker_path = tmp_path / "claude-was-invoked.marker"
        fake_claude = fake_bin_dir / "claude"
        fake_claude.write_text(f"#!/bin/sh\ntouch {marker_path}\nexit 0\n")
        fake_claude.chmod(0o755)

        cache_root = tmp_path / "cache"
        cache_root.mkdir()
        marketplace_root = tmp_path / "marketplace"
        marketplace_root.mkdir()
        state_path = tmp_path / "state.json"
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        state_path.write_text(json.dumps({"last_checked_at": old_timestamp}))

        handler_path = PLUGIN_DOCTOR_HANDLERS / "session-start.py"
        env = dict(os.environ)
        env["PATH"] = f"{fake_bin_dir}:{env['PATH']}"
        env["PLUGIN_DOCTOR_CACHE_DIR"] = str(cache_root)
        env["PLUGIN_DOCTOR_MARKETPLACE_DIR"] = str(marketplace_root)
        env["PLUGIN_DOCTOR_STATE_PATH"] = str(state_path)
        env["PLUGIN_DOCTOR_SKIP_REFRESH"] = "0"

        result = subprocess.run(
            [sys.executable, str(handler_path)],
            input=json.dumps({"session_id": "test"}).encode(),
            capture_output=True,
            env=env,
            timeout=5,
        )

        assert result.returncode == 0
        assert marker_path.exists()

    def test_missing_claude_executable_fails_open(self, tmp_path):
        """When `claude` isn't on PATH, subprocess.run raises FileNotFoundError
        (a subclass of OSError); _refresh_marketplace must swallow it and the
        handler must still complete without crashing."""
        empty_bin_dir = tmp_path / "empty-bin"
        empty_bin_dir.mkdir()

        cache_root = tmp_path / "cache"
        cache_root.mkdir()
        marketplace_root = tmp_path / "marketplace"
        marketplace_root.mkdir()
        state_path = tmp_path / "state.json"
        # No state file -> is_check_due() returns True.

        handler_path = PLUGIN_DOCTOR_HANDLERS / "session-start.py"
        env = dict(os.environ)
        env["PATH"] = str(empty_bin_dir)
        env["PLUGIN_DOCTOR_CACHE_DIR"] = str(cache_root)
        env["PLUGIN_DOCTOR_MARKETPLACE_DIR"] = str(marketplace_root)
        env["PLUGIN_DOCTOR_STATE_PATH"] = str(state_path)
        env["PLUGIN_DOCTOR_SKIP_REFRESH"] = "0"

        result = subprocess.run(
            [sys.executable, str(handler_path)],
            input=json.dumps({"session_id": "test"}).encode(),
            capture_output=True,
            env=env,
            timeout=5,
        )

        assert result.returncode == 0
        stdout = result.stdout.decode().strip()
        if stdout:
            parsed = json.loads(stdout)
            assert isinstance(parsed, dict)
        # State should still have been written despite the refresh failure.
        assert state_path.exists()
        assert "last_checked_at" in json.loads(state_path.read_text())
