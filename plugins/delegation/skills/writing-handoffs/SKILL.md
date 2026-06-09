---
name: writing-handoffs
description: Use when you need to compact the current conversation into a handoff document so a fresh session or agent can continue a branch or task with full context. Trigger phrases include "write a handoff", "hand this off", "compact this for a fresh agent", "handoff doc", "summarize this branch's context", "I'll pick this up later", "create a handoff for the next session". Produces a structured Markdown doc (from a template) capturing purpose, current state, files affected, rationale, do's-and-don'ts learned, and suggested skills. Do NOT use to author PRDs, ADRs, plans, or specs — those are separate durable artifacts that a handoff references by path, not reproduces. Do NOT use for a routine end-of-task summary message; a handoff is a written file for a different session to load.
placement: "Domain skill. Lives at `plugins/delegation/skills/writing-handoffs/` in agentic-primitives. NOT in `.claude/skills/`; that scope is for meta skills."
---

# Writing Handoffs

## Purpose

Invoke this skill when a conversation has accumulated context that a fresh
session or another agent will need to continue the work — typically when you're
pausing a branch, switching machines, hitting a context limit, or handing a task
to a teammate's agent.

A handoff is the agent's own compaction: a written file that preserves the
**irrecoverable context** — *why* the work is shaped the way it is, what was
tried and abandoned, the gotchas learned along the way. A fresh agent can read
the diff and the commits; it cannot reconstruct the reasoning. That reasoning is
what this document carries.

## Procedure

1. **Gather context from the repo, not from memory.** Run, don't recall:
   - `git rev-parse --abbrev-ref HEAD` — current branch
   - `git remote get-url origin` — repository URL
   - `git status --short` and `git diff --stat` — files touched
   - `git log --oneline -10` — recent commits
   Use these to fill the factual header fields exactly.

2. **Resolve the output path.**
   - Default: `docs/handoffs/YYYYMMDD-handoff_<name>.md`
   - `<name>` **defaults to the current branch slug** when the user does not
     supply one (e.g. on branch `handoff-skill` →
     `docs/handoffs/20260608-handoff_handoff-skill.md`).
   - The path is **configurable** — if the user names a different directory,
     file name, or descriptor, honor it. Create the directory if it is missing.

3. **Fill the template.** Copy `template.md` (in this skill directory) and
   replace every placeholder with real content drawn from the conversation and
   the gathered git facts.

4. **Write the file and report the path back** so the user can open or commit it.

## Discipline (the rules that make a handoff worth reading)

- **Don't duplicate existing artifacts.** PRDs, plans, ADRs, specs, issues,
  commits, and diffs already exist — reference them by path or URL. Re-pasting
  them bloats the doc and goes stale.
- **Redact secrets.** No API keys, tokens, passwords, connection strings, or
  PII in the handoff. Replace with `<redacted>` and note where the real value
  lives (e.g. "in macOS Keychain under `…`").
- **Length: 1000-line hard ceiling, aim 100–300.** Concise beats exhaustive. A
  handoff nobody reads is worthless; trim anything the next agent can recover
  from the code itself.
- **Capture the irrecoverable, not the obvious.** Prioritize: the *why*,
  decisions and rejected alternatives, do's-and-don'ts learned this session,
  dead ends, non-obvious constraints and environment quirks. Skip restating what
  the diff plainly shows.
- **Always include Suggested Skills** so the next agent knows what to invoke on
  pickup.

## Template

See `template.md` in this directory. Sections:
Title · Date · Repo/Branch/Status · Purpose & Vision · Current State ·
Files Affected · Rationale & Key Decisions · Do's and Don'ts · Important
Context · Suggested Skills · References.
