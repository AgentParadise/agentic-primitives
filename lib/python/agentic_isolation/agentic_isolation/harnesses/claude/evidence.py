"""Claude Code native identity and structured Agent/Task call-result references.

A sidechain's sessionId is the containing root, not its own native identity or
immediate parent. The immediate parent comes from the paired tool call/result
in the owning transcript. Missing children do not erase this reference.
"""

from __future__ import annotations

from collections import defaultdict

from pydantic import Field

from agentic_isolation.harnesses.evidence import NativeEvidence, NativeLink, WireModel, read_rows


class _Block(WireModel):
    type: str = ""
    name: str | None = None
    id: str | None = None
    tool_use_id: str | None = None


class _Message(WireModel):
    content: list[_Block] | str | None = None


class _Result(WireModel):
    agent_id: str | None = Field(default=None, alias="agentId")


class _Row(WireModel):
    session_id: str | None = Field(default=None, alias="sessionId")
    agent_id: str | None = Field(default=None, alias="agentId")
    sidechain: bool = Field(default=False, alias="isSidechain")
    message: _Message | None = None
    result: _Result | str | list[object] | None = Field(default=None, alias="toolUseResult")


def _identity(rows: tuple[tuple[int, _Row], ...]) -> tuple[str | None, str | None, tuple[int, ...]]:
    roots = {row.session_id for _, row in rows if row.session_id}
    children = {row.agent_id for _, row in rows if row.sidechain and row.agent_id}
    if len(roots) != 1 or len(children) > 1:
        return None, None, ()
    root = next(iter(roots))
    native = "agent-" + next(iter(children)) if children else root
    first_root = next(index for index, row in rows if row.session_id == root)
    first_child = next((index for index, row in rows if row.sidechain and row.agent_id), first_root)
    lines = tuple(sorted({first_root, first_child}))
    return native, root, lines


def _links(
    native: str, rows: tuple[tuple[int, _Row], ...]
) -> tuple[tuple[NativeLink, ...], tuple[str, ...]]:
    calls: dict[str, list[int]] = defaultdict(list)
    results: dict[str, list[tuple[int, str | None]]] = defaultdict(list)
    for index, row in rows:
        blocks = row.message.content if row.message else None
        if not isinstance(blocks, list):
            continue
        result_count = sum(block.type == "tool_result" for block in blocks)
        for block in blocks:
            if block.type == "tool_use" and block.name in ("Agent", "Task") and block.id:
                calls[block.id].append(index)
            elif block.type == "tool_result" and block.tool_use_id:
                child = (
                    row.result.agent_id
                    if isinstance(row.result, _Result) and result_count == 1
                    else None
                )
                results[block.tool_use_id].append((index, child))
    links: list[NativeLink] = []
    issues: list[str] = []
    for call_id, locations in sorted(calls.items()):
        matches = results[call_id]
        if len(locations) != 1 or len(matches) != 1 or not matches[0][1]:
            issues.append(f"unresolved_spawn:{call_id}")
            continue
        result_line, child_id = matches[0]
        assert child_id is not None
        links.append(
            NativeLink(
                parent_id=native,
                child_id="agent-" + child_id,
                relation="spawn",
                basis="parent_call_result",
                mechanism="claude-agent-call-result",
                lines=(locations[0], result_line),
                call_id=call_id,
            )
        )
    return tuple(links), tuple(issues)


class ClaudeNativeEvidenceReader:
    def extract_envelope(self, content: bytes) -> NativeEvidence:
        from ..envelope_evidence import extract_envelope

        return extract_envelope(
            content, self, agent="ClaudeCode", source_format="claude-code-jsonl"
        )

    def extract(self, content: bytes) -> NativeEvidence:
        rows, issues = read_rows(content, _Row)
        native, root, locations = _identity(rows)
        if native is None:
            return NativeEvidence(
                native_id=None, issues=(*issues, "identity_missing_or_conflicting")
            )
        links, link_issues = _links(native, rows)
        return NativeEvidence(
            native_id=native,
            root_id=root,
            identity_lines=locations,
            links=links,
            issues=(*issues, *link_issues),
            extractor_version="claude-native-evidence/1",
        )
