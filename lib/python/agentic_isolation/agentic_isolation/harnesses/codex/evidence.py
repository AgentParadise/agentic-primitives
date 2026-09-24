"""Codex rollout header references, pinned against rust-v0.156.1 protocol.rs.

Only the first session_meta is the current thread header. Later metadata may
belong to inherited fork history and must never replace this identity.
"""

from __future__ import annotations

from agentic_isolation.harnesses.evidence import NativeEvidence, NativeLink, WireModel, read_rows


class _Spawn(WireModel):
    parent_thread_id: str


class _Subagent(WireModel):
    thread_spawn: _Spawn | None = None


class _Source(WireModel):
    subagent: _Subagent | str | None = None


class _Meta(WireModel):
    id: str | None = None
    session_id: str | None = None
    multi_agent_version: str | None = None
    parent_thread_id: str | None = None
    forked_from_id: str | None = None
    source: _Source | str | None = None


class _Row(WireModel):
    type: str
    payload: _Meta | None = None


class CodexNativeEvidenceReader:
    def extract_envelope(self, content: bytes) -> NativeEvidence:
        from ..envelope_evidence import extract_envelope

        return extract_envelope(content, self, agent="Codex", source_format="codex-rollout-jsonl")

    def extract(self, content: bytes) -> NativeEvidence:
        rows, issues = read_rows(content, _Row)
        headers = [(line, row.payload) for line, row in rows if row.type == "session_meta"]
        if not headers:
            return NativeEvidence(native_id=None, issues=(*issues, "identity_missing"))
        line, meta = headers[0]
        # A malformed leading header must not hand identity to copied history.
        if any(int(issue.rsplit(":", 1)[1]) < line for issue in issues if ":" in issue):
            return NativeEvidence(native_id=None, issues=(*issues, "canonical_header_unreadable"))
        if meta is None:
            return NativeEvidence(native_id=None, issues=(*issues, "canonical_header_unreadable"))
        native = meta.id if meta.multi_agent_version == "v2" else meta.session_id or meta.id
        if not native or (
            meta.multi_agent_version != "v2"
            and meta.session_id
            and meta.id
            and meta.session_id != meta.id
        ):
            return NativeEvidence(
                native_id=None, issues=(*issues, "identity_missing_or_conflicting")
            )
        parents = {meta.parent_thread_id} if meta.parent_thread_id else set()
        if isinstance(meta.source, _Source) and isinstance(meta.source.subagent, _Subagent):
            spawn = meta.source.subagent.thread_spawn
            if spawn is not None:
                parents.add(spawn.parent_thread_id)
        links = tuple(
            NativeLink(
                parent_id=parent,
                child_id=native,
                relation="spawn",
                basis="child_header",
                mechanism="codex-session-meta",
                lines=(line,),
            )
            for parent in sorted(parents)
        )
        if meta.forked_from_id:
            links += (
                NativeLink(
                    parent_id=meta.forked_from_id,
                    child_id=native,
                    relation="fork",
                    basis="child_header",
                    mechanism="codex-session-meta",
                    lines=(line,),
                ),
            )
        return NativeEvidence(
            native_id=native,
            root_id=meta.session_id if meta.multi_agent_version == "v2" else None,
            identity_lines=(line,),
            links=links,
            issues=(*issues, *(("parent_identity_conflict",) if len(parents) > 1 else ())),
            extractor_version="codex-native-evidence/2",
        )
