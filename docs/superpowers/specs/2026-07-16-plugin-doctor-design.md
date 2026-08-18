# plugin-doctor: agentic-primitives plugin freshness monitor

## Context

`agentic-primitives` plugins are versioned and updatable (`claude plugin update <name>`), but nothing tells a user an update exists — they only find out by manually running `claude plugin marketplace update` + `claude plugin update <name>` per plugin, or by noticing something's broken. This surfaced concretely in `agent-paradise-standards-system`, where a vendored (pre-plugin-system) copy of `sdlc`'s hook handlers silently drifted for months, shipping an invalid `PreToolUse`/`PostToolUse` JSON schema (`{"decision": "allow"}`, not a valid value) until it started failing hook validation.

That specific case was a vendored copy, not a real plugin install, so it's out of scope for this fix directly — but it exposed the general gap: **installed plugins have no freshness signal at all.** This spec covers that general gap for anyone using the real plugin system.

## Goal

A new plugin, `plugin-doctor@agentic-primitives`, that:
- Checks, at most once a week, whether any installed `agentic-primitives` plugin has a newer version available.
- Surfaces outdated plugins to the user near the start of a session via Claude, who asks whether to update.
- Never runs an update automatically. Update only happens if the user explicitly agrees, at which point Claude runs `claude plugin update <name>@agentic-primitives` itself (a normal, permission-gated Bash call).

## Non-goals

- Checking plugins from other marketplaces (`claude-plugins-official`, `syntropic137`, etc.) — noisy, and update cadence for those isn't ours to reason about.
- Fixing vendored/non-plugin-system copies (like the `agent-paradise-standards-system` case) — those need a one-time manual re-sync or migration to the real plugin system; this plugin can't see them.
- Auto-installing updates.
- A manual "check now" slash command — YAGNI for v1; can be added later if the weekly cadence proves too coarse.

## Design

### 1. Plugin shape

New plugin at `plugins/plugin-doctor/`, following the existing layout:

```
plugins/plugin-doctor/
  .claude-plugin/
    plugin.json
  hooks/
    hooks.json
    handlers/
      session-start.py
```

Single-purpose: one `SessionStart` hook, one handler script. No commands, skills, or agents.

`plugin.json`:
```json
{
  "name": "plugin-doctor",
  "version": "0.1.0",
  "description": "Warns when installed agentic-primitives plugins have updates available",
  "author": { "name": "NeuralEmpowerment" },
  "repository": "https://github.com/AgentParadise/agentic-primitives"
}
```

### 2. Version comparison — pure filesystem reads

No subprocess needed for the comparison itself:

- **Installed version**: for each directory under `~/.claude/plugins/cache/agentic-primitives/<plugin>/`, the directory name is the installed version (e.g. `~/.claude/plugins/cache/agentic-primitives/sdlc/1.4.0/`). This naturally enumerates every `agentic-primitives` plugin currently installed at user scope, enabled or not.
- **Catalog (latest known) version**: read `"version"` from `~/.claude/plugins/marketplaces/agentic-primitives/plugins/<plugin>/.claude-plugin/plugin.json`.
- Compare with a semver-aware comparison (not string comparison — `1.10.0 > 1.9.0`).

If the marketplace cache doesn't have an entry for an installed plugin (renamed/removed upstream), skip it silently — not this plugin's job to flag that.

### 3. State & refresh cadence

State file at `~/.claude/plugin-doctor/state.json` (self-managed; not one of Claude's internal plugin-data conventions):

```json
{ "last_checked_at": "2026-07-16T12:00:00Z" }
```

On `SessionStart`:

1. Read `last_checked_at`. Missing or unparseable → treat as due.
2. If `now - last_checked_at >= 7 days`:
   - Run `claude plugin marketplace update agentic-primitives` as a subprocess, timeout ~10s.
   - Write `last_checked_at = now` **regardless of whether the refresh succeeded.** This keeps the cadence predictable: a transient network failure costs one missed week, not a retry-every-session loop.
3. Compare installed vs. catalog version for every plugin found under `~/.claude/plugins/cache/agentic-primitives/*` (per section 2).
4. If any are behind, emit `hookSpecificOutput.additionalContext` naming each outdated plugin and its versions (e.g. `sdlc 1.4.0 → 1.5.0`), with an instruction to Claude:
   - Mention this near the start of the conversation.
   - Ask the user whether they want to update.
   - Never run `claude plugin update` without the user explicitly agreeing.
5. If nothing is outdated, or the check wasn't due this session, emit nothing — no-op, matching the convention of every other hook in this repo (empty output = allow/no context).

### 4. Error handling

Fail silent/open in every case, matching the rest of the hook handlers in this repo:

- `claude` not on `PATH` → skip the marketplace refresh, still do the local comparison against whatever's cached.
- Marketplace cache directory missing entirely → nothing to compare against, no-op.
- Malformed `plugin.json` or state file → treat as missing, don't crash.
- No network during refresh → subprocess fails, `last_checked_at` still advances per section 3.

None of these should ever block a session or print an error the user has to deal with.

### 5. Testing

The version-diffing and cadence-gating logic are pure functions, independent of the subprocess call and of real `~/.claude` paths — same separation pattern as the `sdlc` plugin's `validate(...)` validators (`plugins/sdlc/hooks/validators/`). Tests inject a fake cache directory and a fake state file path rather than touching real user state or shelling out.

Cases to cover:
- No installed plugins → no-op.
- All installed plugins at latest version → no context emitted.
- One or more outdated → context lists exactly the outdated ones with correct version strings.
- State file missing/malformed → treated as due.
- Refresh due but `claude` missing from `PATH` → falls back to comparing against existing cache, doesn't crash.
- Semver comparison correctness (e.g. `1.10.0` vs `1.9.0`).
