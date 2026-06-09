<!--
Handoff template. Copy this file, fill every <placeholder>, and write the result
to docs/handoffs/YYYYMMDD-handoff_<name>.md (path configurable; <name> defaults
to the branch slug). Aim for 100–300 lines; 1000 is the hard ceiling. Reference
artifacts by path/URL — do not duplicate them. Redact secrets and PII. Delete
this comment in the finished doc.
-->

# Handoff: <title>

**Date:** YYYY-MM-DD
**Repo:** <url>   **Branch:** <branch>
**Status:** <in-progress | blocked | ready-for-review>

## Purpose & Vision

<The why — what this work is for and the end goal it serves. One short
paragraph. If a PRD/spec covers this, summarize in two sentences and link it.>

## Current State

<What's done, what's in flight, what's next. A short bulleted list the next
agent can act on immediately.>

## Files Affected

<One line per path describing its role in this change. Reference the diff
(`git diff <base>`) rather than pasting it.>

- `path/to/file` — <role / what changed and why>

## Rationale & Key Decisions

<Why it was built this way. Decisions made, alternatives considered and
rejected, and the reasoning. This is the context a fresh agent cannot
reconstruct from the diff.>

## Do's and Don'ts (learned this session)

<Hard-won, session-specific guidance.>

- **Do:** <…>
- **Don't:** <… — dead ends, things that looked right but weren't>

## Important Context to Keep in Mind

<Constraints, environment quirks, flaky steps, ordering requirements — anything
non-obvious that will bite the next agent.>

## Suggested Skills

<Skills the next agent should invoke on pickup, with a word on why.>

- `<skill-name>` — <why>

## References

<PRDs, ADRs, specs, plans, issues, PRs — by path or URL. Do not duplicate their
content here.>

- <path-or-url> — <what it is>
