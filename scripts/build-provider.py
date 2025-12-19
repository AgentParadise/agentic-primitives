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
3. Copies Dockerfile, hooks, and builds Python wheels
4. Runs docker build with the staged context

See ADR-027: Provider-Based Workspace Images
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
PRIMITIVES_DIR = ROOT / "primitives" / "v1" / "hooks"
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


def stage_hooks(manifest: dict, build_context: Path) -> None:
    """Copy hook handlers and validators to build context."""
    hooks_config = manifest.get("hooks", {})
    if not hooks_config.get("handlers"):
        print("  ⊘ No hooks configured")
        return

    hooks_dir = build_context / "hooks"
    handlers_dir = hooks_dir / "handlers"
    validators_dir = hooks_dir / "validators"
    handlers_dir.mkdir(parents=True, exist_ok=True)
    validators_dir.mkdir(parents=True, exist_ok=True)

    # Copy handlers
    for handler in hooks_config.get("handlers", []):
        src = PRIMITIVES_DIR / "handlers" / f"{handler}.py"
        if src.exists():
            shutil.copy2(src, handlers_dir / f"{handler}.py")
            print(f"  ✓ Handler: {handler}")
        else:
            print(f"  ⚠ Handler not found: {handler}")

    # Copy validators
    for validator in hooks_config.get("validators", []):
        # Validator format: "security/bash" -> validators/security/bash.py
        parts = validator.split("/")
        if len(parts) == 2:
            category, name = parts
            src = PRIMITIVES_DIR / "validators" / category / f"{name}.py"
            dst_dir = validators_dir / category
            dst_dir.mkdir(parents=True, exist_ok=True)

            if src.exists():
                shutil.copy2(src, dst_dir / f"{name}.py")
                print(f"  ✓ Validator: {validator}")
            else:
                print(f"  ⚠ Validator not found: {validator}")

            # Copy __init__.py if exists
            init_src = PRIMITIVES_DIR / "validators" / category / "__init__.py"
            if init_src.exists():
                shutil.copy2(init_src, dst_dir / "__init__.py")


def build_wheels(build_context: Path) -> None:
    """Build wheels for agentic packages."""
    packages_dir = build_context / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)

    # Packages to include in the image
    required_packages = ["agentic_events", "agentic_security"]

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


def docker_build(
    build_context: Path,
    tag: str,
    no_cache: bool = False,
) -> None:
    """Run docker build."""
    cmd = ["docker", "build", "-t", tag, "."]
    if no_cache:
        cmd.insert(2, "--no-cache")

    print(f"\n🐳 Building Docker image: {tag}")
    print(f"   Context: {build_context}")

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
    stage_hooks(manifest, build_context)
    build_wheels(build_context)

    if args.stage_only:
        print(f"\n✅ Staged to: {build_context}")
        return

    # Build image
    docker_build(build_context, tag, args.no_cache)


if __name__ == "__main__":
    main()
