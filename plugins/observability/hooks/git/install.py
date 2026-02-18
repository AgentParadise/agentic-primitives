#!/usr/bin/env python3
"""Install git hooks for observability.

Cross-platform installer that copies hook scripts into the repo's
.git/hooks/ directory (or globally with --global).

Usage:
    python install.py              # Install to current repo
    python install.py --global     # Install globally for all repos
    python install.py --uninstall  # Remove installed hooks
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOOKS = ["post-commit", "post-merge", "post-rewrite", "pre-push"]
MARKER = "agentic_events"  # Marker to identify our hooks


def get_script_dir() -> Path:
    return Path(__file__).parent.resolve()


def get_git_dir() -> Path | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True, text=True, check=True,
        )
        return Path(r.stdout.strip()).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_global_hooks_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    return Path(xdg) / "git" / "hooks"


def is_our_hook(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return MARKER in path.read_text()
    except (OSError, UnicodeDecodeError):
        return False


def install_hooks(target_dir: Path, script_dir: Path) -> bool:
    print(f"Installing hooks to {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)
    success = True

    for hook in HOOKS:
        src = script_dir / hook
        dst = target_dir / hook

        if not src.exists():
            print(f"  Warning: {src} not found, skipping")
            continue

        if dst.exists() and not dst.is_symlink() and not is_our_hook(dst):
            backup = dst.with_suffix(".bak")
            print(f"  Backing up existing {hook} to {hook}.bak")
            shutil.move(dst, backup)

        try:
            shutil.copy2(src, dst)
            if os.name != "nt":
                dst.chmod(dst.stat().st_mode | 0o111)
            print(f"  Installed {hook}")
        except OSError as e:
            print(f"  Error installing {hook}: {e}")
            success = False

    if success:
        print("Done! Git hooks installed.")
        print("Events will be emitted to stderr via agentic_events.")
    return success


def uninstall_hooks(target_dir: Path) -> bool:
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
        if backup.exists():
            shutil.move(backup, dst)
            print(f"  Restored {hook} from backup")
    print("Done!")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Install observability git hooks")
    parser.add_argument("--global", dest="global_install", action="store_true",
                        help="Install hooks globally (all repos)")
    parser.add_argument("--uninstall", action="store_true",
                        help="Remove installed hooks")
    args = parser.parse_args()
    script_dir = get_script_dir()

    if args.global_install:
        target_dir = get_global_hooks_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        if args.uninstall:
            ok = uninstall_hooks(target_dir)
            if ok:
                subprocess.run(["git", "config", "--global", "--unset", "core.hooksPath"], check=False)
            return 0 if ok else 1
        else:
            ok = install_hooks(target_dir, script_dir)
            if ok:
                subprocess.run(["git", "config", "--global", "core.hooksPath", str(target_dir)], check=True)
            return 0 if ok else 1
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
