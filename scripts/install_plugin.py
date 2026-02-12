#!/usr/bin/env python3
"""Install or uninstall agentic-primitives plugins.

Copies plugin files to the Claude Code plugin cache and merges hooks
into the target settings.json (project or global).

Usage:
    python scripts/install_plugin.py install <name> [--global]
    python scripts/install_plugin.py uninstall <name> [--global]
    python scripts/install_plugin.py list
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"
MARKETPLACE_NAME = "agentic-primitives"


def get_plugin_dir(name: str) -> Path:
    """Return the source plugin directory."""
    return PLUGINS_DIR / name


def load_plugin_json(plugin_dir: Path) -> dict:
    """Load and return plugin.json from a plugin directory."""
    manifest = plugin_dir / ".claude-plugin" / "plugin.json"
    if not manifest.exists():
        print(f"Error: No plugin.json found at {manifest}", file=sys.stderr)
        sys.exit(1)
    with open(manifest) as f:
        return json.load(f)


def get_cache_dir(name: str, global_scope: bool) -> Path:
    """Return the target cache directory for plugin installation."""
    if global_scope:
        base = Path.home() / ".claude" / "plugins" / "cache"
    else:
        base = REPO_ROOT / ".claude" / "plugins" / "cache"
    return base / MARKETPLACE_NAME / name / "local"


def get_settings_path(global_scope: bool) -> Path:
    """Return the target settings.json path."""
    if global_scope:
        return Path.home() / ".claude" / "settings.json"
    return REPO_ROOT / ".claude" / "settings.json"


def load_settings(path: Path) -> dict:
    """Load settings.json, creating it if it doesn't exist."""
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_settings(path: Path, data: dict) -> None:
    """Write settings.json with consistent formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def load_hooks(plugin_dir: Path) -> dict:
    """Load hooks.json from a plugin if it exists."""
    hooks_file = plugin_dir / "hooks" / "hooks.json"
    if not hooks_file.exists():
        return {}
    with open(hooks_file) as f:
        data = json.load(f)
    return data.get("hooks", {})


def make_hook_tag(name: str) -> str:
    """Generate a comment-like tag to identify hooks from a specific plugin."""
    return f"agentic-primitives/{name}"


def merge_hooks(settings: dict, plugin_hooks: dict, plugin_name: str, cache_dir: Path) -> dict:
    """Merge plugin hooks into settings, rewriting paths to use the cache location."""
    if not plugin_hooks:
        return settings

    settings_hooks = settings.get("hooks", {})
    tag = make_hook_tag(plugin_name)

    for event_name, hook_entries in plugin_hooks.items():
        if event_name not in settings_hooks:
            settings_hooks[event_name] = []

        for entry in hook_entries:
            # Rewrite hook commands to point at the installed cache location
            new_hooks = []
            for hook in entry.get("hooks", []):
                new_hook = dict(hook)
                if "command" in new_hook:
                    # Replace ${CLAUDE_PLUGIN_ROOT} with the actual cache path
                    new_hook["command"] = new_hook["command"].replace(
                        "${CLAUDE_PLUGIN_ROOT}", str(cache_dir)
                    )
                new_hook["_plugin"] = tag
                new_hooks.append(new_hook)

            new_entry = {
                "matcher": entry.get("matcher", ""),
                "hooks": new_hooks,
            }
            settings_hooks[event_name].append(new_entry)

    settings["hooks"] = settings_hooks
    return settings


def remove_hooks(settings: dict, plugin_name: str) -> dict:
    """Remove all hooks tagged with a specific plugin name."""
    tag = make_hook_tag(plugin_name)
    settings_hooks = settings.get("hooks", {})
    cleaned = {}

    for event_name, entries in settings_hooks.items():
        kept = []
        for entry in entries:
            hooks = entry.get("hooks", [])
            filtered = [h for h in hooks if h.get("_plugin") != tag]
            if filtered:
                entry["hooks"] = filtered
                kept.append(entry)
        if kept:
            cleaned[event_name] = kept

    if cleaned:
        settings["hooks"] = cleaned
    elif "hooks" in settings:
        del settings["hooks"]

    return settings


def add_enabled_plugin(settings: dict, plugin_name: str) -> dict:
    """Add plugin to enabledPlugins (supports both dict and list formats)."""
    enabled = settings.get("enabledPlugins", {})
    entry = f"{MARKETPLACE_NAME}/{plugin_name}"

    if isinstance(enabled, dict):
        enabled[entry] = True
    else:
        # Legacy list format
        if entry not in enabled:
            enabled.append(entry)

    settings["enabledPlugins"] = enabled
    return settings


def remove_enabled_plugin(settings: dict, plugin_name: str) -> dict:
    """Remove plugin from enabledPlugins (supports both dict and list formats)."""
    enabled = settings.get("enabledPlugins", {})
    entry = f"{MARKETPLACE_NAME}/{plugin_name}"

    if isinstance(enabled, dict):
        enabled.pop(entry, None)
    else:
        enabled = [e for e in enabled if e != entry]

    if not enabled:
        settings.pop("enabledPlugins", None)
    else:
        settings["enabledPlugins"] = enabled
    return settings


def merge_plugin_settings(settings: dict, plugin_settings: dict, plugin_name: str) -> dict:
    """Merge plugin-defined settings (attribution, env, etc.) into settings.json.

    Each merged key is tracked via a _plugin_settings metadata dict so
    uninstall can cleanly revert only settings that came from plugins.
    """
    tracker = settings.get("_plugin_settings", {})

    for key, value in plugin_settings.items():
        settings[key] = value
        # Track which plugin set this key
        tracker[key] = make_hook_tag(plugin_name)

    if tracker:
        settings["_plugin_settings"] = tracker
    return settings


def remove_plugin_settings(settings: dict, plugin_name: str) -> dict:
    """Remove settings that were added by a specific plugin."""
    tag = make_hook_tag(plugin_name)
    tracker = settings.get("_plugin_settings", {})

    keys_to_remove = [k for k, v in tracker.items() if v == tag]
    for key in keys_to_remove:
        settings.pop(key, None)
        del tracker[key]

    if not tracker:
        settings.pop("_plugin_settings", None)
    else:
        settings["_plugin_settings"] = tracker
    return settings


def install_plugin(name: str, global_scope: bool) -> None:
    """Install a plugin to the cache and register it in settings."""
    plugin_dir = get_plugin_dir(name)
    if not plugin_dir.is_dir():
        print(f"Error: Plugin '{name}' not found in {PLUGINS_DIR}", file=sys.stderr)
        sys.exit(1)

    manifest = load_plugin_json(plugin_dir)
    cache_dir = get_cache_dir(name, global_scope)
    settings_path = get_settings_path(global_scope)
    scope_label = "global" if global_scope else "project"

    # Copy plugin files to cache
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(plugin_dir, cache_dir)

    # Load and merge hooks
    plugin_hooks = load_hooks(plugin_dir)
    settings = load_settings(settings_path)

    # Remove old hooks from this plugin first (idempotent reinstall)
    settings = remove_hooks(settings, name)
    settings = merge_hooks(settings, plugin_hooks, name, cache_dir)
    settings = add_enabled_plugin(settings, name)

    # Merge plugin settings (attribution, env, etc.) from manifest
    plugin_settings = manifest.get("settings", {})
    if plugin_settings:
        settings = merge_plugin_settings(settings, plugin_settings, name)

    save_settings(settings_path, settings)

    print(f"Installed {name}@{manifest['version']} ({scope_label})")
    print(f"  Cache:    {cache_dir}")
    print(f"  Settings: {settings_path}")
    if plugin_hooks:
        print(f"  Hooks:    {', '.join(plugin_hooks.keys())}")
    if plugin_settings:
        print(f"  Settings: {', '.join(plugin_settings.keys())}")


def uninstall_plugin(name: str, global_scope: bool) -> None:
    """Remove a plugin from cache and settings."""
    cache_dir = get_cache_dir(name, global_scope)
    settings_path = get_settings_path(global_scope)
    scope_label = "global" if global_scope else "project"

    # Remove cached files
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
        # Clean up empty parent dirs
        parent = cache_dir.parent
        while parent != parent.parent:
            try:
                parent.rmdir()  # only removes if empty
                parent = parent.parent
            except OSError:
                break

    # Remove hooks, plugin settings, and enabled entry from settings
    settings = load_settings(settings_path)
    settings = remove_hooks(settings, name)
    settings = remove_plugin_settings(settings, name)
    settings = remove_enabled_plugin(settings, name)
    save_settings(settings_path, settings)

    print(f"Uninstalled {name} ({scope_label})")


def list_plugins() -> None:
    """List all available plugins with their versions."""
    if not PLUGINS_DIR.is_dir():
        print("No plugins directory found.", file=sys.stderr)
        sys.exit(1)

    plugins = sorted(
        d for d in PLUGINS_DIR.iterdir()
        if d.is_dir() and (d / ".claude-plugin" / "plugin.json").exists()
    )

    if not plugins:
        print("No plugins found.")
        return

    print(f"Available plugins ({len(plugins)}):\n")
    for plugin_dir in plugins:
        manifest = load_plugin_json(plugin_dir)
        name = manifest.get("name", plugin_dir.name)
        version = manifest.get("version", "?")
        desc = manifest.get("description", "")
        # Truncate long descriptions
        if len(desc) > 70:
            desc = desc[:67] + "..."
        print(f"  {name:<12} v{version}  {desc}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install or uninstall agentic-primitives plugins"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # install
    p_install = sub.add_parser("install", help="Install a plugin")
    p_install.add_argument("name", help="Plugin name (e.g. sdlc, workspace)")
    p_install.add_argument(
        "--global", dest="global_scope", action="store_true",
        help="Install globally (~/.claude/) instead of project-local"
    )

    # uninstall
    p_uninstall = sub.add_parser("uninstall", help="Uninstall a plugin")
    p_uninstall.add_argument("name", help="Plugin name")
    p_uninstall.add_argument(
        "--global", dest="global_scope", action="store_true",
        help="Uninstall from global scope"
    )

    # list
    sub.add_parser("list", help="List available plugins")

    args = parser.parse_args()

    if args.command == "install":
        install_plugin(args.name, args.global_scope)
    elif args.command == "uninstall":
        uninstall_plugin(args.name, args.global_scope)
    elif args.command == "list":
        list_plugins()


if __name__ == "__main__":
    main()
