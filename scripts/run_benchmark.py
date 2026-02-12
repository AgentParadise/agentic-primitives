#!/usr/bin/env python3
"""Run a benchmark recording via Docker Compose.

Usage:
    python scripts/run_benchmark.py <benchmark-name>
    python scripts/run_benchmark.py context-window-growth
    python scripts/run_benchmark.py multi-model-usage

See providers/workspaces/claude-cli/fixtures/benchmarks.yaml for available benchmarks.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml")
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_FILE = REPO_ROOT / "providers/workspaces/claude-cli/fixtures/benchmarks.yaml"
COMPOSE_DIR = REPO_ROOT / "providers/workspaces/claude-cli"


def load_benchmarks() -> dict:
    """Load benchmarks from YAML file."""
    if not BENCHMARKS_FILE.exists():
        print(f"Error: Benchmarks file not found: {BENCHMARKS_FILE}")
        sys.exit(1)
    with open(BENCHMARKS_FILE) as f:
        data = yaml.safe_load(f)
    return data.get("benchmarks", {})


def list_benchmarks(benchmarks: dict) -> None:
    """Print available benchmark names."""
    print("Available benchmarks:")
    for name in benchmarks:
        print(f"  {name}")


def find_api_key() -> str | None:
    """Find ANTHROPIC_API_KEY from environment or .env files."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key

    for env_path in [REPO_ROOT / ".env", REPO_ROOT / "../../.env"]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY=") and not line.startswith("#"):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <benchmark-name>")
        print()
        list_benchmarks(load_benchmarks())
        return 1

    benchmark_name = sys.argv[1]
    benchmarks = load_benchmarks()

    if benchmark_name not in benchmarks:
        print(f"Error: Benchmark '{benchmark_name}' not found")
        print()
        list_benchmarks(benchmarks)
        return 1

    benchmark = benchmarks[benchmark_name]
    prompt = benchmark.get("prompt", "")
    description = benchmark.get("description", "")
    expected_cost = benchmark.get("expected_cost", "unknown")

    print("=" * 64)
    print(f"  Running Benchmark: {benchmark_name}")
    print("-" * 64)
    print(f"  Description: {description}")
    print(f"  Expected cost: ~${expected_cost}")
    print("=" * 64)
    print()
    input("Press Enter to continue or Ctrl+C to cancel...")

    api_key = find_api_key()
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set")
        print("Set it in environment or create .env file")
        return 1

    print("Starting recording...")
    env = {
        **os.environ,
        "TASK": benchmark_name,
        "PROMPT": prompt,
        "ANTHROPIC_API_KEY": api_key,
    }

    result = subprocess.run(
        ["docker", "compose", "-f", "docker-compose.record.yaml", "up"],
        cwd=COMPOSE_DIR,
        env=env,
    )

    print()
    print(f"Recording complete! Check fixtures/recordings/{benchmark_name}/")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
