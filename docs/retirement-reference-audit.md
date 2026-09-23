# Agentic Primitives retirement reference audit

Date: 2026-09-22

This is the extraction baseline, not archive approval. Repeat the audit after
two signed Agentic Workspace releases and the first Syntropic137 release that
consumes them.

## Search scope

GitHub code search covered the `AgentParadise` and `syntropic137`
organizations for both canonical reference forms:

```text
"AgentParadise/agentic-primitives"
"lib/agentic-primitives"
```

Results were classified by whether the default-branch file controls a current
build or runtime. Historical plans, immutable experiment records, source
attribution, and compatibility provenance are references, but are not active
consumers.

## Baseline classification

| Repository | Classification | Retirement action |
|---|---|---|
| `syntropic137/syntropic137` | **Active consumer.** Default-branch submodule, editable dependencies, image build inputs, image provenance policy, CI, and operator docs still name Agentic Primitives. | Merge and release the staged Agentic Workspace cutover. Verify signed image digests and rollback before changing this row to cleared. |
| `syntropic137/syntropic137-claude-plugin` | **Active operational documentation.** The setup skill directs developers to inspect `lib/agentic-primitives`. | Update with the Syntropic cutover release. |
| `AgentParadise/agentic-primitives` | **Expected compatibility owner.** Legacy workflows, provider manifests, plugin metadata, and migration documentation remain live during the rollback window. | Disable legacy publishing only after downstream cutover. Preserve migration redirects when archiving. |
| `AgentParadise/agentic-workspace` | **Compatibility provenance, not an external consumer.** Frozen plugin metadata records the extraction source while images preserve the legacy plugin surface. | Replace frozen copies with generated adapters when private cross-repository authentication exists. Historical source fields may remain. |
| `AgentParadise/agentic-skills` | **Source attribution, not an external consumer.** Three extracted skills link to their original source. | No runtime migration required. Keep attribution unless links become misleading. |
| `AgentParadise/agentic-memory` | **Documentation and copied-skill attribution.** References point to original designs or the source of a copied experiment skill. | Prefer canonical Agentic Skills links when that skill is next revised. Not an archive blocker by itself. |
| `AgentParadise/agent-paradise-standards-system` | **Example fixture.** Two code-topology examples contain the old path as sample input. | No runtime migration required. |
| `AgentParadise/experiments` and `syntropic137/spec-store` | **Historical records.** Matches are archived experiments, plans, transcripts, and handoffs. | Preserve as historical evidence. Do not rewrite immutable records. |
| `syntropic137/session-learning-loop` | **Historical finding.** One experiment report names the source repository. | Preserve as historical evidence. |

## Final archive recheck

1. Search both organizations again for the two canonical forms above.
2. Inspect `.gitmodules`, dependency lockfiles, workflow files, Dockerfiles,
   image labels, Sigstore identities, package settings, and marketplace data.
3. Require zero default-branch build or runtime dependency on Agentic
   Primitives. Historical and provenance references must be labeled as such.
4. Record the two successful Workspace releases, the Syntropic release, its
   production-like acceptance run, and its rollback evidence.
5. Archive only after an owner signs the completed recheck.

