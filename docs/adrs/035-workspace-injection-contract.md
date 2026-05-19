---
title: "ADR-035: Workspace Injection Contract"
status: accepted
created: 2026-05-12
updated: 2026-05-12
author: NeuralEmpowerment
tags: [workspace, isolation, contracts, agentic-isolation, claude-cli]
---

# ADR-035: Workspace Injection Contract

## Status

**Accepted**

- Created: 2026-05-12
- Updated: 2026-05-12
- Author(s): NeuralEmpowerment

## Context

Multiple orchestrators run AI agents inside the
`agentic-workspace-claude-cli` image:

- [agentic-domain-runner](https://gitea.neuralempowerment.xyz/HomeLab/agentic-domain-runner)
  — homelab Rust service, one workspace per task.
- [Syntropic137](https://github.com/AgentParadise/syntropic137) — Python
  platform, one workspace per workflow phase.
- Future Codex / Gemini wrappers.

Each one needs to hand a workspace its **context** (a `CLAUDE.md` describing
the job), its **plugins** (skills, commands, hooks), and its **subagents**
(specialized assistants with their own tools and prompts) before the agent
starts.

Before this ADR, every orchestrator reinvented the staging mechanism:

- agentic-domain-runner uses a bind-mount + a Rust `FileStager` port +
  a `BindMountFileStager` adapter.
- Syntropic137 generates CLAUDE.md in Python, fetches plugins from MinIO,
  and uses `docker put_archive` to inject everything post-create /
  pre-start.

Both work. Neither is shared. As more orchestrators land, drift and
divergence become harder to walk back. Agents experience subtly
different workspaces depending on which orchestrator launched them.

There's also growing pressure from the agentic-domain-runner's
[per-domain context injection design](https://gitea.neuralempowerment.xyz/HomeLab/agentic-domain-runner/src/branch/main/docs/superpowers/specs/2026-05-12-per-domain-context-injection-design.md):
its runner-side implementation already speaks an `AGENTIC_DOMAIN_*` (later
renamed to `AGENTIC_WORKSPACE_*`) env-var dialect against a
`/etc/agentic/workspace/` bind-mount path, but the workspace image hasn't
implemented the corresponding entrypoint behavior. The contract exists in
the runner's head only.

`agentic-primitives` owns the workspace image. That's the right home for a
shared contract: it's the only layer that can see what's inside
`/opt/agentic/plugins/` (baked-in plugins live there) and the only layer
whose entrypoint runs inside every workspace regardless of who launched it.

## Decision

The `agentic-workspace-claude-cli` image exposes a small **inbound injection
contract** that all orchestrators target. Three components land:

1. **Entrypoint section 5.5 — workspace context composition.**
   Reads from a read-only bind-mount at `/etc/agentic/workspace/` and three
   optional env vars (`AGENTIC_WORKSPACE_CONTEXT`, `AGENTIC_WORKSPACE_PLUGINS`,
   `AGENTIC_WORKSPACE_AGENTS`). Copies content into the agent-visible
   workspace and appends to `AGENTIC_PLUGIN_FLAGS`. Backwards-compatible —
   silent no-op when the bind-mount is absent.

2. **`WorkspaceFiles` Python helper** in `agentic_isolation`. Exposes
   `bind_mount(host, ctr, read_only)` and `inject(container_id, ctr_path,
   content)` as the two complementary staging primitives. Library import
   only — no new process, no daemon.

3. **Canonical docs** — `docs/workspace.md` describing the boundary and the
   three responsibilities (inject / isolate / observe), README section
   pointing at it, this ADR capturing the durable decisions.

**What is explicitly NOT in the contract:**

- **Tool restrictions** as a separate env var. They live inside subagent
  frontmatter (`tools: [Read, Bash, ...]`) or plugin permission settings —
  the policy travels with the agent that enforces it. Adding
  `AGENTIC_WORKSPACE_ALLOWED_TOOLS` would duplicate state and invite drift.
- **Identity vars** like task id, session id, runner URL, read tokens.
  Those are orchestrator-specific. The runner sets them on its containers;
  the workspace image doesn't know or care. They're part of each
  orchestrator's contract with its own agents, not the workspace contract.
- **Preamble templating.** The orchestrator pre-composes the agent-visible
  CLAUDE.md (preamble + content) before bind-mounting; the entrypoint just
  copies it through verbatim.

## Alternatives Considered

### Alternative 1: Bake everything into the workspace image at build time

**Description**: One image per workspace profile — `agentic-workspace-homelab`,
`agentic-workspace-syntropic-research`, etc. — with CLAUDE.md and plugins
baked in at build time.

**Pros**:
- Zero runtime composition; image is the source of truth.
- No bind-mount layer to debug.

**Cons**:
- Image rebuild per content change (Docker layer cache helps but the
  feedback loop is still slower than file copies).
- N images to maintain instead of one.
- Doesn't support per-task customization (the runner attaches per-task
  volumes; we'd need per-task images, which defeats the purpose).

**Reason for rejection**: Iteration tempo and per-task customization. The
homelab use case routinely tweaks domain CLAUDE.md mid-task; a rebuild
loop there is unacceptable.

---

### Alternative 2: Each orchestrator implements its own injection

**Description**: No shared contract. Each orchestrator (runner, Syntropic137,
future ones) writes its own injection mechanism against the workspace image's
filesystem.

**Pros**:
- No coupling between orchestrators.
- Each orchestrator chooses the right shape for its needs.

**Cons**:
- Drift over time as orchestrators evolve independently.
- Agents experience subtly different workspaces — observability and
  debugging suffer.
- Onboarding cost for new orchestrators (reverse-engineer existing ones to
  match conventions).

**Reason for rejection**: We already feel the drift between
agentic-domain-runner and Syntropic137. One shared contract is cheap to
maintain and pays dividends in consistent agent experience.

---

### Alternative 3: Add `AGENTIC_WORKSPACE_ALLOWED_TOOLS` to the contract

**Description**: Include a fourth env var for orchestrator-supplied tool
allowlists, expanded by the entrypoint into a `--allowedTools X --allowedTools
Y` flag string the cmd wrapper can shell-expand.

**Pros**:
- One uniform mechanism for orchestrators to lock down tool access.
- Convenient if you want a coarse, per-workspace policy without writing
  subagent definitions.

**Cons**:
- Duplicates state with subagent frontmatter `tools:` and plugin
  permissions — two places to keep consistent.
- Locks the contract to a Claude-specific concept; Codex / Gemini
  workspaces will need different mechanisms.
- Pushes policy further from where it's enforced, encouraging drift.

**Reason for rejection**: Subagents are the right level of abstraction.
Tool restrictions belong to the agent that enforces them. See
[Claude subagents docs](https://code.claude.com/docs/en/sub-agents.md).

---

### Alternative 4: Pre-compose + inject only (drop the bind-mount)

**Description**: Always require orchestrators to use `WorkspaceFiles.inject()`;
no bind-mount path. Single mechanism.

**Pros**:
- Works against any Docker daemon (remote, K8s) without changes.
- One code path to test.

**Cons**:
- Forces a `docker put_archive` round trip per container per file, even
  for content that's already on the host filesystem.
- Awkward for orchestrators whose content is already host-resident
  (homelab runner with checked-in domain dirs).
- Bind-mount is genuinely cheaper when daemon and orchestrator share a
  filesystem.

**Reason for rejection**: Both mechanisms have legitimate uses. The
contract supports both via the entrypoint's read of `/etc/agentic/workspace/`
(populated by either method).

## Consequences

### Positive Consequences

- **One contract, multiple consumers.** Runners and platforms target the
  same env vars and paths. New orchestrators target the contract instead
  of reinventing the seam.
- **Tool-restriction policy travels with the agent**, not in a separate
  env-var concept. Less drift, more cohesion.
- **Contract is small enough to fit on one page** (`docs/workspace.md`) —
  discoverable, learnable.
- **Backwards-compatible.** Existing deployments that don't bind-mount
  `/etc/agentic/workspace/` continue working unchanged.
- **Path for non-Claude providers exists.** Future
  `agentic-workspace-codex-cli` would carry its own equivalent of section
  5.5 with appropriate Codex-native paths (`CODEX.md`, etc.); the
  pattern transfers.

### Negative Consequences

- **Cross-repo coordination.** Phase A in agentic-domain-runner has to
  land alongside Phase B–D here, with a follow-on image bump (Phase E).
  Captured in the implementation plan.
- **Image-layer coupling.** The workspace image's behavior is now part of
  every orchestrator's deployment surface. Image bumps need to be
  coordinated; spec-drift surfaces as image-version-dependent behavior.

### Neutral Consequences

- **`AGENTIC_PLUGIN_FLAGS` env var** stays — existing baked-in plugin
  discovery (entrypoint section 2) is unchanged; per-workspace plugins
  append to the same variable.
- **Pre-existing LSP test bug** surfaced during Phase B
  ([docs/issues/001](../issues/001-lsp-entrypoint-test-stdout-pollution.md))
  — not caused by this work but discovered alongside.

## Implementation Notes

**Plan:**
[`docs/superpowers/plans/2026-05-12-workspace-injection-contract.md`](../superpowers/plans/2026-05-12-workspace-injection-contract.md).
Five phases:

- **A** — env rename in agentic-domain-runner
  (`AGENTIC_DOMAIN_*` → `AGENTIC_WORKSPACE_*`; path
  `/etc/agentic/domain/` → `/etc/agentic/workspace/`;
  `AGENTIC_ALLOWED_TOOLS` removed entirely).
- **B** — entrypoint section 5.5 in `providers/workspaces/claude-cli/scripts/entrypoint.sh`
  + 6 integration tests in `tests/integration/test_entrypoint_workspace_injection.py`.
- **C** — `WorkspaceFiles` helper in
  `lib/python/agentic_isolation/agentic_isolation/workspace_files.py`
  + unit tests + package-root export.
- **D** — `docs/workspace.md`, README section, this ADR.
- **E** — image build/tag, runner image-tag bump, previously-blocked
  live Claude smoke.

**Breaking changes:** orchestrators still using `AGENTIC_DOMAIN_*` env vars
or `/etc/agentic/domain/` paths break at the next image bump. Migration
is a one-line sed (captured in agentic-domain-runner's Phase A commit
`d7e0516`).

**Build:**

```bash
just build-workspace-claude-cli
# or
uv run scripts/build-provider.py claude-cli
```

## References

- Design spec:
  [`docs/superpowers/specs/2026-05-12-workspace-injection-contract-design.md`](../superpowers/specs/2026-05-12-workspace-injection-contract-design.md)
- Plan:
  [`docs/superpowers/plans/2026-05-12-workspace-injection-contract.md`](../superpowers/plans/2026-05-12-workspace-injection-contract.md)
- Canonical doc: [`docs/workspace.md`](../workspace.md)
- Sibling spec (runner / consumer side):
  [agentic-domain-runner per-domain context injection](https://gitea.neuralempowerment.xyz/HomeLab/agentic-domain-runner/src/branch/main/docs/superpowers/specs/2026-05-12-per-domain-context-injection-design.md)
- [Claude subagents](https://code.claude.com/docs/en/sub-agents.md) — the
  replacement mechanism for per-workspace tool restrictions
- ADR-027: Provider Workspace Images — the precedent ADR for per-provider
  workspace images
- ADR-033: Plugin-Native Workspace Images — the precedent for baked-in
  plugin discovery (entrypoint section 2), which section 5.5 extends
