#!/usr/bin/env python3
"""Tests for scripts/install_plugin.py — plugin install/uninstall/list."""

import json
import shutil
from pathlib import Path

import pytest

# Import the installer module
import importlib.util

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "install_plugin.py"

spec = importlib.util.spec_from_file_location("install_plugin", SCRIPT_PATH)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


# ============================================================================
# Helpers
# ============================================================================


def _make_plugin(base_dir: Path, name: str = "test-plugin", *, with_hooks: bool = True) -> Path:
    """Create a minimal plugin directory under base_dir/name."""
    plugin_dir = base_dir / name
    plugin_dir.mkdir(parents=True, exist_ok=True)

    manifest_dir = plugin_dir / ".claude-plugin"
    manifest_dir.mkdir(exist_ok=True)
    manifest = {
        "name": name,
        "version": "1.2.3",
        "description": f"A test plugin ({name})",
    }
    (manifest_dir / "plugin.json").write_text(json.dumps(manifest))

    if with_hooks:
        hooks_dir = plugin_dir / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        hooks_data = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/handler.py",
                                "timeout": 10,
                            }
                        ],
                    }
                ]
            }
        }
        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_data))
        (hooks_dir / "handler.py").write_text("# handler stub")

    (plugin_dir / "CHANGELOG.md").write_text("# Changelog\n## 1.2.3\n- Initial\n")
    return plugin_dir


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sandbox(tmp_path):
    """Set up an isolated sandbox with monkeypatched PLUGINS_DIR and REPO_ROOT.

    Returns a dict with sandbox_root and plugins_dir paths.
    Restores originals on cleanup.
    """
    sandbox_root = tmp_path / "sandbox"
    plugins_dir = sandbox_root / "plugins"
    plugins_dir.mkdir(parents=True)

    orig_plugins_dir = installer.PLUGINS_DIR
    orig_repo_root = installer.REPO_ROOT
    installer.PLUGINS_DIR = plugins_dir
    installer.REPO_ROOT = sandbox_root

    yield {"root": sandbox_root, "plugins": plugins_dir}

    installer.PLUGINS_DIR = orig_plugins_dir
    installer.REPO_ROOT = orig_repo_root


# ============================================================================
# load_plugin_json
# ============================================================================


class TestLoadPluginJson:
    def test_loads_valid_manifest(self, tmp_path):
        plugin = _make_plugin(tmp_path, "my-plugin")
        data = installer.load_plugin_json(plugin)
        assert data["name"] == "my-plugin"
        assert data["version"] == "1.2.3"

    def test_missing_manifest_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            installer.load_plugin_json(tmp_path / "nonexistent")


# ============================================================================
# load_hooks
# ============================================================================


class TestLoadHooks:
    def test_loads_hooks_from_plugin(self, tmp_path):
        plugin = _make_plugin(tmp_path, "hooked", with_hooks=True)
        hooks = installer.load_hooks(plugin)
        assert "PreToolUse" in hooks
        assert len(hooks["PreToolUse"]) == 1

    def test_returns_empty_when_no_hooks(self, tmp_path):
        plugin = _make_plugin(tmp_path, "no-hooks", with_hooks=False)
        hooks = installer.load_hooks(plugin)
        assert hooks == {}


# ============================================================================
# merge_hooks / remove_hooks
# ============================================================================


class TestHookMerging:
    def test_merge_adds_tagged_hooks(self, tmp_path):
        plugin = _make_plugin(tmp_path, "test-plugin")
        settings = {}
        hooks = installer.load_hooks(plugin)
        cache = Path("/fake/cache/test-plugin")

        result = installer.merge_hooks(settings, hooks, "test-plugin", cache)

        assert "hooks" in result
        assert "PreToolUse" in result["hooks"]
        entry = result["hooks"]["PreToolUse"][0]
        hook = entry["hooks"][0]
        assert hook["_plugin"] == "agentic-primitives/test-plugin"
        assert "/fake/cache/test-plugin/hooks/handler.py" in hook["command"]

    def test_merge_rewrites_plugin_root(self, tmp_path):
        plugin = _make_plugin(tmp_path, "test-plugin")
        settings = {}
        hooks = installer.load_hooks(plugin)
        cache = Path("/installed/path")

        result = installer.merge_hooks(settings, hooks, "test-plugin", cache)

        hook = result["hooks"]["PreToolUse"][0]["hooks"][0]
        assert "${CLAUDE_PLUGIN_ROOT}" not in hook["command"]
        assert "/installed/path" in hook["command"]

    def test_merge_preserves_existing_hooks(self):
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [{"type": "command", "command": "existing.py"}],
                    }
                ]
            }
        }
        new_hooks = {
            "PreToolUse": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python ${CLAUDE_PLUGIN_ROOT}/new.py",
                        }
                    ],
                }
            ]
        }
        result = installer.merge_hooks(
            settings, new_hooks, "my-plugin", Path("/cache")
        )
        assert len(result["hooks"]["PreToolUse"]) == 2

    def test_merge_empty_hooks_is_noop(self):
        settings = {"hooks": {"Stop": [{"hooks": [{"command": "x"}]}]}}
        result = installer.merge_hooks(settings, {}, "test", Path("/cache"))
        assert result == settings

    def test_remove_hooks_by_tag(self):
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "",
                        "hooks": [
                            {
                                "command": "a.py",
                                "_plugin": "agentic-primitives/sdlc",
                            }
                        ],
                    },
                    {
                        "matcher": "*",
                        "hooks": [{"command": "manual.py"}],
                    },
                ]
            }
        }
        result = installer.remove_hooks(settings, "sdlc")
        assert len(result["hooks"]["PreToolUse"]) == 1
        assert result["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "manual.py"

    def test_remove_hooks_cleans_empty_events(self):
        settings = {
            "hooks": {
                "Stop": [
                    {
                        "hooks": [
                            {
                                "command": "x.py",
                                "_plugin": "agentic-primitives/test",
                            }
                        ]
                    }
                ]
            }
        }
        result = installer.remove_hooks(settings, "test")
        assert "hooks" not in result

    def test_remove_hooks_leaves_untagged_untouched(self):
        settings = {
            "hooks": {
                "Stop": [
                    {"hooks": [{"command": "manual.py"}]},
                ]
            }
        }
        result = installer.remove_hooks(settings, "sdlc")
        assert len(result["hooks"]["Stop"]) == 1


# ============================================================================
# enabledPlugins (dict and list formats)
# ============================================================================


class TestEnabledPlugins:
    def test_add_to_empty_dict(self):
        settings = {}
        result = installer.add_enabled_plugin(settings, "sdlc")
        assert result["enabledPlugins"]["agentic-primitives/sdlc"] is True

    def test_add_preserves_existing_dict_entries(self):
        settings = {"enabledPlugins": {"other/plugin": True}}
        result = installer.add_enabled_plugin(settings, "sdlc")
        assert "other/plugin" in result["enabledPlugins"]
        assert "agentic-primitives/sdlc" in result["enabledPlugins"]

    def test_add_idempotent_dict(self):
        settings = {"enabledPlugins": {"agentic-primitives/sdlc": True}}
        result = installer.add_enabled_plugin(settings, "sdlc")
        assert result["enabledPlugins"]["agentic-primitives/sdlc"] is True

    def test_add_to_list_format(self):
        settings = {"enabledPlugins": ["existing/plugin"]}
        result = installer.add_enabled_plugin(settings, "sdlc")
        assert "agentic-primitives/sdlc" in result["enabledPlugins"]
        assert "existing/plugin" in result["enabledPlugins"]

    def test_add_idempotent_list(self):
        settings = {"enabledPlugins": ["agentic-primitives/sdlc"]}
        result = installer.add_enabled_plugin(settings, "sdlc")
        assert result["enabledPlugins"].count("agentic-primitives/sdlc") == 1

    def test_remove_from_dict(self):
        settings = {
            "enabledPlugins": {
                "agentic-primitives/sdlc": True,
                "other/plugin": True,
            }
        }
        result = installer.remove_enabled_plugin(settings, "sdlc")
        assert "agentic-primitives/sdlc" not in result["enabledPlugins"]
        assert "other/plugin" in result["enabledPlugins"]

    def test_remove_last_from_dict_cleans_key(self):
        settings = {"enabledPlugins": {"agentic-primitives/sdlc": True}}
        result = installer.remove_enabled_plugin(settings, "sdlc")
        assert "enabledPlugins" not in result

    def test_remove_from_list(self):
        settings = {
            "enabledPlugins": [
                "agentic-primitives/sdlc",
                "other/plugin",
            ]
        }
        result = installer.remove_enabled_plugin(settings, "sdlc")
        assert "agentic-primitives/sdlc" not in result["enabledPlugins"]

    def test_remove_last_from_list_cleans_key(self):
        settings = {"enabledPlugins": ["agentic-primitives/sdlc"]}
        result = installer.remove_enabled_plugin(settings, "sdlc")
        assert "enabledPlugins" not in result

    def test_remove_nonexistent_is_noop(self):
        settings = {"enabledPlugins": {"other/plugin": True}}
        result = installer.remove_enabled_plugin(settings, "sdlc")
        assert "other/plugin" in result["enabledPlugins"]


# ============================================================================
# settings I/O
# ============================================================================


class TestSettingsIO:
    def test_load_creates_empty_when_missing(self, tmp_path):
        result = installer.load_settings(tmp_path / "nonexistent.json")
        assert result == {}

    def test_load_reads_existing(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"foo": "bar"}))
        result = installer.load_settings(path)
        assert result == {"foo": "bar"}

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "a" / "b" / "settings.json"
        installer.save_settings(path, {"test": True})
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["test"] is True

    def test_save_has_trailing_newline(self, tmp_path):
        path = tmp_path / "settings.json"
        installer.save_settings(path, {})
        assert path.read_text().endswith("\n")


# ============================================================================
# Full install / uninstall flow (sandboxed)
# ============================================================================


class TestInstallUninstallFlow:
    def test_install_creates_cache_and_settings(self, sandbox):
        _make_plugin(sandbox["plugins"], "test-plugin")
        installer.install_plugin("test-plugin", global_scope=False)

        cache_dir = installer.get_cache_dir("test-plugin", False)
        assert cache_dir.exists()
        assert (cache_dir / ".claude-plugin" / "plugin.json").exists()
        assert (cache_dir / "hooks" / "handler.py").exists()

        settings_path = installer.get_settings_path(False)
        settings = json.loads(settings_path.read_text())
        assert "agentic-primitives/test-plugin" in settings["enabledPlugins"]
        assert "PreToolUse" in settings["hooks"]

        hook = settings["hooks"]["PreToolUse"][0]["hooks"][0]
        assert hook["_plugin"] == "agentic-primitives/test-plugin"
        assert str(cache_dir) in hook["command"]

    def test_uninstall_removes_cache_and_settings(self, sandbox):
        _make_plugin(sandbox["plugins"], "test-plugin")
        installer.install_plugin("test-plugin", global_scope=False)
        installer.uninstall_plugin("test-plugin", global_scope=False)

        cache_dir = installer.get_cache_dir("test-plugin", False)
        assert not cache_dir.exists()

        settings_path = installer.get_settings_path(False)
        settings = json.loads(settings_path.read_text())
        assert "enabledPlugins" not in settings
        assert "hooks" not in settings

    def test_reinstall_is_idempotent(self, sandbox):
        _make_plugin(sandbox["plugins"], "test-plugin")
        installer.install_plugin("test-plugin", global_scope=False)
        installer.install_plugin("test-plugin", global_scope=False)

        settings_path = installer.get_settings_path(False)
        settings = json.loads(settings_path.read_text())

        # Should have exactly 1 hook entry, not duplicated
        assert len(settings["hooks"]["PreToolUse"]) == 1

    def test_install_nonexistent_plugin_exits(self, sandbox):
        with pytest.raises(SystemExit):
            installer.install_plugin("nonexistent", global_scope=False)

    def test_install_plugin_without_hooks(self, sandbox):
        """Plugins without hooks should install without adding hook entries."""
        _make_plugin(sandbox["plugins"], "no-hooks", with_hooks=False)
        installer.install_plugin("no-hooks", global_scope=False)

        settings_path = installer.get_settings_path(False)
        settings = json.loads(settings_path.read_text())
        assert "agentic-primitives/no-hooks" in settings["enabledPlugins"]
        assert "hooks" not in settings or settings["hooks"] == {}


# ============================================================================
# list_plugins (uses real plugins dir)
# ============================================================================


class TestListPlugins:
    def test_list_discovers_plugins(self, capsys):
        """list_plugins should discover all real plugins."""
        # Ensure PLUGINS_DIR points at real plugins
        orig = installer.PLUGINS_DIR
        installer.PLUGINS_DIR = PROJECT_ROOT / "plugins"
        try:
            installer.list_plugins()
            captured = capsys.readouterr()
            assert "sdlc" in captured.out
            assert "workspace" in captured.out
            assert "research" in captured.out
            assert "meta" in captured.out
            assert "docs" in captured.out
            assert "v1.0.0" in captured.out
        finally:
            installer.PLUGINS_DIR = orig

    def test_list_shows_count(self, capsys):
        orig = installer.PLUGINS_DIR
        installer.PLUGINS_DIR = PROJECT_ROOT / "plugins"
        try:
            installer.list_plugins()
            captured = capsys.readouterr()
            assert "Available plugins (5)" in captured.out
        finally:
            installer.PLUGINS_DIR = orig


# ============================================================================
# CLI argument parsing
# ============================================================================


class TestCLI:
    def test_install_command_parsed(self):
        import subprocess

        result = subprocess.run(
            ["python3", str(SCRIPT_PATH), "install", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--global" in result.stdout

    def test_uninstall_command_parsed(self):
        import subprocess

        result = subprocess.run(
            ["python3", str(SCRIPT_PATH), "uninstall", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--global" in result.stdout

    def test_list_command_parsed(self):
        import subprocess

        result = subprocess.run(
            ["python3", str(SCRIPT_PATH), "list"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "sdlc" in result.stdout
