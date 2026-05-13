# 001 — LSP entrypoint test stdout pollution

**Type:** bug, pre-existing
**Priority:** low
**Captured:** 2026-05-12 · Phase B of workspace-injection-contract surfaced it

## Problem

`tests/integration/test_entrypoint_lsp_settings.py` has two failing tests that are not caused by current work:

- `test_entrypoint_enables_lsp_plugins`
- `test_entrypoint_settings_has_hooks`

Both call `json.loads(result.stdout)` against the output of a `docker run … cat /home/agent/.claude/settings.json` invocation. The entrypoint prints log lines like `[entrypoint] Discovered plugin: …` on stdout before `cat` runs, so the captured stdout starts with non-JSON text and `json.loads` throws.

Verified pre-existing: `git stash` of Phase B's changes + re-run shows the same two failures.

## Sketch

Two options:

1. Make the entrypoint's discovery logs go to stderr, not stdout. Cleanest — separates structured output (CMD stdout) from operational logs. One-line change: `echo "[entrypoint] …" >&2` everywhere in the discovery loop.
2. Update the affected tests to strip non-JSON prefix lines before parsing. Less invasive but papers over the real issue.

Option 1 is the right fix; would also help any orchestrator that parses CMD stdout (the runner does for stream-json events).

## Acceptance

- All three tests in `test_entrypoint_lsp_settings.py` pass after the fix.
- No other test regressions (run the full `tests/integration/` suite).
- The new `tests/integration/test_entrypoint_workspace_injection.py` keeps passing (those tests check both stdout and `cat`-pulled file content; if discovery logs move to stderr, the test that asserts `--plugin-dir /opt/agentic/plugins/observability` should still find that string because that env-var content comes via the `echo "$AGENTIC_PLUGIN_FLAGS"` we explicitly run inside the command).

## Out of scope

- Other entrypoint logging — only the `[entrypoint] Discovered plugin: …` lines and any others that interfere with structured CMD stdout.

## Related

- Entrypoint script: `providers/workspaces/claude-cli/scripts/entrypoint.sh`
- Pre-existing failing tests: `tests/integration/test_entrypoint_lsp_settings.py`
