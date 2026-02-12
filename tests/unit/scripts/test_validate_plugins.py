#!/usr/bin/env python3
"""Tests for scripts/validate_plugins.py — plugin structure validation."""

import json
from pathlib import Path

import pytest

import importlib.util

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "validate_plugins.py"

spec = importlib.util.spec_from_file_location("validate_plugins", SCRIPT_PATH)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def valid_plugin(tmp_path):
    """Create a valid plugin directory."""
    plugin_dir = tmp_path / "my-plugin"
    plugin_dir.mkdir()

    manifest_dir = plugin_dir / ".claude-plugin"
    manifest_dir.mkdir()
    manifest = {
        "name": "my-plugin",
        "version": "1.0.0",
        "description": "A valid plugin for testing",
    }
    (manifest_dir / "plugin.json").write_text(json.dumps(manifest))
    (plugin_dir / "CHANGELOG.md").write_text("# Changelog\n## 1.0.0\n- Initial\n")

    return plugin_dir


@pytest.fixture
def plugins_dir(tmp_path, valid_plugin):
    """Create a plugins directory with one valid plugin inside."""
    plugins = tmp_path / "plugins"
    plugins.mkdir()

    import shutil
    shutil.copytree(valid_plugin, plugins / "my-plugin")
    return plugins


# ============================================================================
# validate_plugin_json
# ============================================================================


class TestValidatePluginJson:
    def test_valid_manifest(self, valid_plugin):
        path = valid_plugin / ".claude-plugin" / "plugin.json"
        ok, errors = validator.validate_plugin_json(path)
        assert ok
        assert errors == []

    def test_missing_file(self, tmp_path):
        ok, errors = validator.validate_plugin_json(tmp_path / "missing.json")
        assert not ok
        assert any("Missing" in e for e in errors)

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not valid json")
        ok, errors = validator.validate_plugin_json(path)
        assert not ok
        assert any("Invalid JSON" in e for e in errors)

    def test_missing_name(self, tmp_path):
        path = tmp_path / "plugin.json"
        path.write_text(json.dumps({"version": "1.0.0", "description": "Test"}))
        ok, errors = validator.validate_plugin_json(path)
        assert not ok
        assert any("name" in e for e in errors)

    def test_missing_version(self, tmp_path):
        path = tmp_path / "plugin.json"
        path.write_text(json.dumps({"name": "test", "description": "Test"}))
        ok, errors = validator.validate_plugin_json(path)
        assert not ok
        assert any("version" in e for e in errors)

    def test_missing_description(self, tmp_path):
        path = tmp_path / "plugin.json"
        path.write_text(json.dumps({"name": "test", "version": "1.0.0"}))
        ok, errors = validator.validate_plugin_json(path)
        assert not ok
        assert any("description" in e for e in errors)

    def test_bad_semver_two_parts(self, tmp_path):
        path = tmp_path / "plugin.json"
        path.write_text(
            json.dumps({"name": "t", "version": "1.0", "description": "Test"})
        )
        ok, errors = validator.validate_plugin_json(path)
        assert not ok
        assert any("SemVer" in e for e in errors)

    def test_bad_semver_four_parts(self, tmp_path):
        path = tmp_path / "plugin.json"
        path.write_text(
            json.dumps({"name": "t", "version": "1.0.0.0", "description": "Test"})
        )
        ok, errors = validator.validate_plugin_json(path)
        assert not ok
        assert any("SemVer" in e for e in errors)

    def test_valid_semver_prerelease(self, tmp_path):
        """SemVer with pre-release tag has 3 dot-parts so passes current check."""
        path = tmp_path / "plugin.json"
        path.write_text(
            json.dumps(
                {"name": "t", "version": "1.0.0-beta", "description": "Test plugin"}
            )
        )
        # "1.0.0-beta".split(".") gives 3 parts, so it passes
        ok, errors = validator.validate_plugin_json(path)
        assert ok


# ============================================================================
# validate_plugin_structure
# ============================================================================


class TestValidatePluginStructure:
    def test_valid_structure(self, valid_plugin):
        ok, errors = validator.validate_plugin_structure(valid_plugin)
        assert ok
        assert errors == []

    def test_missing_changelog(self, tmp_path):
        plugin_dir = tmp_path / "no-changelog"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".claude-plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps(
                {"name": "test", "version": "1.0.0", "description": "A test plugin"}
            )
        )
        ok, errors = validator.validate_plugin_structure(plugin_dir)
        assert not ok
        assert any("CHANGELOG" in e for e in errors)

    def test_empty_changelog(self, tmp_path):
        plugin_dir = tmp_path / "empty-cl"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".claude-plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps(
                {"name": "test", "version": "1.0.0", "description": "A test plugin"}
            )
        )
        (plugin_dir / "CHANGELOG.md").write_text("")
        ok, errors = validator.validate_plugin_structure(plugin_dir)
        assert not ok
        assert any("empty" in e.lower() for e in errors)

    def test_missing_manifest_and_changelog(self, tmp_path):
        plugin_dir = tmp_path / "bare"
        plugin_dir.mkdir()
        ok, errors = validator.validate_plugin_structure(plugin_dir)
        assert not ok
        assert len(errors) >= 2  # Missing plugin.json + missing CHANGELOG


# ============================================================================
# validate_all_plugins
# ============================================================================


class TestValidateAllPlugins:
    def test_validates_real_plugins(self):
        """All real plugins in the repo should pass validation."""
        assert validator.validate_all_plugins(PROJECT_ROOT / "plugins")

    def test_nonexistent_dir_returns_false(self, tmp_path):
        assert not validator.validate_all_plugins(tmp_path / "missing")

    def test_empty_dir_returns_true(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert validator.validate_all_plugins(empty)

    def test_mixed_valid_invalid(self, tmp_path):
        plugins = tmp_path / "plugins"
        plugins.mkdir()

        # Valid plugin
        good = plugins / "good"
        good.mkdir()
        (good / ".claude-plugin").mkdir()
        (good / ".claude-plugin" / "plugin.json").write_text(
            json.dumps(
                {"name": "good", "version": "1.0.0", "description": "A good plugin"}
            )
        )
        (good / "CHANGELOG.md").write_text("# Changes\n")

        # Invalid plugin (missing version)
        bad = plugins / "bad"
        bad.mkdir()
        (bad / ".claude-plugin").mkdir()
        (bad / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "bad", "description": "Missing version field"})
        )
        (bad / "CHANGELOG.md").write_text("# Changes\n")

        assert not validator.validate_all_plugins(plugins)
