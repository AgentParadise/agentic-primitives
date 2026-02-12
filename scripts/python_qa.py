#!/usr/bin/env python3
"""Cross-platform Python QA runner for all packages.

Usage:
    python scripts/python_qa.py lint
    python scripts/python_qa.py lint --fix
    python scripts/python_qa.py test
    python scripts/python_qa.py test --integration
    python scripts/python_qa.py check  # lint + test
"""

import argparse
import subprocess
import sys
from pathlib import Path

# All Python packages to check
PACKAGES = [
    Path("lib/python/agentic_adapters"),
    Path("lib/python/agentic_events"),
    Path("lib/python/agentic_isolation"),
    Path("lib/python/agentic_logging"),
    Path("lib/python/agentic_security"),
    Path("lib/python/agentic_settings"),
]

# Additional test directories (not packages)
TEST_DIRS = [
    Path("tests/unit/claude/hooks"),
]


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

        if not run_cmd(["uv", "sync", "--all-extras"], pkg):
            all_passed = False

    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Python QA runner")
    parser.add_argument(
        "command",
        choices=["lint", "test", "check", "sync"],
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
    args = parser.parse_args()

    success = True

    if args.command == "sync":
        success = sync()
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
