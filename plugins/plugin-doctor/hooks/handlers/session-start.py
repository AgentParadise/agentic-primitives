#!/usr/bin/env python3
"""
SessionStart Handler - Warns when installed agentic-primitives plugins
are outdated.

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
from datetime import datetime, timezone
from pathlib import Path

CHECK_INTERVAL_DAYS = 7
MARKETPLACE_NAME = "agentic-primitives"


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


def main() -> None:
    try:
        if not sys.stdin.isatty():
            sys.stdin.read()  # drain stdin so Claude Code doesn't see a hang

        state_path = _state_path()
        state = freshness.read_state(state_path)
        now = datetime.now(timezone.utc)

        if freshness.is_check_due(
            state.get("last_checked_at"), now, CHECK_INTERVAL_DAYS
        ):
            _refresh_marketplace()
            freshness.write_state(state_path, {"last_checked_at": now.isoformat()})

        installed = freshness.get_installed_versions(_cache_root())
        catalog = freshness.get_catalog_versions(_marketplace_plugins_root())
        outdated = freshness.diff_outdated(installed, catalog)

        if not outdated:
            return

        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": freshness.format_context(outdated),
                    }
                }
            )
        )

    except Exception:
        pass  # Fail open -- never block session start


if __name__ == "__main__":
    main()
