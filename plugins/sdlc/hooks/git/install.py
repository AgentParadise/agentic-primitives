#!/usr/bin/env python3
"""Install git hooks for observability.

Cross-platform installer for git observability hooks that emit JSONL events.

Usage:
    python install.py          # Install to current repo
    python install.py --global # Install globally for all repos
    python install.py --uninstall # Remove installed hooks
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOOKS = ["post-commit", "post-checkout", "post-merge", "post-rewrite", "pre-push"]
MARKER = "ANALYTICS_PATH"  # Marker to identify our hooks


def get_script_dir() -> Path:
    """Get the directory containing this script."""
    return Path(__file__).parent.resolve()


def get_git_dir() -> Path | None:
    """Get the .git directory for the current repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip()).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_global_hooks_dir() -> Path:
    """Get the global git hooks directory."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    return Path(xdg_config) / "git" / "hooks"


def is_our_hook(hook_path: Path) -> bool:
    """Check if a hook file is one we installed."""
    if not hook_path.exists():
        return False
    try:
        content = hook_path.read_text()
        return MARKER in content
    except (OSError, UnicodeDecodeError):
        return False


def install_hooks(target_dir: Path, script_dir: Path) -> bool:
    """Install hooks to target directory.

    Args:
        target_dir: Directory to install hooks to
        script_dir: Directory containing hook scripts

    Returns:
        True if successful, False otherwise
    """
    print(f"Installing hooks to {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)

    success = True
    for hook in HOOKS:
        src = script_dir / hook
        dst = target_dir / hook

        if not src.exists():
            print(f"  Warning: {src} not found, skipping")
            continue

        # Backup existing hook if it's not ours
        if dst.exists() and not dst.is_symlink() and not is_our_hook(dst):
            backup = dst.with_suffix(".bak")
            print(f"  Backing up existing {hook} to {hook}.bak")
            shutil.move(dst, backup)

        try:
            shutil.copy2(src, dst)
            # Make executable on Unix-like systems
            if os.name != "nt":
                dst.chmod(dst.stat().st_mode | 0o111)
            print(f"  Installed {hook}")
        except OSError as e:
            print(f"  Error installing {hook}: {e}")
            success = False

    if success:
        print("Done! Git hooks installed.")
        print()
        print(
            "Events will be written to: $ANALYTICS_PATH or .agentic/analytics/events.jsonl"
        )

    return success


def uninstall_hooks(target_dir: Path) -> bool:
    """Remove installed hooks from target directory.

    Args:
        target_dir: Directory to remove hooks from

    Returns:
        True if successful, False otherwise
    """
    print(f"Uninstalling hooks from {target_dir}")

    for hook in HOOKS:
        dst = target_dir / hook
        backup = dst.with_suffix(".bak")

        if dst.exists():
            if is_our_hook(dst):
                dst.unlink()
                print(f"  Removed {hook}")
            else:
                print(f"  Skipped {hook} (not our hook)")

        # Restore backup if exists
        if backup.exists():
            shutil.move(backup, dst)
            print(f"  Restored {hook} from backup")

    print("Done!")
    return True


def configure_global_hooks_path(hooks_dir: Path) -> bool:
    """Configure git to use global hooks directory.

    Args:
        hooks_dir: Path to set as global hooks directory

    Returns:
        True if successful, False otherwise
    """
    try:
        subprocess.run(
            ["git", "config", "--global", "core.hooksPath", str(hooks_dir)],
            check=True,
        )
        print(f"Configured global hooks path: {hooks_dir}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Error configuring global hooks: {e}")
        return False


def clear_global_hooks_path() -> bool:
    """Remove global hooks path configuration.

    Returns:
        True if successful, False otherwise
    """
    try:
        subprocess.run(
            ["git", "config", "--global", "--unset", "core.hooksPath"],
            check=False,  # Don't fail if not set
        )
        print("Removed global hooks path configuration")
        return True
    except FileNotFoundError:
        print("Git not found")
        return False


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Install git observability hooks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Hooks installed:
  post-commit     - Track commits with token metrics
  post-checkout   - Track branch switches and creation
  post-merge      - Track merges, especially to stable branches
  post-rewrite    - Track rebases and amends
  pre-push        - Track push operations

Events are written to: $ANALYTICS_PATH or .agentic/analytics/events.jsonl
""",
    )
    parser.add_argument(
        "--global",
        dest="global_install",
        action="store_true",
        help="Install hooks globally (all repos)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove installed hooks",
    )

    args = parser.parse_args()
    script_dir = get_script_dir()

    if args.global_install:
        target_dir = get_global_hooks_dir()
        target_dir.mkdir(parents=True, exist_ok=True)

        if args.uninstall:
            success = uninstall_hooks(target_dir)
            if success:
                clear_global_hooks_path()
            return 0 if success else 1
        else:
            success = install_hooks(target_dir, script_dir)
            if success:
                configure_global_hooks_path(target_dir)
            return 0 if success else 1
    else:
        git_dir = get_git_dir()
        if git_dir is None:
            print("Error: Not in a git repository")
            return 1

        target_dir = git_dir / "hooks"

        if args.uninstall:
            return 0 if uninstall_hooks(target_dir) else 1
        else:
            return 0 if install_hooks(target_dir, script_dir) else 1


if __name__ == "__main__":
    sys.exit(main())
