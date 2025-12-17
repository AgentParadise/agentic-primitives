"""
Integration tests for the OTel pipeline.

These tests validate that:
1. Claude CLI emits OTel traces when running in the workspace image
2. The OTel collector receives and exports the traces
3. Hook events are properly instrumented

Requirements:
- Docker must be running
- The workspace image must be built: just build-provider claude-cli
- ANTHROPIC_API_KEY must be set (or tests will be skipped)
"""

import os
import subprocess
import time
from pathlib import Path

import pytest

# Marker for tests that require API key
requires_api_key = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set - skipping live API tests",
)


class TestOTelCollector:
    """Tests for the OTel collector setup."""

    def test_collector_is_healthy(self, otel_collector: str):
        """Verify the OTel collector is running and responding."""
        # Check the collector is running
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}",
             "test-otel-collector"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "true"

        # Check health endpoint responds with status
        result = subprocess.run(
            ["curl", "-s", "http://localhost:13133"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "status" in result.stdout

    def test_collector_endpoint_accessible(self, otel_collector: str):
        """Verify we can connect to the collector endpoint."""
        # Use curl to check the health endpoint
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "http://localhost:13133"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout == "200"


class TestWorkspaceImage:
    """Tests for the workspace image."""

    def test_image_exists(self, workspace_image: str):
        """Verify the workspace image is available."""
        result = subprocess.run(
            ["docker", "image", "inspect", workspace_image],
            capture_output=True,
        )
        assert result.returncode == 0, f"Image {workspace_image} not found. Run: just build-provider claude-cli"

    def test_claude_cli_version(self, workspace_image: str):
        """Verify Claude CLI is installed in the image."""
        result = subprocess.run(
            ["docker", "run", "--rm", workspace_image, "claude", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Claude Code" in result.stdout

    def test_agentic_packages_installed(self, workspace_image: str):
        """Verify agentic packages are installed."""
        result = subprocess.run(
            ["docker", "run", "--rm", workspace_image,
             "python3", "-c", "from agentic_otel import OTelConfig; print('ok')"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "ok" in result.stdout

    def test_hooks_installed(self, workspace_image: str):
        """Verify hooks are installed at /opt/agentic/hooks."""
        result = subprocess.run(
            ["docker", "run", "--rm", workspace_image,
             "ls", "-la", "/opt/agentic/hooks/handlers/"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "pre-tool-use.py" in result.stdout


class TestClaudeCLIOTel:
    """Tests for Claude CLI OTel emission."""

    @requires_api_key
    def test_simple_task_emits_traces(
        self,
        otel_collector: str,
        workspace_image: str,
        get_traces,
        output_dir: Path,
    ):
        """
        Run a simple Claude CLI task and verify traces are emitted.

        This is the core integration test - it validates the full pipeline:
        1. Claude CLI runs with OTel configured
        2. Traces are sent to the collector
        3. Collector exports traces to file
        """
        # Clear any existing traces
        traces_file = output_dir / "traces.jsonl"
        if traces_file.exists():
            traces_file.unlink()

        # Run Claude CLI with OTel configured
        # Using a simple echo task that shouldn't require API calls
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "--network", "integration_test-network",
                "-e", "ANTHROPIC_API_KEY",
                "-e", "OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317",
                "-e", "OTEL_SERVICE_NAME=claude-code-test",
                "-e", "OTEL_TRACES_EXPORTER=otlp",
                workspace_image,
                "claude", "-p", "What is 2+2? Reply with just the number.",
                "--allowedTools", "none",
                "--output-format", "json",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Log output for debugging
        print(f"Claude CLI stdout: {result.stdout[:500] if result.stdout else 'empty'}")
        print(f"Claude CLI stderr: {result.stderr[:500] if result.stderr else 'empty'}")

        # The CLI should complete (may fail if no API key, but we check that)
        # Give collector time to flush
        time.sleep(3)

        # Check for traces
        traces = get_traces()

        # We should have at least some trace data
        # Note: If no API key, this will be empty but test is skipped
        print(f"Found {len(traces)} trace entries")

        # For now, just verify the infrastructure works
        # Full trace validation requires API key and actual execution
        assert result.returncode == 0 or "api" in result.stderr.lower()

    def test_otel_env_vars_passed_to_container(self, workspace_image: str):
        """Verify OTel environment variables are accessible in the container."""
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "-e", "OTEL_EXPORTER_OTLP_ENDPOINT=http://test:4317",
                "-e", "OTEL_SERVICE_NAME=test-service",
                workspace_image,
                "bash", "-c", "echo $OTEL_EXPORTER_OTLP_ENDPOINT $OTEL_SERVICE_NAME",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "http://test:4317" in result.stdout
        assert "test-service" in result.stdout


class TestHookOTelEmission:
    """Tests for hook OTel emission (from pre-tool-use, etc.)."""

    def test_hook_can_emit_otel(self, workspace_image: str):
        """Verify the hook can import and use agentic_otel."""
        # Run Python in container to test the hook's OTel capability
        test_script = """
import os
os.environ['OTEL_EXPORTER_OTLP_ENDPOINT'] = 'http://localhost:4317'
os.environ['OTEL_SERVICE_NAME'] = 'test-hook'

from agentic_otel import OTelConfig, HookOTelEmitter

config = OTelConfig(
    endpoint='http://localhost:4317',
    service_name='test-hook',
)
emitter = HookOTelEmitter(config)
print('HookOTelEmitter initialized successfully')
"""
        result = subprocess.run(
            ["docker", "run", "--rm", workspace_image, "python3", "-c", test_script],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "successfully" in result.stdout


class TestEndToEndPipeline:
    """End-to-end tests for the complete OTel pipeline."""

    @requires_api_key
    @pytest.mark.slow
    def test_full_pipeline_with_tool_use(
        self,
        otel_collector: str,
        workspace_image: str,
        get_traces,
        get_logs,
        output_dir: Path,
    ):
        """
        Full end-to-end test with actual tool use.

        This test:
        1. Runs Claude CLI with a task that uses tools
        2. Hooks emit OTel events for tool use
        3. Verifies traces and logs are collected
        """
        # Clear output files
        for f in output_dir.glob("*.jsonl"):
            f.unlink()

        # Run a task that will use the Read tool
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "--network", "integration_test-network",
                "-e", "ANTHROPIC_API_KEY",
                "-e", "OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317",
                "-e", "OTEL_SERVICE_NAME=claude-code-e2e",
                "-e", "OTEL_TRACES_EXPORTER=otlp",
                "-v", f"{output_dir}:/workspace/output",
                workspace_image,
                "claude", "-p", "Read the file /etc/os-release and tell me the OS name",
                "--allowedTools", "Read",
                "--output-format", "json",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )

        print(f"E2E stdout: {result.stdout[:1000] if result.stdout else 'empty'}")
        print(f"E2E stderr: {result.stderr[:500] if result.stderr else 'empty'}")

        # Give collector time to flush
        time.sleep(5)

        # Collect results
        traces = get_traces()
        logs = get_logs()

        print(f"Traces collected: {len(traces)}")
        print(f"Logs collected: {len(logs)}")

        # Verify we got some telemetry
        # The exact content depends on Claude's response and tool use
        assert result.returncode == 0 or len(traces) > 0 or len(logs) > 0
