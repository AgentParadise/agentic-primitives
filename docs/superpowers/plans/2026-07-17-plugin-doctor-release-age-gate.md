# plugin-doctor Release-Age Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 48-hour-minimum-release-age gate to `plugin-doctor`, verified directly against GitHub's per-plugin release tags, so a version is never surfaced to the user the moment it lands — closing the supply-chain gap in the original design (requested change on PR #267).

**Architecture:** A new pure function `is_release_old_enough` in `freshness.py` does the age comparison. A new network function `_fetch_release_commit_date` in `session-start.py` resolves a plugin's release tag to its commit date via a single unauthenticated GitHub REST API call (stdlib `urllib.request` only), following the same fail-open pattern as the existing `_refresh_marketplace`. Both are wired into `main()`: the age-check only runs inside the existing weekly `is_check_due` block, only for plugins already found outdated that session, and its results are cached in `state.json` under a new `release_ages` key so non-due sessions never hit the network.

**Tech Stack:** Python 3.11+ stdlib only (`urllib.request`, `http.server` for test fixtures). No new dependencies.

## Global Constraints

- Minimum release age: 48 hours, exact GitHub endpoint: `GET {api_base}/repos/AgentParadise/agentic-primitives/commits?sha=<plugin>/v<version>&per_page=1`, commit date at `response[0].commit.committer.date`.
- The age-check network call fires **only** inside the existing weekly `is_check_due` gate (`CHECK_INTERVAL_DAYS = 7`), and only for plugins `diff_outdated` already found outdated that session. It must never fire on a non-due session.
- Any failure resolving the age (network error, timeout, non-2xx response, malformed JSON, unexpected shape, or a `None`/unparseable commit date) is treated identically to "not old enough" — fail-safe suppression, never fail-open-to-showing. This is the opposite fail direction from the rest of the plugin's error handling (which fails open to *not blocking*, not to *showing unverified info*) — be precise about this distinction.
- No new external dependency: the fetch uses stdlib `urllib.request` only, ~10s timeout, matching the existing `subprocess.run(..., timeout=10)` pattern already used for `_refresh_marketplace`.
- The GitHub API base URL is overridable via `PLUGIN_DOCTOR_GITHUB_API_BASE` (default `https://api.github.com`), for tests only — production code never needs to set it.
- `release_ages` in `state.json` is recomputed from scratch on every due session (not merged with the prior contents) — a plugin no longer outdated must drop out of the cache, not linger.
- A cached `release_ages` entry only counts as "verified" if its `version` field matches the *current* catalog version for that plugin; a mismatch (catalog bumped again since the last weekly check) is treated as unverified.
- `write_state` must still be called unconditionally whenever `is_check_due` is true, regardless of whether the marketplace refresh or any age-check succeeded — this existing constraint from the original design is unchanged.
- Tests follow this repo's "real behavior, not mocks" convention: the GitHub fetch is tested against a real local `http.server.HTTPServer` on an ephemeral port, not `unittest.mock`.

---

### Task 1: `is_release_old_enough` pure function

**Files:**
- Modify: `plugins/plugin-doctor/hooks/lib/freshness.py`
- Modify: `tests/unit/claude/hooks/test_plugin_doctor.py`

**Interfaces:**
- Produces: `freshness.is_release_old_enough(commit_date_iso: str | None, now: datetime, min_age_hours: int = 48) -> bool`. Task 2's handler calls this exact signature.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/claude/hooks/test_plugin_doctor.py`, after the existing `TestFormatContext` class (before `class TestSessionStartHandler:`):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/neural/Code/AgentParadise/agentic-primitives/.worktrees/plugin-doctor && uv run pytest tests/unit/claude/hooks/test_plugin_doctor.py -v -k TestIsReleaseOldEnough`
Expected: FAIL — `AttributeError: module 'plugin_doctor_freshness' has no attribute 'is_release_old_enough'`.

- [ ] **Step 3: Write the minimal implementation**

Append to `plugins/plugin-doctor/hooks/lib/freshness.py` (at the end of the file, after `format_context`):

```python
def is_release_old_enough(
    commit_date_iso: str | None, now: datetime, min_age_hours: int = 48
) -> bool:
    """True if commit_date_iso represents a timestamp at least
    min_age_hours before now.

    Returns False (fail-safe) if commit_date_iso is None or unparseable.
    This backs a supply-chain-safety gate: an unknown release age must
    never be treated as "old enough to recommend."
    """
    if not commit_date_iso:
        return False
    try:
        commit_date = datetime.fromisoformat(commit_date_iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    if commit_date.tzinfo is None:
        commit_date = commit_date.replace(tzinfo=timezone.utc)
    return now - commit_date >= timedelta(hours=min_age_hours)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/neural/Code/AgentParadise/agentic-primitives/.worktrees/plugin-doctor && uv run pytest tests/unit/claude/hooks/test_plugin_doctor.py -v -k TestIsReleaseOldEnough`
Expected: PASS — 6 tests.

Then run the full file to confirm nothing else broke:

Run: `uv run pytest tests/unit/claude/hooks/test_plugin_doctor.py -v`
Expected: PASS — all previously-passing tests still pass, plus these 6 new ones.

- [ ] **Step 5: Commit**

```bash
cd /Users/neural/Code/AgentParadise/agentic-primitives/.worktrees/plugin-doctor
git add plugins/plugin-doctor/hooks/lib/freshness.py tests/unit/claude/hooks/test_plugin_doctor.py
git commit -m "feat(plugin-doctor): add is_release_old_enough pure function"
```

---

### Task 2: GitHub release-age fetch, `main()` wiring, and end-to-end tests

**Files:**
- Modify: `plugins/plugin-doctor/hooks/handlers/session-start.py`
- Modify: `tests/unit/claude/hooks/test_plugin_doctor.py`

**Interfaces:**
- Consumes: `freshness.is_release_old_enough(commit_date_iso, now, min_age_hours)` from Task 1; `freshness.read_state`, `freshness.write_state`, `freshness.is_check_due`, `freshness.get_installed_versions`, `freshness.get_catalog_versions`, `freshness.diff_outdated`, `freshness.format_context` (all pre-existing, unchanged signatures).
- Produces: the final `main()` behavior described in this task — no other task consumes this directly, it's the last code task in this plan.

**Important — one pre-existing test will break and must be replaced, not just left failing:** `test_emits_context_when_plugin_outdated` (in `TestSessionStartHandler`) currently sets a *recent* `last_checked_at` (not due) and asserts immediate emission with no age verification at all — that assumption is exactly what this task removes. Delete that test and replace it with the new due/verified-emission test below (`test_outdated_plugin_old_enough_release_is_surfaced`), which covers the same "emits when outdated" behavior correctly under the new gate. Every other existing test in `TestSessionStartHandler` uses either an up-to-date cache or an empty cache (no outdated plugins), so the age-gate logic doesn't affect them — leave those as-is.

- [ ] **Step 1: Write the failing tests**

First, add the HTTP fixture server helper near the top of `tests/unit/claude/hooks/test_plugin_doctor.py`, right after the existing `run_session_start` function definition:

```python
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


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
```

Then, in `TestSessionStartHandler` (the existing class — do not create a new class), first **delete** `test_emits_context_when_plugin_outdated` entirely, then **add** these tests (place them after the existing `test_no_context_when_all_plugins_up_to_date`):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/neural/Code/AgentParadise/agentic-primitives/.worktrees/plugin-doctor && uv run pytest tests/unit/claude/hooks/test_plugin_doctor.py -v -k TestSessionStartHandler`
Expected: FAIL — the new tests fail because `session-start.py` doesn't yet read `PLUGIN_DOCTOR_GITHUB_API_BASE`, doesn't yet call any GitHub fetch, and doesn't yet write a `release_ages` key to state, so the assertions on `written["release_ages"]` raise `KeyError`, and the "surfaced" tests get `result == {}` instead of the expected `additionalContext` (since nothing currently gates or checks age, but nothing currently *adds* a `release_ages` cache either, so state won't contain the key the tests check).

- [ ] **Step 3: Write the minimal implementation**

Replace the full contents of `plugins/plugin-doctor/hooks/handlers/session-start.py` with:

```python
#!/usr/bin/env python3
"""
SessionStart Handler - Warns when installed agentic-primitives plugins
are outdated AND their newer version has been released on GitHub for
at least MIN_RELEASE_AGE_HOURS.

Checks at most once every CHECK_INTERVAL_DAYS (state persisted in
~/.claude/plugin-doctor/state.json, or PLUGIN_DOCTOR_STATE_PATH override).
Never updates plugins itself -- only informs Claude via additionalContext,
which is instructed to ask the user before running any update.
"""

import importlib.util
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CHECK_INTERVAL_DAYS = 7
MARKETPLACE_NAME = "agentic-primitives"
GITHUB_OWNER = "AgentParadise"
GITHUB_REPO = "agentic-primitives"
MIN_RELEASE_AGE_HOURS = 48


def _load_freshness():
    module_path = Path(__file__).parent.parent / "lib" / "freshness.py"
    spec = importlib.util.spec_from_file_location(
        "plugin_doctor_freshness", module_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


freshness = _load_freshness()


def _cache_root() -> Path:
    override = os.environ.get("PLUGIN_DOCTOR_CACHE_DIR")
    if override:
        return Path(override)
    return Path.home() / ".claude" / "plugins" / "cache" / MARKETPLACE_NAME


def _marketplace_plugins_root() -> Path:
    override = os.environ.get("PLUGIN_DOCTOR_MARKETPLACE_DIR")
    if override:
        return Path(override)
    return (
        Path.home()
        / ".claude"
        / "plugins"
        / "marketplaces"
        / MARKETPLACE_NAME
        / "plugins"
    )


def _state_path() -> Path:
    override = os.environ.get("PLUGIN_DOCTOR_STATE_PATH")
    if override:
        return Path(override)
    return Path.home() / ".claude" / "plugin-doctor" / "state.json"


def _github_api_base() -> str:
    return os.environ.get("PLUGIN_DOCTOR_GITHUB_API_BASE", "https://api.github.com")


def _refresh_marketplace() -> None:
    if os.environ.get("PLUGIN_DOCTOR_SKIP_REFRESH") == "1":
        return
    try:
        subprocess.run(
            ["claude", "plugin", "marketplace", "update", MARKETPLACE_NAME],
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _fetch_release_commit_date(plugin: str, version: str) -> str | None:
    """Resolve the <plugin>/v<version> release tag to its commit date via
    the GitHub commits API. Returns None on any failure -- network error,
    non-2xx response (including 404 for an untagged version), or an
    unexpected response shape."""
    url = (
        f"{_github_api_base()}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/commits"
        f"?sha={plugin}/v{version}&per_page=1"
    )
    try:
        req = urllib.request.Request(
            url, headers={"Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return data[0]["commit"]["committer"]["date"]
    except Exception:
        return None


def main() -> None:
    try:
        if not sys.stdin.isatty():
            sys.stdin.read()  # drain stdin so Claude Code doesn't see a hang

        state_path = _state_path()
        state = freshness.read_state(state_path)
        now = datetime.now(timezone.utc)
        due = freshness.is_check_due(
            state.get("last_checked_at"), now, CHECK_INTERVAL_DAYS
        )

        if due:
            _refresh_marketplace()

        installed = freshness.get_installed_versions(_cache_root())
        catalog = freshness.get_catalog_versions(_marketplace_plugins_root())
        outdated = freshness.diff_outdated(installed, catalog)

        release_ages = state.get("release_ages", {})
        if not isinstance(release_ages, dict):
            release_ages = {}

        if due:
            release_ages = {}
            for name, (_installed_version, catalog_version) in outdated.items():
                commit_date = _fetch_release_commit_date(name, catalog_version)
                old_enough = freshness.is_release_old_enough(
                    commit_date, now, MIN_RELEASE_AGE_HOURS
                )
                release_ages[name] = {
                    "version": catalog_version,
                    "old_enough": old_enough,
                }
            freshness.write_state(
                state_path,
                {"last_checked_at": now.isoformat(), "release_ages": release_ages},
            )

        verified_outdated = {
            name: versions
            for name, versions in outdated.items()
            if isinstance(release_ages.get(name), dict)
            and release_ages[name].get("version") == versions[1]
            and release_ages[name].get("old_enough") is True
        }

        if not verified_outdated:
            return

        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": freshness.format_context(
                            verified_outdated
                        ),
                    }
                }
            )
        )

    except Exception:
        pass  # Fail open -- never block session start


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/neural/Code/AgentParadise/agentic-primitives/.worktrees/plugin-doctor && uv run pytest tests/unit/claude/hooks/test_plugin_doctor.py -v`
Expected: PASS — every test in the file, including all of Task 1's and Task 2's new tests, and every pre-existing test except the deleted `test_emits_context_when_plugin_outdated`.

Then confirm the plugin manifest and hooks are still valid (nothing in this task touches `plugin.json` or `hooks.json`, but confirm no regression):

Run: `claude plugin validate plugins/plugin-doctor`
Expected: no errors reported for `plugins/plugin-doctor`.

- [ ] **Step 5: Commit**

```bash
cd /Users/neural/Code/AgentParadise/agentic-primitives/.worktrees/plugin-doctor
git add plugins/plugin-doctor/hooks/handlers/session-start.py tests/unit/claude/hooks/test_plugin_doctor.py
git commit -m "feat(plugin-doctor): gate outdated-version warnings on a 48h GitHub release age"
```

---

## Manual verification (post-merge, not automated)

Same as the original plan's manual-verification note: once this branch is merged and installed via `claude plugin update plugin-doctor@agentic-primitives`, the real end-to-end proof is starting a session shortly after a genuine `agentic-primitives` plugin release lands (tagged `<plugin>/v<version>` on GitHub) and confirming plugin-doctor stays silent about it for the first 48 hours, then surfaces it on the first weekly check after that window closes.
