#!/usr/bin/env python3
"""Cross-platform Python QA runner for all packages.

Usage:
    python scripts/python_qa.py lint
    python scripts/python_qa.py lint --fix
    python scripts/python_qa.py test
    python scripts/python_qa.py test --integration
    python scripts/python_qa.py check  # lint + test
    python scripts/python_qa.py lock  # fail if any uv.lock is stale
    python scripts/python_qa.py lock --update  # regenerate stale locks
"""

import argparse
import subprocess
import sys
from pathlib import Path

# All Python packages to check.
#
# This list and the `python-packages` matrix in .github/workflows/qa.yml are the
# same list written twice, so they drift: this one was missing agentic_memory
# and agentic_session_store while CI checked both, which means `just qa` passing
# locally said less than a developer would reasonably assume. Keep them in step
# until one derives from the other (see issue #300 for that argument applied to
# a different pair of duplicated values).
PACKAGES = [
    Path("lib/python/agentic_events"),
    Path("lib/python/agentic_isolation"),
    Path("lib/python/agentic_logging"),
    Path("lib/python/agentic_memory"),
    Path("lib/python/agentic_session_store"),
]

# Additional test directories (not packages)
TEST_DIRS = [
    Path("tests/unit/claude/hooks"),
    Path("tests/consumer_contracts"),
]

# Every directory with its own pyproject.toml + uv.lock pair. CI installs each
# of these with `uv sync --locked`, so a stale lock here is a CI failure.
UV_PROJECTS = PACKAGES + TEST_DIRS


def run_cmd(cmd: list[str], cwd: Path) -> bool:
    """Run command and return success status."""
    print(f"\n{'='*60}")
    print(f"📁 {cwd}")
    print(f"🔧 {' '.join(cmd)}")
    print("=" * 60)

    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode == 0


def lint(fix: bool = False) -> bool:
    """Lint all packages."""
    print("\n🔍 Linting Python code...")
    all_passed = True

    for pkg in PACKAGES:
        if not pkg.exists():
            print(f"⚠️  Skipping {pkg} (not found)")
            continue

        if fix:
            # Fix and format
            if not run_cmd(["uv", "run", "ruff", "check", "--fix", "."], pkg):
                all_passed = False
            run_cmd(["uv", "run", "ruff", "format", "."], pkg)
        else:
            # Check only
            if not run_cmd(["uv", "run", "ruff", "check", "."], pkg):
                all_passed = False

    return all_passed


def test(integration: bool = False) -> bool:
    """Test all packages."""
    print("\n🧪 Running Python tests...")
    all_passed = True

    for pkg in PACKAGES:
        if not pkg.exists():
            print(f"⚠️  Skipping {pkg} (not found)")
            continue

        # Skip integration tests by default for agentic_isolation
        if pkg.name == "agentic_isolation" and not integration:
            cmd = ["uv", "run", "pytest", "-x", "-q", "--ignore=tests/integration"]
        else:
            cmd = ["uv", "run", "pytest", "-x", "-q"]

        if not run_cmd(cmd, pkg):
            all_passed = False

    # Run additional test directories
    for test_dir in TEST_DIRS:
        if not test_dir.exists():
            print(f"⚠️  Skipping {test_dir} (not found)")
            continue

        if not run_cmd(["uv", "run", "pytest", "-x", "-q"], test_dir):
            all_passed = False

    return all_passed


def sync() -> bool:
    """Sync all package dependencies (required before testing)."""
    print("\n📦 Syncing Python package dependencies...")
    all_passed = True

    for pkg in PACKAGES:
        if not pkg.exists():
            print(f"⚠️  Skipping {pkg} (not found)")
            continue

        # --locked mirrors CI: a stale lock fails loudly instead of silently
        # re-resolving to a different dependency set than CI installs.
        if not run_cmd(["uv", "sync", "--locked", "--all-extras"], pkg):
            all_passed = False

    return all_passed


def lock(update: bool = False) -> bool:
    """Check that every uv.lock is current, or regenerate them with --update."""
    action = "Regenerating" if update else "Checking"
    print(f"\n🔒 {action} uv lockfiles...")
    all_passed = True
    stale: list[Path] = []

    for project in UV_PROJECTS:
        if not project.exists():
            print(f"⚠️  Skipping {project} (not found)")
            continue

        cmd = ["uv", "lock"] if update else ["uv", "lock", "--check"]
        if not run_cmd(cmd, project):
            all_passed = False
            stale.append(project)

    if stale:
        print("\n❌ Lockfiles out of date with their pyproject.toml:")
        for project in stale:
            print(f"   - {project}/uv.lock")
        print("\nRun `just python-lock-update` and commit the result.")
        print("CI installs with `uv sync --locked`, so a stale lock fails the build.")

    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Python QA runner")
    parser.add_argument(
        "command",
        choices=["lint", "test", "check", "sync", "lock"],
        help="Command to run",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix lint issues",
    )
    parser.add_argument(
        "--integration",
        action="store_true",
        help="Include integration tests",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Regenerate lockfiles instead of only checking them",
    )
    args = parser.parse_args()

    success = True

    if args.command == "sync":
        success = sync()
    elif args.command == "lock":
        success = lock(update=args.update)
    elif args.command == "lint":
        success = lint(fix=args.fix)
    elif args.command == "test":
        success = test(integration=args.integration)
    elif args.command == "check":
        success = lint(fix=args.fix) and test(integration=args.integration)

    if success:
        print("\n✅ All checks passed!")
        return 0
    else:
        print("\n❌ Some checks failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
