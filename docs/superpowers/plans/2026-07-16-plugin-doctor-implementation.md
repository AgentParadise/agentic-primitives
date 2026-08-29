# plugin-doctor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `plugin-doctor@agentic-primitives`, a plugin that warns (via a `SessionStart` hook) when installed `agentic-primitives` plugins have newer versions available, checked at most weekly, and that never updates anything on its own.

**Architecture:** Pure comparison logic (semver parsing, installed-vs-catalog diffing, cadence gating, state I/O) lives in `plugins/plugin-doctor/hooks/lib/freshness.py`, unit-tested directly with no subprocess or real filesystem paths. A thin `session-start.py` handler wires that logic to real paths (with env-var overrides for testability), optionally refreshes the marketplace cache via `claude plugin marketplace update`, and emits `hookSpecificOutput.additionalContext` when something's outdated. Everything fails silent/open, matching every other hook handler in this repo.

**Tech Stack:** Python 3.11+ (stdlib only — `json`, `subprocess`, `pathlib`, `datetime`, `importlib.util`), pytest, following the existing `plugins/sdlc/hooks/validators/` pure-function + dynamic-import pattern.

## Global Constraints

- Only compare plugins sourced from the `agentic-primitives` marketplace — never other marketplaces (spec §"Non-goals").
- Refresh the marketplace catalog at most once every 7 days; comparison itself runs every session against whatever's cached (spec §3).
- Never run `claude plugin update` automatically — only inform Claude via `additionalContext`, which must ask the user first (spec §3 step 4, §"Goal").
- All failure modes (missing cache, malformed JSON, `claude` not on `PATH`, no network) fail silent/open — never block session start (spec §4).
- No manual "check now" slash command in this plan — out of scope per spec (spec §"Non-goals").
- New plugin, not an addition to an existing one: `plugins/plugin-doctor/`, `.claude-plugin/plugin.json` with `name`, `version`, `description`, `author`, `repository` (per `CLAUDE.md` "Plugin Structure" — only `name` is strictly required, but existing plugins set all five).
- Must be registered in `.claude-plugin/marketplace.json` and both README.md tables per `CLAUDE.md` "Add a plugin" checklist.
- Run `just qa-fix` before considering the work done (repo convention).

---

### Task 1: State I/O and cadence gating

**Files:**
- Create: `plugins/plugin-doctor/hooks/lib/freshness.py`
- Test: `tests/unit/claude/hooks/test_plugin_doctor.py`

**Interfaces:**
- Produces: `freshness.read_state(state_path: Path) -> dict`, `freshness.write_state(state_path: Path, state: dict) -> None`, `freshness.is_check_due(last_checked_at: str | None, now: datetime, interval_days: int = 7) -> bool`. Task 2 imports and extends this same module; Task 3's handler calls all three functions.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/claude/hooks/test_plugin_doctor.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/neural/Code/AgentParadise/agentic-primitives && uv run pytest tests/unit/claude/hooks/test_plugin_doctor.py -v`
Expected: FAIL — `plugins/plugin-doctor/hooks/lib/freshness.py` doesn't exist, so `load_freshness()` raises (`spec` is `None`, `AttributeError` on `.loader`).

- [ ] **Step 3: Write the minimal implementation**

Create `plugins/plugin-doctor/hooks/lib/freshness.py`:

```python
"""
Pure functions for plugin-doctor: state I/O, cadence gating, semver
comparison, and outdated-plugin context formatting.

No I/O side effects except read_state/write_state, which take explicit
paths so callers (and tests) control where state lives. No subprocess
calls anywhere in this module — the marketplace refresh subprocess call
lives in session-start.py, not here.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def read_state(state_path: Path) -> dict:
    """Read the state file, returning {} if missing or malformed."""
    try:
        return json.loads(state_path.read_text())
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
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return now - last >= timedelta(days=interval_days)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/neural/Code/AgentParadise/agentic-primitives && uv run pytest tests/unit/claude/hooks/test_plugin_doctor.py -v`
Expected: PASS — 8 tests (3 `TestStateIO` + 5 `TestIsCheckDue`).

- [ ] **Step 5: Commit**

```bash
cd /Users/neural/Code/AgentParadise/agentic-primitives
git add plugins/plugin-doctor/hooks/lib/freshness.py tests/unit/claude/hooks/test_plugin_doctor.py
git commit -m "feat(plugin-doctor): add state I/O and cadence gating"
```

---

### Task 2: Semver comparison and context formatting

**Files:**
- Modify: `plugins/plugin-doctor/hooks/lib/freshness.py`
- Modify: `tests/unit/claude/hooks/test_plugin_doctor.py`

**Interfaces:**
- Consumes: nothing from Task 1's functions directly (independent pure functions in the same module).
- Produces: `freshness.parse_semver(version: str) -> tuple[int, int, int] | None`, `freshness.get_installed_versions(cache_root: Path) -> dict[str, str]`, `freshness.get_catalog_versions(marketplace_plugins_root: Path) -> dict[str, str]`, `freshness.diff_outdated(installed: dict[str, str], catalog: dict[str, str]) -> dict[str, tuple[str, str]]`, `freshness.format_context(outdated: dict[str, tuple[str, str]]) -> str`. Task 3's handler calls all five.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/claude/hooks/test_plugin_doctor.py` (after the `TestIsCheckDue` class):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/neural/Code/AgentParadise/agentic-primitives && uv run pytest tests/unit/claude/hooks/test_plugin_doctor.py -v`
Expected: FAIL — `AttributeError: module 'plugin_doctor_freshness' has no attribute 'parse_semver'` (and similarly for the other four new functions).

- [ ] **Step 3: Write the minimal implementation**

Append to `plugins/plugin-doctor/hooks/lib/freshness.py` (add `import re` to the existing imports at the top, then append these functions):

```python
import re

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/neural/Code/AgentParadise/agentic-primitives && uv run pytest tests/unit/claude/hooks/test_plugin_doctor.py -v`
Expected: PASS — 21 tests total (8 from Task 1 + 13 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/neural/Code/AgentParadise/agentic-primitives
git add plugins/plugin-doctor/hooks/lib/freshness.py tests/unit/claude/hooks/test_plugin_doctor.py
git commit -m "feat(plugin-doctor): add semver comparison and context formatting"
```

---

### Task 3: Plugin scaffold and session-start handler

**Files:**
- Create: `plugins/plugin-doctor/.claude-plugin/plugin.json`
- Create: `plugins/plugin-doctor/hooks/hooks.json`
- Create: `plugins/plugin-doctor/hooks/handlers/session-start.py`
- Modify: `tests/unit/claude/hooks/test_plugin_doctor.py`

**Interfaces:**
- Consumes: `freshness.read_state`, `freshness.write_state`, `freshness.is_check_due`, `freshness.get_installed_versions`, `freshness.get_catalog_versions`, `freshness.diff_outdated`, `freshness.format_context` (all from Tasks 1–2).
- Produces: a runnable `session-start.py` that reads a `PreToolUse`-style JSON event from stdin and either prints nothing or `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}`. Honors `PLUGIN_DOCTOR_CACHE_DIR`, `PLUGIN_DOCTOR_MARKETPLACE_DIR`, `PLUGIN_DOCTOR_STATE_PATH`, `PLUGIN_DOCTOR_SKIP_REFRESH` env var overrides — Task 4 doesn't touch these, but any future test or manual run relies on this exact contract.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/claude/hooks/test_plugin_doctor.py`:

```python
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

    def test_emits_context_when_plugin_outdated(self, tmp_path):
        cache_root = tmp_path / "cache"
        (cache_root / "sdlc" / "1.4.0").mkdir(parents=True)
        marketplace_root = tmp_path / "marketplace"
        manifest_dir = marketplace_root / "sdlc" / ".claude-plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text(json.dumps({"version": "1.5.0"}))
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
        assert result["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert "sdlc: 1.4.0 -> 1.5.0" in result["hookSpecificOutput"]["additionalContext"]

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/neural/Code/AgentParadise/agentic-primitives && uv run pytest tests/unit/claude/hooks/test_plugin_doctor.py -v`
Expected: FAIL — `plugins/plugin-doctor/hooks/handlers/session-start.py` doesn't exist, so `subprocess.run` fails to find the interpreter target / `result.stdout` is empty and `FileNotFoundError` or non-zero exit surfaces as a test failure (`json.loads` on empty output raising, or subprocess raising `FileNotFoundError` for the missing script path).

- [ ] **Step 3: Write the minimal implementation**

Create `plugins/plugin-doctor/.claude-plugin/plugin.json`:

```json
{
  "name": "plugin-doctor",
  "version": "0.1.0",
  "description": "Warns when installed agentic-primitives plugins have updates available, checked weekly. Never auto-updates.",
  "author": {
    "name": "NeuralEmpowerment"
  },
  "repository": "https://github.com/AgentParadise/agentic-primitives"
}
```

Create `plugins/plugin-doctor/hooks/hooks.json`:

```json
{
  "description": "Warns when installed agentic-primitives plugins have newer versions available (checked at most weekly). Never auto-updates.",
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/handlers/session-start.py",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

Create `plugins/plugin-doctor/hooks/handlers/session-start.py`:

```python
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
```

Make it executable:

```bash
chmod +x plugins/plugin-doctor/hooks/handlers/session-start.py
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/neural/Code/AgentParadise/agentic-primitives && uv run pytest tests/unit/claude/hooks/test_plugin_doctor.py -v`
Expected: PASS — 26 tests total (21 from Tasks 1–2 + 5 new).

Then validate the manifest and hooks directly:

Run: `cd /Users/neural/Code/AgentParadise/agentic-primitives && claude plugin validate plugins/plugin-doctor`
Expected: no errors reported for `plugins/plugin-doctor` (the command may print unrelated pre-existing warnings for other plugins if run against the whole repo — running it scoped to `plugins/plugin-doctor` avoids that noise).

- [ ] **Step 5: Commit**

```bash
cd /Users/neural/Code/AgentParadise/agentic-primitives
git add plugins/plugin-doctor tests/unit/claude/hooks/test_plugin_doctor.py
git commit -m "feat(plugin-doctor): add SessionStart handler and plugin manifest"
```

---

### Task 4: Marketplace registration and docs

**Files:**
- Modify: `.claude-plugin/marketplace.json`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Create: `plugins/plugin-doctor/README.md`
- Create: `plugins/plugin-doctor/CHANGELOG.md`

**Interfaces:**
- Consumes: nothing new — this task only adds registration/documentation for the plugin built in Tasks 1–3.
- Produces: nothing consumed by other tasks — this is the last task in the plan.

- [ ] **Step 1: Register in the marketplace catalog**

In `.claude-plugin/marketplace.json`, the `"plugins"` array currently ends with the `"experiments"` entry followed by `    }\n  ]\n}`. Add a new entry after `"experiments"` and before the closing `]`:

```json
    {
      "name": "experiments",
      "description": "Hypothesis-first experiment workflow — scaffolding, eval packs, results, verdicts, and the two-commit discipline",
      "source": "./plugins/experiments",
      "category": "development"
    },
    {
      "name": "plugin-doctor",
      "description": "Warns when installed agentic-primitives plugins have updates available, checked weekly. Never auto-updates.",
      "source": "./plugins/plugin-doctor",
      "category": "observability"
    }
  ]
}
```

(i.e. add a trailing comma to the existing `"experiments"` entry's closing `}` and insert the new object before the final `]`.)

- [ ] **Step 2: Validate the marketplace manifest**

Run: `cd /Users/neural/Code/AgentParadise/agentic-primitives && claude plugin validate .claude-plugin/marketplace.json`
Expected: no errors mentioning `plugin-doctor` or malformed JSON.

- [ ] **Step 3: Add the plugin README**

Create `plugins/plugin-doctor/README.md`:

```markdown
# 🩺 plugin-doctor

Warns you when installed `agentic-primitives` plugins have newer versions available. Checked at most once a week. Never updates anything on its own — it only tells Claude, who asks you.

## How it works

On `SessionStart`, plugin-doctor:

1. Checks `~/.claude/plugin-doctor/state.json` for when it last refreshed the marketplace catalog.
2. If that was 7+ days ago (or never), runs `claude plugin marketplace update agentic-primitives` to refresh the local catalog cache, then records the new check time — regardless of whether the refresh succeeded, so a network hiccup costs one missed week, not a retry loop.
3. Compares every installed `agentic-primitives` plugin's version (read from `~/.claude/plugins/cache/agentic-primitives/<plugin>/<version>/`) against the catalog version (read from `~/.claude/plugins/marketplaces/agentic-primitives/plugins/<plugin>/.claude-plugin/plugin.json`).
4. If anything's outdated, tells Claude via `additionalContext` — Claude will mention it early in the conversation and ask if you want to update. It will never run `claude plugin update` without you explicitly agreeing.

Only `agentic-primitives`-sourced plugins are checked — not other marketplaces.

## Install

```bash
claude plugin install plugin-doctor@agentic-primitives --scope user
```

## Updating manually

If you don't want to wait for the weekly check:

```bash
claude plugin marketplace update agentic-primitives
claude plugin update <name>@agentic-primitives
```
```

- [ ] **Step 4: Add the plugin CHANGELOG**

Create `plugins/plugin-doctor/CHANGELOG.md`:

```markdown
# Changelog

## 0.1.0 — 2026-07-16

- Initial release: `SessionStart` hook warns when installed `agentic-primitives` plugins have newer versions available, checked at most weekly, never auto-updates.
```

- [ ] **Step 5: Update the root README**

In `README.md`, the "Available Plugins" table currently ends with the `experiments` row. Add a new row immediately after it:

```markdown
| **experiments** | `claude plugin install experiments@agentic-primitives --scope user` | Hypothesis-first experiment workflow |
| **plugin-doctor** | `claude plugin install plugin-doctor@agentic-primitives --scope user` | Warns when installed plugins are outdated |
```

In the "What's in each plugin" table, add a row immediately after the `experiments` row:

```markdown
| **experiments** | -- | `running-experiments` | -- | -- |
| **plugin-doctor** | -- | -- | -- | SessionStart plugin-freshness check (weekly, never auto-updates) |
```

- [ ] **Step 6: Update the root CHANGELOG**

In `CHANGELOG.md`, under the existing `## [Unreleased]` heading (before the first `###` subsection), add a new subsection:

```markdown
### 🩺 plugin-doctor

A new plugin that warns when installed `agentic-primitives` plugins have updates available.

#### Added

- **`plugins/plugin-doctor/`** — `SessionStart` hook compares installed plugin versions (from `~/.claude/plugins/cache/agentic-primitives/`) against the marketplace catalog (from `~/.claude/plugins/marketplaces/agentic-primitives/`), refreshing the catalog at most once a week. Emits `additionalContext` naming outdated plugins when found; instructs Claude to ask the user before updating anything. Never runs `claude plugin update` itself.
- **26 unit/integration tests** in `tests/unit/claude/hooks/test_plugin_doctor.py` covering state I/O, cadence gating, semver comparison, and the handler end-to-end via subprocess.
```

- [ ] **Step 7: Run full QA and commit**

Run: `cd /Users/neural/Code/AgentParadise/agentic-primitives && just qa-fix`
Expected: formatting applied, lint passes, all tests pass (including the 26 new ones).

```bash
cd /Users/neural/Code/AgentParadise/agentic-primitives
git add .claude-plugin/marketplace.json README.md CHANGELOG.md plugins/plugin-doctor/README.md plugins/plugin-doctor/CHANGELOG.md
git commit -m "docs(plugin-doctor): register plugin and document"
```

---

## Manual verification (post-merge, not automated)

`plugin-doctor` can only be installed once this branch is merged and the `agentic-primitives` GitHub marketplace source picks it up (the configured marketplace source is the GitHub repo, not a local path — see `claude plugin marketplace list`). After merging:

```bash
claude plugin marketplace update agentic-primitives
claude plugin install plugin-doctor@agentic-primitives --scope user
```

Then start a new Claude Code session and confirm no crash. To force an "outdated" scenario for a real end-to-end smoke test, temporarily edit the cached `plugin.json` version for an already-installed plugin down a version, start a session, and confirm the warning appears and that Claude asks before updating rather than updating automatically.
