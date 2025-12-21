"""
Pytest fixtures for OTel integration testing.

These fixtures manage the Docker infrastructure needed for testing:
- OTel Collector (receives traces/metrics/logs)
- Workspace containers (runs Claude CLI)
"""

import contextlib
import json
import os
import subprocess
import time
from collections.abc import Generator
from pathlib import Path

import pytest

# Test directory
TEST_DIR = Path(__file__).parent
OUTPUT_DIR = TEST_DIR / "output"
COMPOSE_FILE = TEST_DIR / "docker-compose.yaml"

# Workspace image
WORKSPACE_IMAGE = os.getenv("AGENTIC_WORKSPACE_IMAGE", "agentic-workspace-claude-cli:latest")


@pytest.fixture(scope="session")
def otel_collector() -> Generator[str, None, None]:
    """
    Start the OTel collector for the test session.

    Yields the collector endpoint URL.
    """
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Stop any existing collector and clean output files
    # This ensures file handles are fresh when files are created
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "down", "-v"],
        capture_output=True,
    )

    # Clean output files after stopping collector
    for f in OUTPUT_DIR.glob("*.jsonl"):
        f.unlink()

    # Start the collector (don't use --wait, it's flaky with health checks)
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"],
        check=True,
        capture_output=True,
    )

    # Wait for the health endpoint to respond (more reliable than Docker health check)
    max_retries = 30
    endpoint_ready = False
    for _ in range(max_retries):
        try:
            result = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://localhost:13133"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout == "200":
                endpoint_ready = True
                break
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass  # Retry until health endpoint responds
        time.sleep(1)

    if not endpoint_ready:
        pytest.fail("OTel collector health endpoint not responding")

    yield "http://localhost:4317"

    # Don't cleanup in fixture - let the user control this
    # (avoids issues when running tests multiple times)
    # subprocess.run(
    #     ["docker", "compose", "-f", str(COMPOSE_FILE), "down", "-v"],
    #     capture_output=True,
    # )


@pytest.fixture
def output_dir() -> Path:
    """Return the output directory for OTel exports."""
    return OUTPUT_DIR


@pytest.fixture
def workspace_image() -> str:
    """Return the workspace image name."""
    return WORKSPACE_IMAGE


def read_jsonl_file(path: Path) -> list[dict]:
    """Read a JSONL file and return list of parsed objects."""
    if not path.exists():
        return []

    results = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                with contextlib.suppress(json.JSONDecodeError):
                    results.append(json.loads(line))
    return results


@pytest.fixture
def get_traces(output_dir: Path):
    """Factory fixture to get traces from the output file."""

    def _get_traces() -> list[dict]:
        return read_jsonl_file(output_dir / "traces.jsonl")

    return _get_traces


@pytest.fixture
def get_metrics(output_dir: Path):
    """Factory fixture to get metrics from the output file."""

    def _get_metrics() -> list[dict]:
        return read_jsonl_file(output_dir / "metrics.jsonl")

    return _get_metrics


@pytest.fixture
def get_logs(output_dir: Path):
    """Factory fixture to get logs from the output file."""

    def _get_logs() -> list[dict]:
        return read_jsonl_file(output_dir / "logs.jsonl")

    return _get_logs
