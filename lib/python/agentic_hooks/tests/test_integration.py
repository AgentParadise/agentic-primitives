"""Integration tests for the complete client → backend flow.

These tests verify the full integration between the agentic-hooks client
library and the hooks-backend service.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agentic_hooks import EventType, HookClient, HookEvent
from agentic_hooks.backends import JSONLBackend, NullBackend


def make_event(session_id: str = "session-123") -> HookEvent:
    """Create a test event."""
    return HookEvent(
        event_type=EventType.SESSION_STARTED,
        session_id=session_id,
        data={"key": "value"},
    )


class TestClientJSONLIntegration:
    """Integration tests for client with JSONL backend."""

    @pytest.mark.asyncio
    async def test_full_flow_single_event(self, tmp_path: Path) -> None:
        """Test complete flow: emit → flush → stored in JSONL."""
        output_path = tmp_path / "events.jsonl"
        backend = JSONLBackend(output_path=output_path)

        async with HookClient(backend=backend, batch_size=50) as client:
            await client.emit(make_event("session-1"))
            await client.flush()

        # Verify event was stored
        lines = output_path.read_text().strip().split("\n")
        assert len(lines) == 1

        event = json.loads(lines[0])
        assert event["session_id"] == "session-1"
        assert event["event_type"] == "session_started"

    @pytest.mark.asyncio
    async def test_full_flow_batch_events(self, tmp_path: Path) -> None:
        """Test batch emission and storage."""
        output_path = tmp_path / "events.jsonl"
        backend = JSONLBackend(output_path=output_path)

        async with HookClient(backend=backend, batch_size=50) as client:
            for i in range(100):
                await client.emit(make_event(f"session-{i}"))

        # Verify all events stored
        lines = output_path.read_text().strip().split("\n")
        assert len(lines) == 100

    @pytest.mark.asyncio
    async def test_auto_flush_on_close(self, tmp_path: Path) -> None:
        """Test events are flushed when client closes."""
        output_path = tmp_path / "events.jsonl"
        backend = JSONLBackend(output_path=output_path)

        async with HookClient(backend=backend, batch_size=100) as client:
            # Emit fewer than batch_size
            for i in range(10):
                await client.emit(make_event(f"session-{i}"))

        # Events should be flushed on close
        lines = output_path.read_text().strip().split("\n")
        assert len(lines) == 10

    @pytest.mark.asyncio
    async def test_periodic_flush(self, tmp_path: Path) -> None:
        """Test periodic flush based on interval."""
        output_path = tmp_path / "events.jsonl"
        backend = JSONLBackend(output_path=output_path)

        async with HookClient(
            backend=backend,
            batch_size=100,  # High batch size
            flush_interval_seconds=0.1,  # Short interval
        ) as client:
            await client.emit(make_event())
            await asyncio.sleep(0.2)  # Wait for periodic flush

            # Check file during client lifecycle
            lines = output_path.read_text().strip().split("\n")
            assert len(lines) >= 1


class TestClientConcurrency:
    """Tests for concurrent client operations."""

    @pytest.mark.asyncio
    async def test_concurrent_emits(self) -> None:
        """Test multiple concurrent emit calls."""
        backend = NullBackend()

        async with HookClient(backend=backend, batch_size=50) as client:
            # Emit 100 events concurrently
            tasks = [client.emit(make_event(f"session-{i}")) for i in range(100)]
            await asyncio.gather(*tasks)

        # All events should be received
        assert len(backend.events_received) == 100

    @pytest.mark.asyncio
    async def test_multiple_clients_same_backend(self, tmp_path: Path) -> None:
        """Test multiple clients writing to same backend."""
        output_path = tmp_path / "events.jsonl"

        async def emit_events(client_id: int, count: int) -> None:
            backend = JSONLBackend(output_path=output_path)
            async with HookClient(backend=backend, batch_size=10) as client:
                for i in range(count):
                    await client.emit(make_event(f"client-{client_id}-session-{i}"))

        # Run 5 clients concurrently
        tasks = [emit_events(i, 20) for i in range(5)]
        await asyncio.gather(*tasks)

        # All events from all clients should be stored
        lines = output_path.read_text().strip().split("\n")
        assert len(lines) == 100  # 5 clients × 20 events


class TestBenchmarkConcurrentClients:
    """Benchmark tests for concurrent client performance."""

    @pytest.mark.asyncio
    async def test_100_concurrent_clients(self) -> None:
        """Benchmark: 100 concurrent clients each emitting 10 events."""
        backend = NullBackend()
        num_clients = 100
        events_per_client = 10

        async def client_task(client_id: int) -> None:
            async with HookClient(backend=backend, batch_size=5) as client:
                for i in range(events_per_client):
                    await client.emit(make_event(f"client-{client_id}-{i}"))

        start = datetime.now(UTC)

        tasks = [client_task(i) for i in range(num_clients)]
        await asyncio.gather(*tasks)

        duration = (datetime.now(UTC) - start).total_seconds()

        total_events = num_clients * events_per_client
        events_per_second = total_events / duration

        print("\n=== 100 Client Benchmark ===")
        print(f"Total events: {total_events}")
        print(f"Duration: {duration:.3f}s")
        print(f"Throughput: {events_per_second:.0f} events/second")

        # Verify all events received
        assert len(backend.events_received) == total_events

    @pytest.mark.asyncio
    async def test_1000_concurrent_clients(self) -> None:
        """Benchmark: 1000 concurrent clients each emitting 10 events.

        This is the primary scalability target for the hook system.
        Target: <5ms p99 latency.
        """
        backend = NullBackend()
        num_clients = 1000
        events_per_client = 10

        latencies: list[float] = []

        async def client_task(client_id: int) -> None:
            async with HookClient(backend=backend, batch_size=10) as client:
                for i in range(events_per_client):
                    start = datetime.now(UTC)
                    await client.emit(make_event(f"client-{client_id}-{i}"))
                    latency = (datetime.now(UTC) - start).total_seconds() * 1000
                    latencies.append(latency)

        overall_start = datetime.now(UTC)

        tasks = [client_task(i) for i in range(num_clients)]
        await asyncio.gather(*tasks)

        overall_duration = (datetime.now(UTC) - overall_start).total_seconds()

        total_events = num_clients * events_per_client
        events_per_second = total_events / overall_duration

        # Calculate latency statistics
        sorted_latencies = sorted(latencies)
        p50 = sorted_latencies[len(sorted_latencies) // 2]
        p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
        p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]

        print("\n=== 1000 Client Benchmark ===")
        print(f"Total events: {total_events}")
        print(f"Duration: {overall_duration:.3f}s")
        print(f"Throughput: {events_per_second:.0f} events/second")
        print(f"Latency p50: {p50:.2f}ms")
        print(f"Latency p95: {p95:.2f}ms")
        print(f"Latency p99: {p99:.2f}ms")

        # Verify all events received
        assert len(backend.events_received) == total_events

        # Performance assertions
        # Note: In-memory NullBackend should easily beat these targets
        assert p99 < 10.0, f"p99 latency {p99:.2f}ms exceeds 10ms target"

    @pytest.mark.asyncio
    async def test_burst_traffic(self) -> None:
        """Test handling burst traffic (1000 events in rapid succession)."""
        backend = NullBackend()

        async with HookClient(backend=backend, batch_size=100) as client:
            start = datetime.now(UTC)

            # Burst: 1000 events as fast as possible
            for i in range(1000):
                await client.emit(make_event(f"burst-{i}"))

            await client.flush()

            duration = (datetime.now(UTC) - start).total_seconds()

        events_per_second = 1000 / duration

        print("\n=== Burst Traffic Benchmark ===")
        print("Total events: 1000")
        print(f"Duration: {duration:.3f}s")
        print(f"Throughput: {events_per_second:.0f} events/second")

        assert len(backend.events_received) == 1000


class TestEventCorrelation:
    """Tests for event correlation and ordering."""

    @pytest.mark.asyncio
    async def test_session_events_ordered(self, tmp_path: Path) -> None:
        """Test events for same session are stored in order."""
        output_path = tmp_path / "events.jsonl"
        backend = JSONLBackend(output_path=output_path)

        async with HookClient(backend=backend, batch_size=50) as client:
            # Emit session lifecycle events in order
            await client.emit(
                HookEvent(
                    event_type=EventType.SESSION_STARTED,
                    session_id="session-1",
                    data={"order": 1},
                )
            )
            await client.emit(
                HookEvent(
                    event_type=EventType.TOOL_EXECUTION_STARTED,
                    session_id="session-1",
                    data={"order": 2},
                )
            )
            await client.emit(
                HookEvent(
                    event_type=EventType.TOOL_EXECUTION_COMPLETED,
                    session_id="session-1",
                    data={"order": 3},
                )
            )
            await client.emit(
                HookEvent(
                    event_type=EventType.SESSION_COMPLETED,
                    session_id="session-1",
                    data={"order": 4},
                )
            )

        # Verify order is preserved
        lines = output_path.read_text().strip().split("\n")
        events = [json.loads(line) for line in lines]

        assert len(events) == 4
        assert [e["data"]["order"] for e in events] == [1, 2, 3, 4]
        assert events[0]["event_type"] == "session_started"
        assert events[3]["event_type"] == "session_completed"

    @pytest.mark.asyncio
    async def test_workflow_phase_milestone_correlation(self) -> None:
        """Test workflow/phase/milestone correlation is preserved."""
        backend = NullBackend()

        async with HookClient(backend=backend) as client:
            await client.emit(
                HookEvent(
                    event_type=EventType.TOOL_EXECUTION_STARTED,
                    session_id="session-1",
                    workflow_id="workflow-1",
                    phase_id="phase-1",
                    milestone_id="milestone-1",
                )
            )

        assert len(backend.events_received) == 1
        event = backend.events_received[0]
        assert event["workflow_id"] == "workflow-1"
        assert event["phase_id"] == "phase-1"
        assert event["milestone_id"] == "milestone-1"
