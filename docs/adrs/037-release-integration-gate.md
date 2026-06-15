---
title: "ADR-037: Release Integration Gate"
status: draft
created: 2026-06-15
updated: 2026-06-15
author: NeuralEmpowerment
tags: [ci, release, workspace, claude-cli, integration-tests, supply-chain]
---

# ADR-037: Release Integration Gate

## Status

**Draft**

- Created: 2026-06-15
- Updated: 2026-06-15
- Author(s): NeuralEmpowerment

## Context

The `claude-cli` workspace container is built, pushed to GHCR, and cosign-signed
on every push to `main` by `build-workspace-images.yml`. That workflow has **no
test step** — it ships the container without ever running the integration tests
(`tests/integration/test_entrypoint_memory.py`,
`tests/integration/test_entrypoint_workspace_injection.py`) against it.

Those integration tests are the only coverage that exercises the real entrypoint
end-to-end, including the path-traversal / injection hardening added in PR #170
(see [ADR-035](035-workspace-injection-contract.md),
[ADR-036](036-memory-primitive-and-doctor.md)). `qa.yml` explicitly
`--ignore=tests/integration`, so today they run **only** when a human builds the
image and runs them locally. A regression in the entrypoint or memory-injection
surface would reach a signed, published container undetected.

There is no separate release branch: plugins release off `main` via
`plugin-tag.yml`, and the container publishes off `main` via
`build-workspace-images.yml`. So `main` is the correct place for the gate, not a
release-branch promotion step.

## Decision

Add a **publish-blocking integration gate** to `build-workspace-images.yml`.

On push to `main`:

```
job: integration-gate (claude-cli)
   stage context  -> docker build --load (linux/amd64, single-arch)
   -> uv sync --all-extras  (lib/python/agentic_isolation)
   -> pytest tests/integration            # lean: ~15 run, 4 hindsight-dependent skip
job: build-push  [needs: integration-gate]
   -> existing multi-arch build + push + cosign-sign   # runs only if gate is green
```

A broken container never gets pushed or signed. The merge is already on `main`
(fix-forward model), but nothing ships until the gate passes.

### Structure considered

- **A (chosen):** one gate job inside `build-workspace-images.yml`, with the
  publish job depending on it via `needs:`. Same workflow, same event, genuine
  blocking.
- **B (rejected):** a separate `integration-gate.yml` wired via `workflow_run`.
  Cross-workflow gating runs *after* the publish workflow, so it cannot block the
  same push; it degrades to detect-after, which was explicitly not wanted.
- **C (rejected):** fold integration tests into `qa.yml`. Wrong altitude:
  `qa.yml` has no Docker/image-build layer, and it would slow every PR.

### Scope

- **Provider:** the integration suite targets `claude-cli`'s entrypoint /
  memory surface. The gate runs that suite once and, as a job dependency
  (`needs:`), blocks the entire publish stage — both `claude-cli` and
  `interactive-tmux`. Per-provider gating (matrix-conditional `needs`) was
  rejected as fragile; holding the `interactive-tmux` publish when the shared
  build tree is in a failing state is the conservative, safe choice.
- **Triggers:** runs on push to `main` (blocks publish) and on PRs matching the
  workflow's existing path filter (`providers/workspaces/**`, `plugins/**`,
  `lib/python/**`, `scripts/build-provider.py`), where it is informational —
  nothing publishes on a PR, but the early signal is free.
- **Coverage:** lean. No hindsight backend is stood up; the 4 backend-dependent
  tests skip. All traversal / injection / doctor-fail hardening (the security
  surface motivating the gate) runs without a backend.

### Build/test mechanics

- The gate builds **single-arch `linux/amd64` with `--load`** so the image is
  available to the local Docker daemon for `docker run`; multi-arch buildx output
  is not loadable into the daemon.
- The integration tests resolve the image via `AGENTIC_WORKSPACE_IMAGE` (default
  `agentic-workspace-claude-cli:latest`); the gate tags its loaded build to match.
- The gate's amd64 build and the publish job's multi-arch build share the
  existing `type=gha` BuildKit cache, so the gate warms the publish build rather
  than doubling cost.
- Test deps come from `uv sync --all-extras` in `lib/python/agentic_isolation`
  (installs the `docker` + `dev` extras: pytest, pytest-asyncio, docker SDK).

## Consequences

### Positive

- A push to `main` that breaks the entrypoint/memory surface fails the
  `integration-gate` job and **does not** publish or sign a container.
- A clean push to `main` runs the gate green, then publishes + signs as today.
- PRs touching the relevant paths get early integration signal for free.

### Negative / trade-offs

- Fix-forward only: a regression still lands on `main` (the merge is done); the
  gate prevents *publishing* it, not *merging* it.
- Adds bounded wall-clock to the `main` pipeline (one amd64 build + the suite).

### Future enhancements

- **Pre-merge prevention.** Because the gate is post-merge, a regression still
  lands on `main` before publish is blocked. A path-filtered *pre-merge* required
  check on the relevant PRs (`providers/workspaces/**`, `lib/python/**`,
  `scripts/build-provider.py`) would prevent the merge itself, closing the
  fix-forward window. Deferred to keep the PR loop fast for unrelated changes;
  revisit if regressions actually reach `main`.

### Out of scope (YAGNI)

- Standing up a hindsight backend for the 4 skipped tests — phase-2 follow-up
  once the gate is proven stable.
- Gating `plugin-tag.yml` — plugins do not depend on the container.
- Integration tests for the `interactive-tmux` provider — no such suite exists.
- Installing `pytest-timeout` (the integration tests reference a `timeout`
  option but the plugin is absent — harmless warning today; separate cleanup).
