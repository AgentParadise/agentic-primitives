"""
Unit tests for Firecrawl Scraper Tool.

All Firecrawl API calls are mocked to avoid network dependencies.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from firecrawl_scraper import (
    ScrapeMetadata,
    ScrapeResult,
    app,
    generate_frontmatter,
    get_firecrawl_api_key,
    save_markdown,
    scrape_url,
)

runner = CliRunner()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_firecrawl():
    """Mock Firecrawl API client."""
    with patch("firecrawl.FirecrawlApp") as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        mock_instance.scrape_url.return_value = {
            "markdown": "# Test Page\n\nThis is test content.",
            "metadata": {"title": "Test Page Title"},
        }
        yield mock_instance


@pytest.fixture
def tmp_output_dir(tmp_path: Path) -> Path:
    """Create temporary output directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def sample_metadata() -> ScrapeMetadata:
    """Create sample metadata for testing."""
    return ScrapeMetadata(
        source_url="https://example.com/docs",  # type: ignore[arg-type]
        title="Example Documentation",
        scraped_at=datetime(2025, 11, 29, 10, 30, 0, tzinfo=UTC),
        version="1.0.0",
        session_id="test-session-123",
    )


# =============================================================================
# Test ScrapeMetadata Model
# =============================================================================


class TestScrapeMetadata:
    """Tests for ScrapeMetadata model."""

    def test_create_minimal_metadata(self):
        """Test creating metadata with minimal fields."""
        metadata = ScrapeMetadata(
            source_url="https://example.com",  # type: ignore[arg-type]
            title="Test",
        )
        assert str(metadata.source_url) == "https://example.com/"
        assert metadata.title == "Test"
        assert metadata.version is None
        assert metadata.tool == "firecrawl-scraper"

    def test_create_full_metadata(self, sample_metadata: ScrapeMetadata):
        """Test creating metadata with all fields."""
        assert str(sample_metadata.source_url) == "https://example.com/docs"
        assert sample_metadata.title == "Example Documentation"
        assert sample_metadata.version == "1.0.0"
        assert sample_metadata.session_id == "test-session-123"

    def test_scraped_at_default(self):
        """Test that scraped_at defaults to current time."""
        metadata = ScrapeMetadata(
            source_url="https://example.com",  # type: ignore[arg-type]
            title="Test",
        )
        assert metadata.scraped_at is not None
        assert isinstance(metadata.scraped_at, datetime)


# =============================================================================
# Test ScrapeResult Model
# =============================================================================


class TestScrapeResult:
    """Tests for ScrapeResult model."""

    def test_create_result(self):
        """Test creating a scrape result."""
        result = ScrapeResult(
            path="/output/test.md",
            bytes=1234,
            source_url="https://example.com",
            title="Test Page",
        )
        assert result.path == "/output/test.md"
        assert result.bytes == 1234
        assert result.source_url == "https://example.com"
        assert result.title == "Test Page"


# =============================================================================
# Test Frontmatter Generation
# =============================================================================


class TestGenerateFrontmatter:
    """Tests for frontmatter generation."""

    def test_minimal_frontmatter(self):
        """Test frontmatter with minimal fields."""
        metadata = ScrapeMetadata(
            source_url="https://example.com",  # type: ignore[arg-type]
            title="Test Page",
            scraped_at=datetime(2025, 11, 29, 10, 30, 0, tzinfo=UTC),
        )
        frontmatter = generate_frontmatter(metadata)

        assert "---" in frontmatter
        assert "source_url: https://example.com/" in frontmatter
        assert "title: Test Page" in frontmatter
        assert "scraped_at: 2025-11-29T10:30:00+00:00" in frontmatter
        assert "tool: firecrawl-scraper" in frontmatter
        assert "version:" not in frontmatter
        assert "session_id:" not in frontmatter

    def test_full_frontmatter(self, sample_metadata: ScrapeMetadata):
        """Test frontmatter with all fields."""
        frontmatter = generate_frontmatter(sample_metadata)

        assert "version: 1.0.0" in frontmatter
        assert "session_id: test-session-123" in frontmatter

    def test_frontmatter_format(self, sample_metadata: ScrapeMetadata):
        """Test frontmatter starts and ends with ---."""
        frontmatter = generate_frontmatter(sample_metadata)
        lines = frontmatter.split("\n")

        assert lines[0] == "---"
        assert lines[-1] == "---"


# =============================================================================
# Test API Key Retrieval
# =============================================================================


class TestGetFirecrawlApiKey:
    """Tests for API key retrieval."""

    def test_get_key_from_environment(self):
        """Test getting API key from environment variable."""
        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "fc-test-key-123"}):
            key = get_firecrawl_api_key()
            assert key == "fc-test-key-123"

    def test_missing_key_raises_exit(self):
        """Test that missing API key raises typer.Exit."""
        import typer

        with patch.dict(os.environ, {}, clear=True):
            # Remove any existing key
            os.environ.pop("FIRECRAWL_API_KEY", None)

            with pytest.raises(typer.Exit):
                get_firecrawl_api_key()

    @pytest.mark.skip(reason="Requires agentic_settings to be installed")
    def test_get_key_from_agentic_settings(self):
        """Test getting API key from agentic_settings.
        
        Note: This test is skipped until agentic_settings is properly installed.
        The integration with agentic_settings is verified in integration tests.
        """
        pass  # Covered by integration tests when agentic_settings is available


# =============================================================================
# Test URL Scraping
# =============================================================================


class TestScrapeUrl:
    """Tests for URL scraping function."""

    def test_scrape_returns_content_and_title(self, mock_firecrawl):
        """Test that scrape_url returns content and title."""
        content, title = scrape_url(
            "https://example.com",
            "fc-test-key",
            ["markdown"],
        )

        assert "# Test Page" in content
        assert title == "Test Page Title"
        mock_firecrawl.scrape_url.assert_called_once()

    def test_scrape_extracts_title_from_content(self, mock_firecrawl):
        """Test title extraction from first heading if not in metadata."""
        mock_firecrawl.scrape_url.return_value = {
            "markdown": "# Heading Title\n\nContent here.",
            "metadata": {},
        }

        content, title = scrape_url("https://example.com", "fc-test-key")
        assert title == "Heading Title"

    def test_scrape_default_title(self, mock_firecrawl):
        """Test default title when none found."""
        mock_firecrawl.scrape_url.return_value = {
            "markdown": "No heading here, just content.",
            "metadata": {},
        }

        content, title = scrape_url("https://example.com", "fc-test-key")
        assert title == "Untitled Document"

    def test_scrape_uses_default_formats(self, mock_firecrawl):
        """Test that default formats is markdown."""
        scrape_url("https://example.com", "fc-test-key")

        mock_firecrawl.scrape_url.assert_called_with(
            "https://example.com",
            params={"formats": ["markdown"]},
        )


# =============================================================================
# Test File Saving
# =============================================================================


class TestSaveMarkdown:
    """Tests for markdown file saving."""

    def test_save_creates_file(
        self, tmp_output_dir: Path, sample_metadata: ScrapeMetadata
    ):
        """Test that save_markdown creates the output file."""
        output_path = tmp_output_dir / "test.md"
        content = "# Test Content\n\nSome text."

        result = save_markdown(content, output_path, sample_metadata)

        assert output_path.exists()
        assert result.path == str(output_path)
        assert result.bytes > 0

    def test_save_includes_frontmatter(
        self, tmp_output_dir: Path, sample_metadata: ScrapeMetadata
    ):
        """Test that saved file includes frontmatter."""
        output_path = tmp_output_dir / "test.md"
        content = "# Test Content"

        save_markdown(content, output_path, sample_metadata)

        saved_content = output_path.read_text()
        assert saved_content.startswith("---")
        assert "source_url:" in saved_content
        assert "# Test Content" in saved_content

    def test_save_creates_parent_dirs(
        self, tmp_output_dir: Path, sample_metadata: ScrapeMetadata
    ):
        """Test that save_markdown creates parent directories."""
        output_path = tmp_output_dir / "nested" / "deep" / "test.md"

        save_markdown("Content", output_path, sample_metadata)

        assert output_path.exists()

    def test_save_result_has_correct_bytes(
        self, tmp_output_dir: Path, sample_metadata: ScrapeMetadata
    ):
        """Test that result has correct byte count."""
        output_path = tmp_output_dir / "test.md"
        content = "Test content"

        result = save_markdown(content, output_path, sample_metadata)

        actual_size = output_path.stat().st_size
        assert result.bytes == actual_size


# =============================================================================
# Test CLI Commands
# =============================================================================


class TestCLI:
    """Tests for CLI commands."""

    def test_version_command(self):
        """Test version command shows version."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "firecrawl-scraper" in result.stdout

    def test_scrape_command_missing_args(self):
        """Test scrape command requires arguments."""
        result = runner.invoke(app, ["scrape"])
        assert result.exit_code != 0

    def test_scrape_command_success(self, mock_firecrawl, tmp_path: Path):
        """Test successful scrape command."""
        output_file = tmp_path / "output.md"

        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "fc-test-key"}):
            result = runner.invoke(
                app,
                [
                    "scrape",
                    "https://example.com",
                    str(output_file),
                    "--title",
                    "Custom Title",
                ],
            )

        assert result.exit_code == 0
        assert output_file.exists()
        assert "Scrape Complete" in result.stdout

    def test_scrape_command_with_version(self, mock_firecrawl, tmp_path: Path):
        """Test scrape command with version option."""
        output_file = tmp_path / "output.md"

        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "fc-test-key"}):
            result = runner.invoke(
                app,
                [
                    "scrape",
                    "https://example.com",
                    str(output_file),
                    "--version",
                    "2.5.0",
                ],
            )

        assert result.exit_code == 0
        content = output_file.read_text()
        assert "version: 2.5.0" in content

    def test_scrape_command_with_session_id(self, mock_firecrawl, tmp_path: Path):
        """Test scrape command with session-id option."""
        output_file = tmp_path / "output.md"

        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "fc-test-key"}):
            result = runner.invoke(
                app,
                [
                    "scrape",
                    "https://example.com",
                    str(output_file),
                    "--session-id",
                    "sess-123",
                ],
            )

        assert result.exit_code == 0
        content = output_file.read_text()
        assert "session_id: sess-123" in content

    def test_scrape_command_missing_api_key(self, tmp_path: Path):
        """Test scrape command fails without API key."""
        output_file = tmp_path / "output.md"

        # Clear environment
        env = os.environ.copy()
        env.pop("FIRECRAWL_API_KEY", None)

        with patch.dict(os.environ, env, clear=True):
            result = runner.invoke(
                app, ["scrape", "https://example.com", str(output_file)]
            )

        assert result.exit_code == 1
        assert "Missing Firecrawl API Key" in result.stdout or "Missing" in str(
            result.output
        )

    def test_scrape_command_verbose(self, mock_firecrawl, tmp_path: Path):
        """Test scrape command with verbose flag."""
        output_file = tmp_path / "output.md"

        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "fc-test-key"}):
            result = runner.invoke(
                app,
                [
                    "scrape",
                    "https://example.com",
                    str(output_file),
                    "--verbose",
                ],
            )

        assert result.exit_code == 0


# =============================================================================
# Integration-like Tests (still mocked)
# =============================================================================


class TestEndToEnd:
    """End-to-end tests with mocked API."""

    def test_full_scrape_workflow(self, mock_firecrawl, tmp_path: Path):
        """Test complete scrape workflow from CLI to file."""
        output_file = tmp_path / "docs" / "scraped.md"

        mock_firecrawl.scrape_url.return_value = {
            "markdown": "# API Reference\n\n## Endpoints\n\nGET /users",
            "metadata": {"title": "API Docs"},
        }

        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "fc-prod-key"}):
            result = runner.invoke(
                app,
                [
                    "scrape",
                    "https://api.example.com/docs",
                    str(output_file),
                    "--version",
                    "3.0.0",
                    "--session-id",
                    "workflow-test",
                ],
            )

        assert result.exit_code == 0
        assert output_file.exists()

        content = output_file.read_text()

        # Verify frontmatter
        assert "---" in content
        assert "source_url: https://api.example.com/docs" in content
        assert "title: API Docs" in content
        assert "version: 3.0.0" in content
        assert "session_id: workflow-test" in content
        assert "tool: firecrawl-scraper" in content

        # Verify content
        assert "# API Reference" in content
        assert "GET /users" in content

