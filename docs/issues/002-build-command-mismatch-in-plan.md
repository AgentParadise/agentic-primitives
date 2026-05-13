# 002 — Plan referenced wrong build command for the workspace image

**Type:** docs, plan-correction
**Priority:** low (already resolved by subagent autonomy; capture for future plans)
**Captured:** 2026-05-12 · Phase B of workspace-injection-contract

## Problem

The plan at `docs/superpowers/plans/2026-05-12-workspace-injection-contract.md` Phase B and Phase E reference:

```bash
docker build -t agentic-workspace-claude-cli:latest providers/workspaces/claude-cli
```

That `docker build` invocation fails because the Dockerfile expects a staged build context this repo doesn't ship in raw form. The actual canonical command is:

```bash
uv run scripts/build-provider.py claude-cli
```

The Phase B subagent used the canonical command and built cleanly. The plan wasn't updated.

## Sketch

Update plan Task B.2 Step 3 and plan Task E.2 Step 2 to reference `uv run scripts/build-provider.py claude-cli`. Optionally tag a specific version with `--tag <version>` (read `scripts/build-provider.py --help` for actual flag).

Also worth documenting in `docs/workspace.md` (Phase D) or the top-level README so the build command is discoverable.

## Acceptance

- Plan corrected.
- `docs/workspace.md` mentions the canonical build command in its "Pointers" or "Building the image" section.

## Related

- Build script: `scripts/build-provider.py`
- Plan: `docs/superpowers/plans/2026-05-12-workspace-injection-contract.md`
