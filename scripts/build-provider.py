#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""
Build Provider Workspace Image

Stages all required files and builds a Docker image for a workspace provider.

Usage:
    uv run scripts/build-provider.py claude-cli
    uv run scripts/build-provider.py claude-cli --tag my-custom-tag
    uv run scripts/build-provider.py claude-cli --no-cache

The build process:
1. Reads manifest.yaml from providers/workspaces/<provider>/
2. Creates staged build context in build/<provider>/
3. Copies Dockerfile, plugins, and builds Python wheels
4. Runs docker build with the staged context

See ADR-027: Provider-Based Workspace Images
See ADR-033: Plugin-Native Workspace Images
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

# Paths relative to agentic-primitives root
ROOT = Path(__file__).parent.parent
PROVIDERS_DIR = ROOT / "providers" / "workspaces"
PLUGINS_DIR = ROOT / "plugins"
PYTHON_PACKAGES_DIR = ROOT / "lib" / "python"
BUILD_DIR = ROOT / "build"


def load_manifest(provider: str) -> dict:
    """Load and validate provider manifest."""
    manifest_path = PROVIDERS_DIR / provider / "manifest.yaml"
    if not manifest_path.exists():
        print(f"❌ Provider manifest not found: {manifest_path}")
        sys.exit(1)

    with manifest_path.open() as f:
        return yaml.safe_load(f)


def stage_dockerfile(provider: str, build_context: Path) -> None:
    """Copy Dockerfile to build context."""
    src = PROVIDERS_DIR / provider / "Dockerfile"
    dst = build_context / "Dockerfile"
    shutil.copy2(src, dst)
    print("  ✓ Dockerfile")


def stage_plugins(manifest: dict, build_context: Path) -> None:
    """Copy plugin directories to build context (ADR-033).

    Each plugin is a self-contained directory with .claude-plugin/plugin.json.
    The entire directory tree is copied to preserve hooks, commands, skills, etc.
    """
    plugins_config = manifest.get("plugins", {})
    plugin_names = plugins_config.get("include", [])

    if not plugin_names:
        print("  ⊘ No plugins configured")
        return

    plugins_dst = build_context / "plugins"
    plugins_dst.mkdir(parents=True, exist_ok=True)

    for plugin_name in plugin_names:
        src = PLUGINS_DIR / plugin_name
        if not src.exists():
            print(f"  ⚠ Plugin not found: {plugin_name}")
            continue

        # Validate plugin has required manifest
        manifest_file = src / ".claude-plugin" / "plugin.json"
        if not manifest_file.exists():
            print(f"  ⚠ Plugin missing .claude-plugin/plugin.json: {plugin_name}")
            continue

        # Copy entire plugin directory
        dst = plugins_dst / plugin_name
        shutil.copytree(src, dst)
        print(f"  ✓ Plugin: {plugin_name}")


def stage_scripts(provider: str, build_context: Path) -> None:
    """Copy scripts directory (e.g., entrypoint.sh) to build context."""
    scripts_src = PROVIDERS_DIR / provider / "scripts"
    if not scripts_src.exists():
        return  # No scripts directory

    scripts_dst = build_context / "scripts"
    scripts_dst.mkdir(parents=True, exist_ok=True)

    for script in scripts_src.iterdir():
        if script.is_file():
            shutil.copy2(script, scripts_dst / script.name)
            print(f"  ✓ Script: {script.name}")


def build_wheels(build_context: Path) -> None:
    """Build wheels for agentic packages."""
    packages_dir = build_context / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)

    # Packages to include in the image
    # agentic_events is the core observability package used by plugin hooks
    required_packages = ["agentic_events"]

    for pkg_name in required_packages:
        pkg_path = PYTHON_PACKAGES_DIR / pkg_name
        if not pkg_path.exists():
            print(f"  ⚠ Package not found: {pkg_name}")
            continue

        print(f"  ⏳ Building wheel: {pkg_name}")
        result = subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(packages_dir)],
            cwd=pkg_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"  ❌ Failed to build {pkg_name}: {result.stderr}")
        else:
            print(f"  ✓ Built: {pkg_name}")


def get_git_commit() -> str:
    """Get the current git commit hash."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()[:12]  # Short hash
    return "unknown"


def docker_build(
    build_context: Path,
    tag: str,
    no_cache: bool = False,
) -> None:
    """Run docker build with commit label for cache invalidation."""
    commit = get_git_commit()
    cmd = ["docker", "build", "-t", tag, "--label", f"agentic.commit={commit}", "."]
    if no_cache:
        cmd.insert(2, "--no-cache")

    print(f"\n🐳 Building Docker image: {tag}")
    print(f"   Context: {build_context}")
    print(f"   Commit: {commit}")

    result = subprocess.run(cmd, cwd=build_context)

    if result.returncode != 0:
        print("\n❌ Docker build failed")
        sys.exit(1)

    print(f"\n✅ Successfully built: {tag}")


def main():
    parser = argparse.ArgumentParser(description="Build workspace provider image")
    parser.add_argument("provider", help="Provider name (e.g., claude-cli)")
    parser.add_argument("--tag", help="Custom image tag")
    parser.add_argument("--no-cache", action="store_true", help="Build without cache")
    parser.add_argument("--stage-only", action="store_true", help="Only stage files, don't build")
    args = parser.parse_args()

    provider = args.provider

    # Load manifest
    print(f"\n📦 Building provider: {provider}")
    manifest = load_manifest(provider)
    print(f"   Version: {manifest.get('version', 'unknown')}")

    # Determine tag
    default_tag = manifest.get("image", {}).get("tag", f"agentic-workspace-{provider}")
    tag = args.tag or f"{default_tag}:latest"

    # Create build context
    build_context = BUILD_DIR / provider
    if build_context.exists():
        shutil.rmtree(build_context)
    build_context.mkdir(parents=True)

    print(f"\n📁 Staging build context: {build_context}")

    # Stage files
    stage_dockerfile(provider, build_context)
    stage_scripts(provider, build_context)
    stage_plugins(manifest, build_context)
    build_wheels(build_context)

    if args.stage_only:
        print(f"\n✅ Staged to: {build_context}")
        return

    # Build image
    docker_build(build_context, tag, args.no_cache)


if __name__ == "__main__":
    main()
