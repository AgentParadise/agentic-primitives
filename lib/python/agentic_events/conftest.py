"""Pytest configuration for agentic_events tests."""

import pytest

from agentic_events import load_recording


@pytest.fixture
def recording(request):
    """Load recording from @pytest.mark.recording('name') marker.

    Usage:
        @pytest.mark.recording("list-files")
        def test_something(recording):
            events = recording.get_events()
            assert len(events) > 0
    """
    marker = request.node.get_closest_marker("recording")
    if marker is None:
        pytest.skip("No recording marker specified")

    name = marker.args[0]
    try:
        return load_recording(name)
    except FileNotFoundError:
        pytest.skip(f"Recording '{name}' not found")
