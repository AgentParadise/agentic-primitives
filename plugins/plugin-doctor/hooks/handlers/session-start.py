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
