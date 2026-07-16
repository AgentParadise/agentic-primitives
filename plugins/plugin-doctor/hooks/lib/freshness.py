"""
Pure functions for plugin-doctor: state I/O, cadence gating, semver
comparison, and outdated-plugin context formatting.

No I/O side effects except read_state/write_state, which take explicit
paths so callers (and tests) control where state lives. No subprocess
calls anywhere in this module — the marketplace refresh subprocess call
lives in session-start.py, not here.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


def read_state(state_path: Path) -> dict:
    """Read the state file, returning {} if missing or malformed."""
    try:
        data = json.loads(state_path.read_text())
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(state_path: Path, state: dict) -> None:
    """Write the state file, creating parent directories as needed."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state))


def is_check_due(
    last_checked_at: str | None, now: datetime, interval_days: int = 7
) -> bool:
    """True if a refresh is due: no valid last_checked_at, or it's at
    least interval_days old."""
    if not last_checked_at:
        return True
    try:
        last = datetime.fromisoformat(last_checked_at)
    except (ValueError, TypeError):
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return now - last >= timedelta(days=interval_days)


SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def parse_semver(version) -> tuple[int, int, int] | None:
    """Parse a semver-ish string like '1.4.0' into (1, 4, 0).

    Returns None if the string doesn't start with N.N.N (e.g. "unknown"),
    or if version isn't a string at all.
    """
    if not isinstance(version, str):
        return None
    match = SEMVER_RE.match(version.strip())
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def get_installed_versions(cache_root: Path) -> dict[str, str]:
    """Return {plugin_name: version} for each plugin under cache_root.

    cache_root is e.g. ~/.claude/plugins/cache/agentic-primitives, where
    each child directory is a plugin name containing one or more
    version-numbered subdirectories. If more than one version directory
    exists for a plugin, the highest by semver wins.
    """
    installed: dict[str, str] = {}
    if not cache_root.is_dir():
        return installed

    for plugin_dir in sorted(cache_root.iterdir()):
        if not plugin_dir.is_dir():
            continue
        candidates = [
            (name, parsed)
            for name in (d.name for d in plugin_dir.iterdir() if d.is_dir())
            if (parsed := parse_semver(name)) is not None
        ]
        if not candidates:
            continue
        best_version, _ = max(candidates, key=lambda item: item[1])
        installed[plugin_dir.name] = best_version

    return installed


def get_catalog_versions(marketplace_plugins_root: Path) -> dict[str, str]:
    """Return {plugin_name: version} read from each plugin's plugin.json.

    marketplace_plugins_root is e.g.
    ~/.claude/plugins/marketplaces/agentic-primitives/plugins, where each
    child directory is a plugin name containing .claude-plugin/plugin.json.
    """
    catalog: dict[str, str] = {}
    if not marketplace_plugins_root.is_dir():
        return catalog

    for plugin_dir in sorted(marketplace_plugins_root.iterdir()):
        manifest_path = plugin_dir / ".claude-plugin" / "plugin.json"
        if not manifest_path.is_file():
            continue
        try:
            data = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        version = data.get("version")
        if isinstance(version, str) and parse_semver(version) is not None:
            catalog[plugin_dir.name] = version

    return catalog


def diff_outdated(
    installed: dict[str, str], catalog: dict[str, str]
) -> dict[str, tuple[str, str]]:
    """Return {plugin_name: (installed_version, catalog_version)} for each
    plugin where the catalog version is strictly newer than installed.

    Plugins missing from the catalog, or with unparsable versions on
    either side, are skipped rather than flagged.
    """
    outdated: dict[str, tuple[str, str]] = {}
    for name, installed_version in installed.items():
        catalog_version = catalog.get(name)
        if catalog_version is None:
            continue
        installed_parsed = parse_semver(installed_version)
        catalog_parsed = parse_semver(catalog_version)
        if installed_parsed is None or catalog_parsed is None:
            continue
        if catalog_parsed > installed_parsed:
            outdated[name] = (installed_version, catalog_version)
    return outdated


def format_context(outdated: dict[str, tuple[str, str]]) -> str:
    """Build the additionalContext message describing outdated plugins."""
    lines = [
        "agentic-primitives plugin update check: "
        f"{len(outdated)} installed plugin(s) have newer versions available.",
    ]
    for name, (installed_version, catalog_version) in sorted(outdated.items()):
        lines.append(f"  - {name}: {installed_version} -> {catalog_version}")
    lines.append(
        "Mention this to the user near the start of the conversation and ask "
        "if they'd like to update. If they agree, run "
        "`claude plugin update <name>@agentic-primitives` for each plugin "
        "they approve. Never run a plugin update without the user explicitly "
        "agreeing first."
    )
    return "\n".join(lines)
