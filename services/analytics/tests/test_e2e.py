"""End-to-End tests for the analytics pipeline

These tests validate the full analytics pipeline from hook input to event output:
1. Raw hook event → EventNormalizer → NormalizedEvent
2. NormalizedEvent → EventPublisher → Output (file/API)
3. Full pipeline integration with middleware scripts
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from analytics.models.hook_input import HookInput
from analytics.normalizer import EventNormalizer
from analytics.publishers.api import APIPublisher
from analytics.publishers.file import FilePublisher

# Test fixtures path
FIXTURES_DIR = Path(__file__).parent / "fixtures"
CLAUDE_HOOKS_DIR = FIXTURES_DIR / "claude_hooks"


@pytest.mark.e2e
class TestFullPipelineIntegration:
    """Test the complete analytics pipeline end-to-end"""

    async def test_full_pipeline_pre_tool_use(self, tmp_path: Path) -> None:
        """Test full pipeline: PreToolUse hook → normalize → publish to file"""
        # Step 1: Load raw hook event
        with open(CLAUDE_HOOKS_DIR / "pre_tool_use.json") as f:
            raw_event = json.load(f)

        hook_input = HookInput(provider="claude", event="PreToolUse", data=raw_event)

        # Step 2: Normalize event
        normalizer = EventNormalizer()
        normalized_event = normalizer.normalize(hook_input)

        # Validate normalized event
        assert normalized_event.event_type == "tool_execution_started"
        assert normalized_event.provider == "claude"
        assert normalized_event.session_id == "abc123-def456-ghi789"

        # Step 3: Publish to file
        output_file = tmp_path / "events.jsonl"
        publisher = FilePublisher(output_path=output_file)
        await publisher.publish(normalized_event)
        await publisher.close()

        # Step 4: Verify output
        assert output_file.exists()
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) == 1
            event_data = json.loads(lines[0])
            assert event_data["event_type"] == "tool_execution_started"
            assert event_data["session_id"] == "abc123-def456-ghi789"

    async def test_full_pipeline_session_lifecycle(self, tmp_path: Path) -> None:
        """Test full pipeline for complete session lifecycle"""
        output_file = tmp_path / "session_events.jsonl"
        publisher = FilePublisher(output_path=output_file)
        normalizer = EventNormalizer()

        # Session lifecycle: Start → UserPrompt → PreToolUse → PostToolUse → End
        events = [
            ("session_start.json", "SessionStart", "session_started"),
            (
                "user_prompt_submit.json",
                "UserPromptSubmit",
                "user_prompt_submitted",
            ),
            ("pre_tool_use.json", "PreToolUse", "tool_execution_started"),
            ("post_tool_use.json", "PostToolUse", "tool_execution_completed"),
            ("session_end.json", "SessionEnd", "session_completed"),
        ]

        for fixture_file, event_type, expected_normalized_type in events:
            with open(CLAUDE_HOOKS_DIR / fixture_file) as f:
                raw_event = json.load(f)

            hook_input = HookInput(provider="claude", event=event_type, data=raw_event)
            normalized_event = normalizer.normalize(hook_input)
            assert normalized_event.event_type == expected_normalized_type
            await publisher.publish(normalized_event)

        await publisher.close()

        # Verify all events were written
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) == 5

            # Verify event types in order
            event_types = [json.loads(line)["event_type"] for line in lines]
            assert event_types == [
                "session_started",
                "user_prompt_submitted",
                "tool_execution_started",
                "tool_execution_completed",
                "session_completed",
            ]

    async def test_full_pipeline_multiple_providers(self, tmp_path: Path) -> None:
        """Test full pipeline with events from multiple providers"""
        output_file = tmp_path / "multi_provider_events.jsonl"
        publisher = FilePublisher(output_path=output_file)
        normalizer = EventNormalizer()

        # Test with different provider names (provider-agnostic)
        providers = ["claude", "openai", "cursor", "gemini"]

        for provider in providers:
            with open(CLAUDE_HOOKS_DIR / "session_start.json") as f:
                raw_event = json.load(f)

            hook_input = HookInput(provider=provider, event="SessionStart", data=raw_event)
            normalized_event = normalizer.normalize(hook_input)
            assert normalized_event.provider == provider
            await publisher.publish(normalized_event)

        await publisher.close()

        # Verify all providers were recorded
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) == 4

            recorded_providers = [json.loads(line)["provider"] for line in lines]
            assert set(recorded_providers) == set(providers)

    async def test_full_pipeline_api_backend(self, tmp_path: Path) -> None:
        """Test full pipeline with API publisher backend"""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = AsyncMock(status_code=200)

            # Load event
            with open(CLAUDE_HOOKS_DIR / "pre_tool_use.json") as f:
                raw_event = json.load(f)

            hook_input = HookInput(provider="claude", event="PreToolUse", data=raw_event)

            # Normalize
            normalizer = EventNormalizer()
            normalized_event = normalizer.normalize(hook_input)

            # Publish to API
            publisher = APIPublisher(endpoint="https://api.example.com/events")
            await publisher.publish(normalized_event)
            await publisher.close()

            # Verify API was called
            assert mock_post.called
            call_args = mock_post.call_args
            assert "https://api.example.com/events" in str(call_args)

    async def test_full_pipeline_batch_processing(self, tmp_path: Path) -> None:
        """Test full pipeline with batch event processing"""
        output_file = tmp_path / "batch_events.jsonl"
        publisher = FilePublisher(output_path=output_file)
        normalizer = EventNormalizer()

        # Normalize multiple events
        normalized_events = []
        for fixture_file in [
            "session_start.json",
            "pre_tool_use.json",
            "post_tool_use.json",
        ]:
            with open(CLAUDE_HOOKS_DIR / fixture_file) as f:
                raw_event = json.load(f)

            # Infer event type from filename
            event_map = {
                "session_start.json": "SessionStart",
                "pre_tool_use.json": "PreToolUse",
                "post_tool_use.json": "PostToolUse",
            }
            event_type = event_map[fixture_file]

            hook_input = HookInput(provider="claude", event=event_type, data=raw_event)
            normalized_events.append(normalizer.normalize(hook_input))

        # Publish batch
        await publisher.publish_batch(normalized_events)
        await publisher.close()

        # Verify batch was written
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) == 3


@pytest.mark.e2e
class TestMiddlewareScripts:
    """Test the middleware entry point scripts"""

    def test_event_normalizer_middleware_script(self, tmp_path: Path) -> None:
        """Test event_normalizer.py middleware script via subprocess"""
        # Prepare input
        with open(CLAUDE_HOOKS_DIR / "pre_tool_use.json") as f:
            raw_event = json.load(f)

        hook_input = HookInput(provider="claude", event="PreToolUse", data=raw_event)
        input_json = hook_input.model_dump_json()

        # Run middleware script
        middleware_path = Path(__file__).parent.parent / "middleware" / "event_normalizer.py"
        result = subprocess.run(
            [sys.executable, str(middleware_path)],
            check=False,
            input=input_json,
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Verify output
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["event_type"] == "tool_execution_started"
        assert output["provider"] == "claude"

    def test_event_publisher_middleware_script(self, tmp_path: Path) -> None:
        """Test event_publisher.py middleware script via subprocess"""
        # Prepare normalized event
        with open(FIXTURES_DIR / "normalized_events" / "tool_execution_started.json") as f:
            normalized_event_data = json.load(f)

        # Run middleware script with file backend
        middleware_path = Path(__file__).parent.parent / "middleware" / "event_publisher.py"
        output_file = tmp_path / "middleware_output.jsonl"

        env = {
            "ANALYTICS_PUBLISHER_BACKEND": "file",
            "ANALYTICS_OUTPUT_PATH": str(output_file),
        }

        result = subprocess.run(
            [sys.executable, str(middleware_path)],
            check=False,
            input=json.dumps(normalized_event_data),
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
            timeout=5,
        )

        # Verify script succeeded
        assert result.returncode == 0

        # Verify file was written
        assert output_file.exists()
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) == 1
            event_data = json.loads(lines[0])
            assert event_data["event_type"] == "tool_execution_started"

    def test_middleware_pipeline_integration(self, tmp_path: Path) -> None:
        """Test full middleware pipeline: normalizer → publisher"""
        # Prepare input
        with open(CLAUDE_HOOKS_DIR / "pre_tool_use.json") as f:
            raw_event = json.load(f)

        hook_input = HookInput(provider="claude", event="PreToolUse", data=raw_event)
        input_json = hook_input.model_dump_json()

        # Step 1: Run normalizer
        normalizer_path = Path(__file__).parent.parent / "middleware" / "event_normalizer.py"
        normalizer_result = subprocess.run(
            [sys.executable, str(normalizer_path)],
            check=False,
            input=input_json,
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert normalizer_result.returncode == 0
        normalized_json = normalizer_result.stdout

        # Step 2: Run publisher
        publisher_path = Path(__file__).parent.parent / "middleware" / "event_publisher.py"
        output_file = tmp_path / "pipeline_output.jsonl"

        env = {
            "ANALYTICS_PUBLISHER_BACKEND": "file",
            "ANALYTICS_OUTPUT_PATH": str(output_file),
        }

        publisher_result = subprocess.run(
            [sys.executable, str(publisher_path)],
            check=False,
            input=normalized_json,
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
            timeout=5,
        )

        assert publisher_result.returncode == 0

        # Verify final output
        assert output_file.exists()
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) == 1
            event_data = json.loads(lines[0])
            assert event_data["event_type"] == "tool_execution_started"
            assert event_data["session_id"] == "abc123-def456-ghi789"


@pytest.mark.e2e
class TestErrorRecovery:
    """Test error recovery and resilience in the pipeline"""

    async def test_pipeline_handles_malformed_events(self, tmp_path: Path) -> None:
        """Test that pipeline handles malformed events gracefully"""
        from pydantic import ValidationError

        normalizer = EventNormalizer()

        # Malformed event (missing required fields)
        bad_input = HookInput(
            provider="claude",
            event="PreToolUse",
            data={"session_id": "test"},  # Missing many required fields
        )

        # Should raise ValidationError
        with pytest.raises(ValidationError):
            normalizer.normalize(bad_input)

    async def test_pipeline_handles_publisher_failures(self, tmp_path: Path) -> None:
        """Test that pipeline continues even if publisher fails"""
        # Load and normalize event
        with open(CLAUDE_HOOKS_DIR / "pre_tool_use.json") as f:
            raw_event = json.load(f)

        hook_input = HookInput(provider="claude", event="PreToolUse", data=raw_event)
        normalizer = EventNormalizer()
        normalized_event = normalizer.normalize(hook_input)

        # Try to publish to invalid path (should not raise)
        publisher = FilePublisher(output_path=Path("/invalid/path/events.jsonl"))
        await publisher.publish(normalized_event)  # Should not raise
        await publisher.close()

    async def test_pipeline_handles_api_failures(self, tmp_path: Path) -> None:
        """Test that pipeline continues even if API fails"""
        with patch("httpx.AsyncClient.post") as mock_post:
            import httpx

            mock_post.side_effect = httpx.ConnectError("Connection refused")

            # Load and normalize event
            with open(CLAUDE_HOOKS_DIR / "pre_tool_use.json") as f:
                raw_event = json.load(f)

            hook_input = HookInput(provider="claude", event="PreToolUse", data=raw_event)
            normalizer = EventNormalizer()
            normalized_event = normalizer.normalize(hook_input)

            # Publish to failing API (should not raise)
            publisher = APIPublisher(endpoint="https://api.example.com/events", retry_attempts=0)
            await publisher.publish(normalized_event)  # Should not raise
            await publisher.close()


@pytest.mark.e2e
class TestDataIntegrity:
    """Test data integrity throughout the pipeline"""

    async def test_event_data_preserved_through_pipeline(self, tmp_path: Path) -> None:
        """Test that event data is preserved accurately through the pipeline"""
        # Load original event
        with open(CLAUDE_HOOKS_DIR / "pre_tool_use.json") as f:
            raw_event = json.load(f)

        original_session_id = raw_event["session_id"]
        original_tool_name = raw_event["tool_name"]
        original_tool_input = raw_event["tool_input"]

        # Process through pipeline
        hook_input = HookInput(provider="claude", event="PreToolUse", data=raw_event)
        normalizer = EventNormalizer()
        normalized_event = normalizer.normalize(hook_input)

        output_file = tmp_path / "integrity_test.jsonl"
        publisher = FilePublisher(output_path=output_file)
        await publisher.publish(normalized_event)
        await publisher.close()

        # Read back and verify
        with open(output_file) as f:
            event_data = json.loads(f.read())

        assert event_data["session_id"] == original_session_id
        assert event_data["context"]["tool_name"] == original_tool_name
        assert event_data["context"]["tool_input"] == original_tool_input

    async def test_timestamp_consistency(self, tmp_path: Path) -> None:
        """Test that timestamps are consistent and valid"""
        from datetime import UTC, datetime

        # Process event
        with open(CLAUDE_HOOKS_DIR / "pre_tool_use.json") as f:
            raw_event = json.load(f)

        hook_input = HookInput(provider="claude", event="PreToolUse", data=raw_event)
        normalizer = EventNormalizer()
        normalized_event = normalizer.normalize(hook_input)

        # Verify timestamp is recent and in UTC
        assert isinstance(normalized_event.timestamp, datetime)
        assert normalized_event.timestamp.tzinfo == UTC

        # Timestamp should be within last minute
        now = datetime.now(UTC)
        time_diff = (now - normalized_event.timestamp).total_seconds()
        assert 0 <= time_diff < 60

    async def test_metadata_preservation(self, tmp_path: Path) -> None:
        """Test that metadata is preserved through the pipeline"""
        # Load event
        with open(CLAUDE_HOOKS_DIR / "pre_tool_use.json") as f:
            raw_event = json.load(f)

        hook_input = HookInput(provider="claude", event="PreToolUse", data=raw_event)
        normalizer = EventNormalizer()
        normalized_event = normalizer.normalize(hook_input)

        # Verify metadata
        assert normalized_event.metadata.hook_event_name == "PreToolUse"
        assert normalized_event.metadata.transcript_path == raw_event["transcript_path"]
        assert normalized_event.metadata.permission_mode == raw_event["permission_mode"]
        assert normalized_event.metadata.raw_event is not None


@pytest.mark.e2e
class TestPerformance:
    """Test performance characteristics of the pipeline"""

    async def test_pipeline_throughput(self, tmp_path: Path) -> None:
        """Test that pipeline can handle reasonable throughput"""
        import time

        output_file = tmp_path / "throughput_test.jsonl"
        publisher = FilePublisher(output_path=output_file)
        normalizer = EventNormalizer()

        # Load event
        with open(CLAUDE_HOOKS_DIR / "pre_tool_use.json") as f:
            raw_event = json.load(f)

        # Process 100 events
        start_time = time.time()
        for _ in range(100):
            hook_input = HookInput(provider="claude", event="PreToolUse", data=raw_event)
            normalized_event = normalizer.normalize(hook_input)
            await publisher.publish(normalized_event)

        await publisher.close()
        elapsed_time = time.time() - start_time

        # Should process 100 events in under 5 seconds
        assert elapsed_time < 5.0

        # Verify all events were written
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) == 100

    async def test_pipeline_memory_efficiency(self, tmp_path: Path) -> None:
        """Test that pipeline doesn't leak memory with many events"""
        import gc

        output_file = tmp_path / "memory_test.jsonl"
        publisher = FilePublisher(output_path=output_file)
        normalizer = EventNormalizer()

        # Load event
        with open(CLAUDE_HOOKS_DIR / "pre_tool_use.json") as f:
            raw_event = json.load(f)

        # Process many events
        for _ in range(1000):
            hook_input = HookInput(provider="claude", event="PreToolUse", data=raw_event)
            normalized_event = normalizer.normalize(hook_input)
            await publisher.publish(normalized_event)

        await publisher.close()

        # Force garbage collection
        gc.collect()

        # Verify all events were written
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) == 1000


@pytest.mark.e2e
class TestConcurrency:
    """Test concurrent pipeline operations"""

    async def test_concurrent_publishers(self, tmp_path: Path) -> None:
        """Test that multiple publishers can write concurrently"""
        import asyncio

        # Load event
        with open(CLAUDE_HOOKS_DIR / "pre_tool_use.json") as f:
            raw_event = json.load(f)

        hook_input = HookInput(provider="claude", event="PreToolUse", data=raw_event)
        normalizer = EventNormalizer()
        normalized_event = normalizer.normalize(hook_input)

        # Create multiple publishers
        publishers = [
            FilePublisher(output_path=tmp_path / f"concurrent_{i}.jsonl") for i in range(5)
        ]

        # Publish concurrently
        await asyncio.gather(*[publisher.publish(normalized_event) for publisher in publishers])

        # Close all publishers
        await asyncio.gather(*[publisher.close() for publisher in publishers])

        # Verify all files were written
        for i in range(5):
            output_file = tmp_path / f"concurrent_{i}.jsonl"
            assert output_file.exists()
            with open(output_file) as f:
                lines = f.readlines()
                assert len(lines) == 1
