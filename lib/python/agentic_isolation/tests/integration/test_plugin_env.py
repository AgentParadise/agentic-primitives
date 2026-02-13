"""Integration tests for plugin env var forwarding (ADR-033).

Validates that requires_env declared in plugin.json gets auto-forwarded
into Docker containers via resolve_plugin_env().

These tests require:
- Docker installed and running
- FIRECRAWL_API_KEY set in the environment

Run with: pytest tests/integration/test_plugin_env.py -v
"""

import os
from pathlib import Path

import pytest

from agentic_isolation import (
    AgenticWorkspace,
    SecurityConfig,
    WorkspaceConfig,
    WorkspaceDockerProvider,
)

# Path to the research plugin (has requires_env with FIRECRAWL_API_KEY)
RESEARCH_PLUGIN = Path(__file__).parent.parent.parent.parent.parent.parent / "plugins" / "research"


def docker_available() -> bool:
    """Check if Docker is available."""
    return WorkspaceDockerProvider.is_available()


def firecrawl_key_available() -> bool:
    """Check if FIRECRAWL_API_KEY is set."""
    return bool(os.environ.get("FIRECRAWL_API_KEY"))


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not docker_available(), reason="Docker not available"),
    pytest.mark.skipif(not firecrawl_key_available(), reason="FIRECRAWL_API_KEY not set"),
]


class TestPluginEnvForwarding:
    """Tests for requires_env auto-forwarding into Docker containers."""

    @pytest.mark.asyncio
    async def test_resolve_plugin_env_populates_secrets(self) -> None:
        """resolve_plugin_env() should read requires_env and forward matching host env vars."""
        config = WorkspaceConfig(
            provider="docker",
            image="python:3.12-slim",
            plugins=[str(RESEARCH_PLUGIN)],
        )

        # Before: no secrets
        assert "FIRECRAWL_API_KEY" not in config.secrets

        # Resolve: reads plugin.json requires_env, matches host env
        config.resolve_plugin_env()

        # After: secret forwarded
        assert "FIRECRAWL_API_KEY" in config.secrets
        assert config.secrets["FIRECRAWL_API_KEY"] == os.environ["FIRECRAWL_API_KEY"]

    @pytest.mark.asyncio
    async def test_secret_available_inside_container(self) -> None:
        """FIRECRAWL_API_KEY should be accessible inside the Docker container."""
        async with AgenticWorkspace.create(
            provider="docker",
            image="python:3.12-slim",
            plugins=[str(RESEARCH_PLUGIN)],
            security=SecurityConfig.development(),
        ) as workspace:
            result = await workspace.execute("echo $FIRECRAWL_API_KEY")

            # Should be set and non-empty
            value = result.stdout.strip()
            assert value, "FIRECRAWL_API_KEY should be set inside container"
            assert value == os.environ["FIRECRAWL_API_KEY"]

    @pytest.mark.asyncio
    async def test_firecrawl_api_call_inside_container(self) -> None:
        """Should be able to call Firecrawl API from inside the container."""
        async with AgenticWorkspace.create(
            provider="docker",
            image="python:3.12-slim",
            plugins=[str(RESEARCH_PLUGIN)],
            security=SecurityConfig.development(),
        ) as workspace:
            # Write a test script to avoid shell quoting issues
            await workspace.write_file(
                "test_firecrawl.py",
                "import os\n"
                "from firecrawl import FirecrawlApp\n"
                "app = FirecrawlApp(api_key=os.environ['FIRECRAWL_API_KEY'])\n"
                "result = app.scrape('https://httpbin.org/html', formats=['markdown'])\n"
                "print(f'OK: {len(result.markdown)} chars')\n",
            )

            # Install firecrawl-py and run the test script
            result = await workspace.execute(
                "pip install -q firecrawl-py > /dev/null 2>&1 && python3 test_firecrawl.py",
                timeout=60,
            )

            assert result.exit_code == 0, f"Firecrawl call failed: {result.stderr}"
            assert "OK:" in result.stdout, f"Unexpected output: {result.stdout}"
            # Parse "OK: 1234 chars"
            chars = int(result.stdout.split("OK: ")[1].split(" chars")[0])
            assert chars > 100, f"Expected substantial content, got {chars} chars"


class TestPluginEnvEdgeCases:
    """Edge case tests for plugin env resolution."""

    @pytest.mark.asyncio
    async def test_missing_optional_env_not_fatal(self) -> None:
        """Optional env vars should not cause errors if not set."""
        config = WorkspaceConfig(
            provider="docker",
            image="python:3.12-slim",
            plugins=[str(RESEARCH_PLUGIN)],
        )

        # Temporarily unset the key to test optional behavior
        original = os.environ.pop("FIRECRAWL_API_KEY", None)
        try:
            # Should not raise (FIRECRAWL_API_KEY is required=false in plugin.json)
            config.resolve_plugin_env()
            assert "FIRECRAWL_API_KEY" not in config.secrets
        finally:
            if original:
                os.environ["FIRECRAWL_API_KEY"] = original

    @pytest.mark.asyncio
    async def test_explicit_secret_not_overwritten(self) -> None:
        """Explicitly set secrets should not be overwritten by resolve_plugin_env()."""
        config = WorkspaceConfig(
            provider="docker",
            image="python:3.12-slim",
            plugins=[str(RESEARCH_PLUGIN)],
            secrets={"FIRECRAWL_API_KEY": "explicit-value"},
        )

        config.resolve_plugin_env()

        # Should keep the explicit value
        assert config.secrets["FIRECRAWL_API_KEY"] == "explicit-value"

    @pytest.mark.asyncio
    async def test_plugin_without_requires_env(self) -> None:
        """Plugins without requires_env should work fine."""
        # sdlc plugin has no requires_env
        sdlc_plugin = RESEARCH_PLUGIN.parent / "sdlc"
        if not sdlc_plugin.exists():
            pytest.skip("sdlc plugin not found")

        config = WorkspaceConfig(
            provider="docker",
            image="python:3.12-slim",
            plugins=[str(sdlc_plugin)],
        )

        # Should not raise
        config.resolve_plugin_env()
        assert len(config.secrets) == 0
