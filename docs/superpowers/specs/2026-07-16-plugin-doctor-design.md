# plugin-doctor: agentic-primitives plugin freshness monitor

## Context

`agentic-primitives` plugins are versioned and updatable (`claude plugin update <name>`), but nothing tells a user an update exists — they only find out by manually running `claude plugin marketplace update` + `claude plugin update <name>` per plugin, or by noticing something's broken. This surfaced concretely in `agent-paradise-standards-system`, where a vendored (pre-plugin-system) copy of `sdlc`'s hook handlers silently drifted for months, shipping an invalid `PreToolUse`/`PostToolUse` JSON schema (`{"decision": "allow"}`, not a valid value) until it started failing hook validation.

That specific case was a vendored copy, not a real plugin install, so it's out of scope for this fix directly — but it exposed the general gap: **installed plugins have no freshness signal at all.** This spec covers that general gap for anyone using the real plugin system.

## Goal

A new plugin, `plugin-doctor@agentic-primitives`, that:
- Checks, at most once a week, whether any installed `agentic-primitives` plugin has a newer version available.
- Verifies that newer version has actually been live on GitHub for at least 48 hours before ever mentioning it — a supply-chain safety cooldown, so a freshly-pushed (and potentially bad or quickly-reverted) release is never surfaced the moment it lands.
- Surfaces outdated-and-old-enough plugins to the user near the start of a session via Claude, who asks whether to update.
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
4. Filter step 3's outdated set down to only plugins whose newer version has been verified as release-age-eligible (per section 6) — see section 6 for exactly when that verification runs.
5. If any remain, emit `hookSpecificOutput.additionalContext` naming each outdated plugin and its versions (e.g. `sdlc 1.4.0 → 1.5.0`), with an instruction to Claude:
   - Mention this near the start of the conversation.
   - Ask the user whether they want to update.
   - Never run `claude plugin update` without the user explicitly agreeing.
6. If nothing remains after the age filter, emit nothing — no-op, matching the convention of every other hook in this repo (empty output = allow/no context). This is independent of whether the weekly refresh ran this session: the comparison in step 3 always runs against whatever's cached, so a session can still report outdated-and-old-enough plugins (or report nothing) regardless of whether step 2's refresh fired.

### 4. Error handling

Fail silent/open in every case, matching the rest of the hook handlers in this repo:

- `claude` not on `PATH` → skip the marketplace refresh, still do the local comparison against whatever's cached.
- Marketplace cache directory missing entirely → nothing to compare against, no-op.
- Malformed `plugin.json` or state file → treat as missing, don't crash.
- No network during refresh → subprocess fails, `last_checked_at` still advances per section 3.

None of these should ever block a session or print an error the user has to deal with.

### 6. GitHub release-age gate (supply-chain safety)

`agentic-primitives` tags each plugin release on GitHub as `<plugin>/v<version>` (via the repo's own `claude plugin tag` command) — a deliberate, intentional release marker, distinct from a version bump merely landing on `main`. This gives a real "when was this actually released" timestamp that the local marketplace cache (a shallow, non-git snapshot) cannot provide.

**Mechanism**: a single unauthenticated GitHub REST API call resolves a tag straight to its commit date:

```
GET https://api.github.com/repos/AgentParadise/agentic-primitives/commits?sha=<plugin>/v<version>&per_page=1
```

The response's `[0].commit.committer.date` is the release timestamp. Unauthenticated rate limit is 60 requests/hour — ample given this call only fires weekly and only for plugins already found outdated (typically 0-2 per week).

**When it runs**: only inside the existing step 2 weekly-due block, and only for plugins step 3 already found outdated that session (using the just-refreshed catalog). It does **not** run every session — that would mean a network call on every session start for as long as a candidate stays under 48 hours old, which is both wasteful and unnecessary given the weekly cadence already in place.

**Caching**: the result is cached in `state.json` under a new `release_ages` key, keyed by plugin name, alongside the version it was checked against:

```json
{
  "last_checked_at": "2026-07-16T12:00:00Z",
  "release_ages": {
    "sdlc": { "version": "1.5.0", "old_enough": false }
  }
}
```

Each weekly due-check recomputes `release_ages` from scratch (discarding stale entries for plugins that are no longer outdated, so it never grows unbounded). Step 4's filter (above) checks this cache: a plugin is only surfaced if `release_ages[plugin].version` matches the *current* catalog version and `old_enough` is `true`. A plugin that just became outdated has no matching cache entry yet — the filter treats "no entry" the same as "not old enough," so it's suppressed until the *next* weekly check reaches it. This is intentional: it means detection-to-notification latency is up to one extra week in the worst case, which is an acceptable cost for the safety property this section exists to provide.

**Failure handling**: any failure resolving the age (network down, rate-limited, malformed response, or — critically — the tag not existing yet because a version landed on `main` but hasn't been tagged/released) is treated identically to "not old enough" (`old_enough: false`). This is a deliberate fail-safe: plugin-doctor must never recommend an update it couldn't verify is actually a confirmed, aged release. No new external dependency is added for this — the fetch uses stdlib `urllib.request` only, with a ~10s timeout, matching the "stdlib only" constraint from section 5.

**Configurability**: the minimum age (`48` hours) and the GitHub API base URL are both overridable — the latter purely for testing (see section 7), pointing it at a local fixture server instead of the real GitHub API.

### 7. Testing

The version-diffing and cadence-gating logic are pure functions, independent of the subprocess call and of real `~/.claude` paths — same separation pattern as the `sdlc` plugin's `validate(...)` validators (`plugins/sdlc/hooks/validators/`). Tests inject a fake cache directory and a fake state file path rather than touching real user state or shelling out.

Cases to cover:
- No installed plugins → no-op.
- All installed plugins at latest version → no context emitted.
- One or more outdated → context lists exactly the outdated ones with correct version strings.
- State file missing/malformed → treated as due.
- Refresh due but `claude` missing from `PATH` → falls back to comparing against existing cache, doesn't crash.
- Semver comparison correctness (e.g. `1.10.0` vs `1.9.0`).

**Release-age gate testing** (section 6): the same "real behavior, not mocks" principle applies to the GitHub fetch — rather than mocking `urllib.request`, tests spin up a real local `http.server.HTTPServer` on an ephemeral port in a background thread, serving canned JSON fixture responses, and point the handler at it via the GitHub-API-base-URL override. This mirrors how the marketplace-refresh subprocess path is tested with a real fake `claude` executable on `PATH` rather than a mocked `subprocess.run`.

Additional cases to cover:
- `is_release_old_enough` (pure): `None` input → `False`; unparseable date string → `False`; a date less than 48h before `now` → `False`; a date 48h+ before `now` → `True`; a date exactly 48h before `now` → `True` (boundary, `>=`).
- Handler end-to-end: an outdated plugin whose fixture server returns a commit date 48h+ old → surfaced in `additionalContext`. An outdated plugin whose fixture server returns a commit date under 48h old → NOT surfaced, but still recorded in `release_ages` with `old_enough: false`. A fixture server returning 404 (tag not found) → NOT surfaced, fails open, no crash. Fixture server unreachable (nothing listening on the target port) → NOT surfaced, fails open, no crash. A cached `release_ages` entry from a prior version that no longer matches the current catalog version → treated as unverified, NOT surfaced. Weekly-due session correctly recomputes `release_ages` from scratch (a plugin no longer outdated drops out of the cache). Non-due session correctly reuses the cached `release_ages` without hitting the fixture server at all.
