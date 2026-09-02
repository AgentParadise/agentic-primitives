"""Tests for claude_cli_contract_canary.py's check_contract().

check_contract() is fed synthetic stream-json fixtures instead of a real
`claude` invocation (this canary is designed to only run against a real,
authenticated CLI -- see the script's docstring). What matters here isn't
that the fixture round-trips (the object you just built passing a check
about itself proves nothing) -- it's that when a field the canary's own
docstring/REQUIRED_*_FIELDS claims to check is missing from the fixture fed
to check_contract(), check_contract() actually raises. That is the thing
event_parser.py's silent `.get(..., default)` reads would NOT catch, and
the thing the canary exists to catch instead.

Every mutation test below deletes exactly one field the canary claims to
require and asserts ContractViolation. Before the corresponding fix, the
mutations touching `usage` (assistant.message.usage, result.usage) and
`is_error` (tool_result) passed through check_contract() silently -- these
tests would have failed (no exception raised) against that code.
"""

import copy
import json
import sys
from pathlib import Path

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from claude_cli_contract_canary import ContractViolation, check_contract


def _baseline_events() -> list[dict]:
    """A complete, contract-conforming synthetic session.

    Includes a regular tool call (Bash) and a subagent call (Agent) so
    check_contract()'s subagent_count assertion is also satisfied.
    """
    return [
        {"type": "system", "subtype": "init", "tools": ["Bash", "Agent", "Read"]},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Bash",
                        "input": {"command": "echo canary-subagent"},
                    }
                ],
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_1",
                        "is_error": False,
                        "content": "canary-subagent",
                    }
                ]
            },
        },
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_2",
                        "name": "Agent",
                        "input": {"description": "run canary subtask"},
                    }
                ],
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 8,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_2",
                        "is_error": False,
                        "content": "done",
                    }
                ]
            },
        },
        {
            "type": "result",
            "is_error": False,
            "total_cost_usd": 0.01,
            "duration_ms": 100,
            "duration_api_ms": 80,
            "num_turns": 2,
            "usage": {
                "input_tokens": 30,
                "output_tokens": 13,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        },
    ]


def _lines(events: list[dict]) -> list[str]:
    return [json.dumps(e) for e in events]


def test_baseline_fixture_passes() -> None:
    """A complete fixture with every claimed field present must pass.

    Control for the mutation tests below: if this fails, a mutation test
    "passing" (raising ContractViolation) wouldn't prove the mutation was
    the cause.
    """
    check_contract(_lines(_baseline_events()))


# (description, event index in _baseline_events(), mutator applied to a deep
# copy of that event). Each mutator removes exactly one field the canary
# claims to check (docstring + REQUIRED_TOP_LEVEL_FIELDS/REQUIRED_TOOL_USE_FIELDS/
# REQUIRED_TOOL_RESULT_FIELDS/REQUIRED_USAGE_FIELDS) and nothing else.
MUTATIONS = [
    ("assistant top-level: message", 1, lambda e: e.pop("message")),
    ("user top-level: message", 2, lambda e: e.pop("message")),
    ("result top-level: is_error", 5, lambda e: e.pop("is_error")),
    ("result top-level: total_cost_usd", 5, lambda e: e.pop("total_cost_usd")),
    ("result top-level: duration_ms", 5, lambda e: e.pop("duration_ms")),
    ("result top-level: duration_api_ms", 5, lambda e: e.pop("duration_api_ms")),
    ("result top-level: num_turns", 5, lambda e: e.pop("num_turns")),
    ("result top-level: usage", 5, lambda e: e.pop("usage")),
    ("assistant.message: usage", 1, lambda e: e["message"].pop("usage")),
    ("tool_use: id", 1, lambda e: e["message"]["content"][0].pop("id")),
    ("tool_use: name", 1, lambda e: e["message"]["content"][0].pop("name")),
    ("tool_use: input", 1, lambda e: e["message"]["content"][0].pop("input")),
    ("tool_result: tool_use_id", 2, lambda e: e["message"]["content"][0].pop("tool_use_id")),
    ("tool_result: is_error", 2, lambda e: e["message"]["content"][0].pop("is_error")),
    (
        "assistant.message.usage: input_tokens",
        1,
        lambda e: e["message"]["usage"].pop("input_tokens"),
    ),
    (
        "assistant.message.usage: output_tokens",
        1,
        lambda e: e["message"]["usage"].pop("output_tokens"),
    ),
    (
        "assistant.message.usage: cache_creation_input_tokens",
        1,
        lambda e: e["message"]["usage"].pop("cache_creation_input_tokens"),
    ),
    (
        "assistant.message.usage: cache_read_input_tokens",
        1,
        lambda e: e["message"]["usage"].pop("cache_read_input_tokens"),
    ),
    ("result.usage: input_tokens", 5, lambda e: e["usage"].pop("input_tokens")),
    ("result.usage: output_tokens", 5, lambda e: e["usage"].pop("output_tokens")),
    (
        "result.usage: cache_creation_input_tokens",
        5,
        lambda e: e["usage"].pop("cache_creation_input_tokens"),
    ),
    (
        "result.usage: cache_read_input_tokens",
        5,
        lambda e: e["usage"].pop("cache_read_input_tokens"),
    ),
]


@pytest.mark.parametrize("description,index,mutate", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_missing_required_field_is_a_contract_violation(description, index, mutate) -> None:
    events = copy.deepcopy(_baseline_events())
    mutate(events[index])
    with pytest.raises(ContractViolation):
        check_contract(_lines(events))
