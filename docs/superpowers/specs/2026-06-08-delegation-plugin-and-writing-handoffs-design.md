# Design: `delegation` plugin + `writing-handoffs` skill

**Date:** 2026-06-08
**Branch:** `handoff-skill`
**Status:** approved — ready for implementation plan

## Purpose

Three related changes, one spec:

1. Rename the `claude-p` plugin to `delegation` — a broader home for "handing
   work off to other agents" (autonomous `claude -p` today; `delegating-to-codex`
   and friends later).
2. Add a new `writing-handoffs` skill under `delegation`: an agent produces its
   own compaction/handoff document so a fresh session or agent can pick up a
   branch or task with full context (the *why*, not just the *what*).
3. Add a CI guard that fails when a `plugins/*/` directory is not registered in
   `marketplace.json` — the exact gap that let `claude-p` ship unlisted.

## Background

- `plugins/claude-p/` exists with a single skill, `delegating-to-claude-p`, but
  was **never registered** in `.claude-plugin/marketplace.json`, the README
  install table, or the README feature matrix. The v1.0.0 PR (`a8f067c`) added
  only the plugin directory.
- The CI `plugin-validate` job in `.github/workflows/qa.yml` loops over every
  `plugins/*/` directory and validates manifest structure, but does **not**
  cross-check `marketplace.json`. That blind spot is why the omission was not
  caught.
- Reference inspiration for the handoff skill: mattpocock's `handoff` skill
  (productivity). We want a more structured, template-driven version that
  captures rationale and hard-won lessons, not just a terse summary.

## Non-goals

- No slash command for handoffs — skills are directly invocable and
  auto-dispatch on triggers; a command would be redundant.
- No changes to the `delegating-to-claude-p` skill *content* beyond its
  `placement:` path line.
- No local (`just qa`) mirror of the registration check — CI `plugin-validate`
  is the canonical gate and the natural fit.

## Scope addendum (mid-implementation)

After the original design was approved, two additions were made in the same PR:

- **`delegating-to-codex` skill** (originally a non-goal). Added at the user's
  request — the empirically-validated `codex exec` recipe, grounded in two real
  trials. This makes `delegation` the home for both autonomous-Claude and
  autonomous-Codex dispatch. Consequences carried through below: plugin version
  is **1.2.0** (not 1.1.0), the feature matrix lists **3 skills**, and the
  plugin description/README/CHANGELOG cover Codex.
- **`experiments` registration.** The new CI guard (Piece C) revealed that
  `experiments` — a complete plugin merged in #176 — was also never registered.
  It is registered here alongside `delegation`.

---

## Piece A — Rename `claude-p` → `delegation`

### Directory move
- `git mv plugins/claude-p plugins/delegation` (preserves history).
- The `delegating-to-claude-p` skill moves with it unchanged, **except** its
  frontmatter `placement:` line, which currently reads
  `plugins/claude-p/skills/delegating-to-claude-p/` → update to
  `plugins/delegation/skills/delegating-to-claude-p/`.

### `plugins/delegation/.claude-plugin/plugin.json`
- `name`: `claude-p` → `delegation`
- `version`: `1.0.0` → `1.2.0` (rename + `writing-handoffs` + `delegating-to-codex`)
- `description`: broaden to cover the plugin's theme, e.g.
  *"Handing work off to other agents — empirically-validated `claude -p`
  delegation and structured session-to-session handoff documents."*
- Keep `author`, `repository`.

### Registration & docs
- **`marketplace.json`**: add a `delegation` entry
  (`source: ./plugins/delegation`, `category: development`).
- **README install table** (around line 146): add a `delegation` row.
- **README feature matrix** (around line 158): add `delegation` —
  0 commands / 3 skills / 0 agents / 0 hooks.
- **`plugins/delegation/README.md`**: rewrite to describe the plugin as a home
  for delegation/handoff skills and document its skills.
- **`plugins/delegation/CHANGELOG.md`**: `1.1.0` (rename + `writing-handoffs`)
  and `1.2.0` (`delegating-to-codex`) entries.

---

## Piece B — `writing-handoffs` skill

### Location
```
plugins/delegation/skills/writing-handoffs/
├── SKILL.md
└── template.md
```

### `SKILL.md` frontmatter
- `name: writing-handoffs`
- `description:` — trigger phrases: "write a handoff", "hand this off",
  "compact this for a fresh agent/session", "summarize this branch's context",
  "pick this up later". Include a "Do NOT use for…" clause (e.g. not for
  generating PRDs/ADRs/plans — those are separate artifacts the handoff
  *references*).
- `placement:` line mirroring the claude-p skill convention, pointing at
  `plugins/delegation/skills/writing-handoffs/`.

### `SKILL.md` body — procedure
1. **Gather context** from the repo, not memory: `git` for branch, remote URL,
   and changed files (`git status`, `git diff --stat`, recent commits).
2. **Resolve output path**: `docs/handoffs/YYYYMMDD-handoff_<name>.md`.
   - `<name>` **defaults to the current branch slug** when the user does not
     pass one (e.g. branch `handoff-skill` → `20260608-handoff_handoff-skill.md`).
   - Path is **configurable**: the user may override the directory/name.
3. **Fill `template.md`** with gathered + conversational context.
4. **Write** the file; report the path back to the user.

### `SKILL.md` body — discipline rules (the lines that earn their place)
- **Don't duplicate** existing artifacts (PRDs, plans, ADRs, issues, commits,
  diffs) — reference them by path or URL.
- **Redact** secrets, API keys, tokens, and PII.
- **Length: 1000-line hard ceiling, aim 100–300.** Concise beats exhaustive;
  a handoff nobody reads is worthless.
- **Capture the irrecoverable context**: *why* it was done this way, decisions
  and rejected alternatives, do's-and-don'ts learned this session, dead ends,
  non-obvious constraints. A fresh agent can read the diff; it cannot
  reconstruct the reasoning.
- **Suggested Skills** section so the next agent knows what to invoke.

### `template.md`
Fill-in skeleton with these sections (Purpose & Vision kept merged):

```markdown
# Handoff: <title>

**Date:** YYYY-MM-DD
**Repo:** <url>   **Branch:** <branch>
**Status:** <in-progress | blocked | ready-for-review>

## Purpose & Vision
<the why — what this work is for, the end goal>

## Current State
<what's done, what's in flight, what's next>

## Files Affected
<path — one-line role; reference diffs, don't paste them>

## Rationale & Key Decisions
<why it was done this way; alternatives rejected and why>

## Do's and Don'ts (learned this session)
<gotchas, dead ends, conventions discovered>

## Important Context to Keep in Mind
<constraints, env quirks, anything non-obvious>

## Suggested Skills
<skills the next agent should invoke>

## References
<PRDs, ADRs, issues, plans — by path/URL, not duplicated>
```

---

## Piece C — Marketplace-registration CI guard

### Where
Inside the existing `plugin-validate` job loop in
`.github/workflows/qa.yml` (the `for plugin_dir in plugins/*/` loop, after the
required-fields check).

### Check
For each `plugins/<name>/`, assert `.claude-plugin/marketplace.json` contains a
plugin entry whose `source` equals `./plugins/<name>` (jq query). On miss:
`[ERROR] <name> not registered in marketplace.json` and set `failed=1`.

### Rationale
Promotes the claude-p footgun from "silently unlisted" to "red CI". Lives in
CI (not `just qa`) to match the existing `plugin-validate` pattern; uses the
same bash/jq style already present in the job.

---

## Touchpoint checklist

- [ ] `git mv plugins/claude-p plugins/delegation`
- [ ] `plugins/delegation/.claude-plugin/plugin.json` (name, version, description)
- [ ] `delegating-to-claude-p` SKILL.md `placement:` path line
- [ ] `plugins/delegation/skills/writing-handoffs/SKILL.md` (new)
- [ ] `plugins/delegation/skills/writing-handoffs/template.md` (new)
- [ ] `plugins/delegation/README.md` (rewrite)
- [ ] `plugins/delegation/CHANGELOG.md` (1.1.0 entry)
- [ ] `.claude-plugin/marketplace.json` (register delegation)
- [ ] `README.md` install table + feature matrix
- [ ] `.github/workflows/qa.yml` (registration guard)
- [ ] `just qa-fix` clean

## Verification

- `just qa` passes (incl. the new registration guard once delegation is
  registered).
- `claude plugin install delegation@agentic-primitives` resolves (manual / CI).
- Invoking `writing-handoffs` on this branch produces
  `docs/handoffs/20260608-handoff_handoff-skill.md` filled from the template,
  under the line ceiling, with no duplicated artifacts or leaked secrets.
- Temporarily unregistering a plugin makes the new CI guard fail (sanity check).
