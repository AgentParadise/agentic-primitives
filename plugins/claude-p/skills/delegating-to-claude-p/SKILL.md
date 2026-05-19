---
name: delegating-to-claude-p
description: Use when authoring a non-interactive `claude -p` invocation or designing a delegation prompt for autonomous Claude on the consumer side. Provides the empirically-validated flag set, prompt template, steers-vs-needs-naming map, failure-mode catalog, recipe templates, and cost reference distilled from 22 sub-experiments (S1 → S22) in the agentic-harness-lab v0.8.0 dogfood arc. Trigger phrases include "delegate to claude -p", "claude -p flags", "autonomous claude", "one-shot claude", "claude -p prompt", "headless claude". Do NOT use for interactive Claude Code sessions, brainstorming, or genuine multi-turn work — `claude -p` is a one-shot contract; pick interactive Claude for those.
placement: "Domain skill. Lives at `plugins/claude-p/skills/delegating-to-claude-p/` in agentic-primitives. NOT in `.claude/skills/`; that scope is for meta skills."
---

# Delegating to `claude -p`

## Purpose

Invoke this skill any time you are about to write a `claude -p` invocation or design a delegation prompt for autonomous Claude on the consumer side. It captures the empirically-validated flag set + prompt template from paired trials S6 → S16 of the agentic-harness-lab v0.8.0 dogfood arc, plus the failure modes that surfaced across S1 → S22. Source evidence: `docs/retrospectives/023-harness-dogfood-claude-p-steering.md` in `agentic-harness-lab`.

The single guiding finding: **hard gates and explicit prompt verbs are what steer `claude -p`. Soft documentation (CLAUDE.md content, skill indices, advisory rules) is largely inert in non-interactive mode unless the user prompt names it explicitly.**

## The validated invocation

```sh
claude -p --verbose \
  --permission-mode bypassPermissions \
  --append-system-prompt-file ./CLAUDE.md \
  --output-format stream-json --include-hook-events --include-partial-messages \
  --max-budget-usd <N> \
  --no-session-persistence \
  "$TASK_PROMPT"
```

### Per-flag rationale

- **`--verbose` + `--output-format stream-json`** — required *together*. Text mode hides tool calls and is unscoreable (S7 footgun: stream-json with `--print` errors without `--verbose`). If you only set one, the transcript is useless for triage.
- **`--permission-mode bypassPermissions`** — the realistic-autonomy mode. The default mode is read-only (S4 returned no-go because Claude could not write files). `acceptEdits` auto-approves Edit/Write but denies Bash (S5 no-go). Only `bypassPermissions` opens both, which you need for fmt/test/commit loops.
- **`--append-system-prompt-file ./CLAUDE.md`** — injects project context. CWD auto-discovery also works (verified S11), but explicit is safer when invoking from a wrapper that may not cd into the project root.
- **`--include-hook-events`** — lefthook firings become parseable events in the JSONL stream. Without this, gate-bounce-and-retry behavior (S7) is invisible.
- **`--include-partial-messages`** — richer tool-call detail; useful when scoring or debugging a transcript.
- **`--max-budget-usd <N>`** — the hard cap. macOS lacks `timeout` (G-19); this is the only enforced bound. Pick the value from the cost reference below.
- **`--no-session-persistence`** — clean one-shot trials do not pollute interactive history.

## The validated prompt template

```
<TASK DESCRIPTION>

Before extending: WebSearch <topic> and CITE >=N sources in the commit message.
Use conventional commits. N commits total (Part 1 then Part 2 if applicable).
```

### Why each piece (with trial evidence)

- **Strong-verb "WebSearch and CITE"**. S12 used the weak verb "verify" → **0** WebSearch calls. S13 used "WebSearch and cite ≥2 sources" → **2** WebSearch calls on an identical task. The 0 → 2 delta is causal: descriptive verbs are silently ignored; action verbs bind.
- **Explicit "Use conventional commits / N commits total"**. S13 had the WebSearch directive but lacked an explicit commit directive → **0** commits landed despite work being done (Claude stopped at *"Ready to commit when you say go"*). S14 added "Two commits total" → **2** commits with **5** URL citations.
- **"Cite ≥N sources"** produces substantive reasoning, not URL padding. S16 picked sessionStorage for a JWT auth wiring task but disclosed HttpOnly cookies as the production pattern, citing Descope and Duende docs. Citation discipline forces tradeoff articulation.

## What steers autonomously vs needs explicit naming

| Surface | Effect | Activation |
|---|---|---|
| **Lefthook + cog-verify hard gates** | ✅ Deterministic | Always-on; zero agent buy-in needed (S7 confirmed gate-bounce-and-retry; no `--no-verify` attempts) |
| **Plugin skills** | ✅ Task-shape dispatch | Auto-dispatches on relevant tasks (S8: `superpowers:test-driven-development` fired on a TDD-shaped JWT task without being named) |
| **Project-local `.claude/skills/`** | ✅ Dispatchable | Must name in prompt; bare unnamespaced names work (S9 verified) |
| **CLAUDE.md rules** | ⚠️ Advisory | Bind only when the user prompt uses matching action verbs (G-49: Claude silently ignored a CLAUDE.md rule mandating "verify" even when the rule was present) |
| **Skills index in CLAUDE.md** | ❌ Inert in `-p` | Useful only for human / interactive Claude Code use (S10 found **zero** behavioral delta from adding the index vs. S6 baseline) |

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Exits without committing despite finishing work | Missing explicit commit directive in prompt | Add "Use conventional commits. N commits total." (S13 → S14) |
| Zero WebSearch despite CLAUDE.md mandating it | Soft-doc rules do not bind autonomously in `-p` | Use strong action verbs in the user prompt itself (G-49) |
| Reads default Anthropic system prompt only; ignores project context | CLAUDE.md not at CWD AND no `--append-system-prompt-file` | Either cd into project root OR pass `--append-system-prompt-file ./CLAUDE.md` explicitly |
| Auth / read-only / cannot-edit failures | Default permission mode is read-only | Set `--permission-mode bypassPermissions` explicitly |
| Unscoreable transcript (no tool calls visible) | Default `--output-format text` hides tool detail | Use all three together: `--output-format stream-json`, `--verbose`, `--include-hook-events` |
| Hung past budget | macOS lacks `timeout`; no time-based bound | `--max-budget-usd` is the only hard cap |
| Project-local skill never dispatched | `.claude/skills/` is NOT auto-enumerated in `-p` | Name the skill explicitly in the task prompt (bare unnamespaced name dispatches local files) |
| `tee`-style epilogue lines break JSONL parsing | `echo ... | tee -a transcript.jsonl` writes plain text into JSONL | Write epilogue to a sibling `.txt` file (G-29) |

## Recipe templates

Five task families with complete invocations, sample prompts, and expected behavior.

### 1. Single-file change (~$0.40)

```sh
claude -p --verbose \
  --permission-mode bypassPermissions \
  --append-system-prompt-file ./CLAUDE.md \
  --output-format stream-json --include-hook-events --include-partial-messages \
  --max-budget-usd 1.00 \
  --no-session-persistence \
  "Add a /version endpoint to the example-rust axum server. Return JSON {\"version\": CARGO_PKG_VERSION}. Add tests. Use conventional commits."
```

Expected: one commit, fmt/clippy/cog-verify all clean, <60s wall-clock. S6 reference.

### 2. Multi-commit feature (~$1.50)

```sh
claude -p ... --max-budget-usd 3.00 ... \
  "Part 1: add a JWT bearer-token middleware to the axum server. Part 2: add a DELETE /todos/:id endpoint that requires the middleware.

Before extending: WebSearch axum 0.8 middleware patterns and CITE >=2 sources in the commit message.
Use conventional commits. 2 commits total (Part 1 then Part 2)."
```

Expected: 2 commits, ≥2 cited URLs in commit bodies. S14 reference.

### 3. Mapping probe (research-heavy) (~$1.00)

```sh
claude -p ... --max-budget-usd 2.00 ... \
  "Use the running-experiments skill to produce a hypothesis-first mapping probe for self-hosted Postgres alternatives to Supabase. WebSearch the current state of 4-6 candidates. Recommend one with sourced reasoning. Don't write integration code yet. Commit only the probe README under experiments/<date>--supabase-alternatives/."
```

Expected: 1 commit, probe README only, broad WebSearch usage. S11 reference.

### 4. Refactor (~$1.00)

```sh
claude -p ... --max-budget-usd 2.00 ... \
  "Refactor the todos handler in src/handlers/todos.rs to follow the error-handling convention used in src/handlers/users.rs. Don't add unrelated cleanup. Use conventional commits."
```

Expected: 1 commit, no scope creep, style matches reference file.

### 5. Cross-stack (~$1.50)

```sh
claude -p ... --max-budget-usd 3.00 ... \
  "Wire the Tasks page in the Vite frontend to call the GET /tasks endpoint on the Rust API. Use the existing /api/* Vite proxy (don't add CORS). Match conventions in existing fetcher helpers.

Before extending: WebSearch SWR vs TanStack Query for axum-backed APIs and CITE >=2 sources in the commit message.
Use conventional commits."
```

Expected: 1-2 commits across frontend, no CORS additions, cited library choice. S15 reference.

## Cost reference (from v0.8.0 arc empirical data)

| Task shape | Cost | Wall-clock | Turns | Trial |
|---|---|---|---|---|
| /version endpoint (trivial) | $0.41 | 34s | 6 | S6 |
| /todos CRUD (Rust-only, ~4× S6) | $0.60 | 81s | 12 | S7 |
| sqlx + migrations + tests | $1.14 | 195s | 25 | S12 |
| JWT middleware + DELETE (2 commits) | $1.43 | 154s | 29 | S14 |
| Frontend tasks wire-up (cross-stack) | $1.63 | ~10 min | — | S15 |
| Supabase mapping probe (research) | $0.90 | 131s | 11 | S11 |
| JWT frontend auth wiring | $2.89 | 6m20s | 53 | S16 |

### `--max-budget-usd` recommended settings

- **Single-file / trivial**: `1.00`
- **Multi-commit feature / cross-stack**: `3.00`
- **Research-heavy** (mapping probe, WebSearch loop): `2.00`
- **Defensive default** when unsure: `4.00`

The most expensive trial in the arc (S16, JWT frontend auth wiring) ran $2.89; `4.00` covers it with margin. Below `1.00` is dangerous — even trivial tasks can spike if cog-verify rejects multiple commit messages.

## When NOT to use `claude -p`

- **Interactive ideation or brainstorming** — use interactive Claude Code; the one-shot contract loses signal in genuine exploration.
- **Tasks requiring genuine multi-turn back-and-forth** — `claude -p` is one prompt → one output stream. If you need clarification cycles, pick interactive.
- **Subjective UX or design work where hard gates cannot enforce correctness** — there is no fmt/clippy/cog-verify for "does this feel right." Without deterministic gates, `claude -p` output quality is uncalibrated.
- **Sensitive operations where you cannot safely use `bypassPermissions`** — production credentials, shared filesystems, untrusted dependencies. Run those interactively with explicit human approval per Bash call.

## References

- **Retrospective 023** (`agentic-harness-lab/docs/retrospectives/023-harness-dogfood-claude-p-steering.md`) — full S1 → S22 synthesis + addendum. Canonical evidence base for every claim in this skill.
- **Pair with `sdlc:security-hardening`** — the CI-side supply-chain controls that `claude -p` retries against (not against). The two skills are complementary: this one tells you how to dispatch; that one tells you what gates to dispatch into.
- **Pair with `experiments:running-experiments`** — the discipline that produced this skill's evidence. Use it when designing your own paired trial to extend or contest these findings.
- **Template doc**: `templates/polyglot-monorepo/files/CLAUDE.md` in `agentic-harness-lab` ships a condensed version of this recipe in scaffolded projects (v0.8.3+, commit `006036d`).
