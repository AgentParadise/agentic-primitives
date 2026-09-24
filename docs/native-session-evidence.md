# Native session evidence

`EvidenceHarnessPlugin` extends the existing harness registry with an optional,
pure `evidence_reader()` capability. It accepts exact JSONL bytes and returns
native identity, root context, structured relationship references, line locations,
extractor version, and explicit issues. It does not assign runs, authorize access,
price work, register invocations, or certify capture completeness.

Consumers must retain the source byte hash and apply their own evidence policy.
The Syntropic137 adapter translates these facts through `NativeSessionEvidencePort`;
its central resolver owns membership, provenance, contradictions, and coverage.
An unsupported harness returns no capability rather than a guessed identity.

## Format anchors

The workspace currently pins Claude Code 2.1.281 and Codex 0.156.1 in
`providers/workspaces/omni-agent/Dockerfile`. Extraction uses these mechanisms:

- Claude: `sessionId` for root context; `agentId` with `isSidechain` for a
  child's native `agent-<id>` identity; unique `Agent`/`Task` tool-use and
  tool-result IDs paired with `toolUseResult.agentId` for immediate parentage.
  A shared `sessionId` never makes every descendant a direct root child.
- Codex: the first `session_meta` header identifies the current transcript.
  Later copied headers cannot replace it. Explicit subagent parent and fork
  fields remain separate relationship types. See the pinned
  [Codex protocol source](https://github.com/openai/codex/blob/rust-v0.156.1/codex-rs/protocol/src/protocol.rs).
  Between 0.150.1 and 0.156.1 `SessionMeta` only gained
  `forked_from_ordinal_exclusive` and `runtime_workspace_roots`; the fields
  this reader uses are unchanged.

`tests/test_native_evidence.py` uses content-free structural fixtures for these
mechanisms, including depth three, missing bodies, duplicate calls, conflicting
identities, copied fork history, and malformed headers. Claude shapes were
reproduced from the local lineage experiment described in Syntropic137 #1398;
no conversation text or credentials are embedded in fixtures.

## Bounds and trust

Readers reject documents above 16 MiB or 100,000 lines and report lines above
1 MiB individually. Invalid records produce issues; an unreadable leading Codex
header cannot cause an inherited ancestor to become the selected identity.
Call-result references remain evidence even if the referenced child body is
absent. They are observed native facts, not independent host attestations.

These readers alone do not cover pre-launch native child registration, durable
spooling, background descendant completion, or cross-harness shell delegation.
Those require their corresponding capture and registration integrations before
a consumer may declare complete supported-launch coverage.
# Captured envelopes

Claude and Codex evidence readers also expose `extract_envelope`. This validates
the envelope's harness, source format, and session identity against native facts.
Conflicts yield an explicit gap instead of assigning the claimed identity.
For array-valued Codex payloads, line references identify logical rows. Callers
must archive the original envelope bytes; normalized rows are extraction input
and do not replace the archival representation.
