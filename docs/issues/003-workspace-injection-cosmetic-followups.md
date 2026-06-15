# 003 — Workspace injection cosmetic follow-ups

**Type:** cleanup, low-priority
**Priority:** low
**Captured:** 2026-05-12 · Final review of workspace-injection-contract surfaced these

## Problem

Two non-blocking cosmetic notes from the final reviewer on the merged
`feat/workspace-injection-contract` branch:

### 3.1 — Empty `/workspace/.agentic-plugins/` directory when plugins/ mount is empty

In `providers/workspaces/claude-cli/scripts/entrypoint.sh` section 5.5,
the entrypoint does `mkdir -p "${INJECT_TARGET_PLUGINS}"` before the
plugin-discovery loop. When `/etc/agentic/workspace/plugins/` is mounted
but contains no valid plugin directories (or `AGENTIC_WORKSPACE_PLUGINS`
filters to zero matches), the `mkdir` still runs — leaving an empty
`/workspace/.agentic-plugins/` directory.

Harmless functionally; the agent just sees an empty dir. Cosmetic.

**Sketch:** move the `mkdir` inside the read-loop so it only fires the
first time a valid plugin is about to be copied. Use a sentinel or just
move `mkdir -p` to right before the `cp -a`.

### 3.2 — `WorkspaceFiles.inject()` requires parent dir to exist

`lib/python/agentic_isolation/agentic_isolation/workspace_files.py`'s
`inject()` calls `container.put_archive(parent, archive)`. If the parent
directory doesn't exist inside the container, `put_archive` errors —
but the helper doesn't document this requirement.

**Sketch:** add a one-line note to `inject()`'s docstring:

> The container_path's parent directory must already exist inside the
> container; `put_archive` does not create intermediate directories.
> Bind-mount a base path or create the parent via `container.exec_run`
> first if it doesn't.

Alternatively, the helper could `exec_run("mkdir -p <parent>")` before
the put_archive — but that's scope creep ("primitives only" per spec §6
discipline). Doc note is the right call.

## Acceptance

- 3.1: empty `/workspace/.agentic-plugins/` dir is not created when no
  plugins are copied. Integration test
  `test_entrypoint_skips_when_no_workspace_mount` should keep passing.
  Optional new test: `test_entrypoint_does_not_create_empty_plugins_dir`.
- 3.2: docstring on `inject()` mentions the parent-dir requirement.

## Related

- ADR-035: workspace injection contract
- `docs/workspace.md`
- Phase B/C of the implementation plan
