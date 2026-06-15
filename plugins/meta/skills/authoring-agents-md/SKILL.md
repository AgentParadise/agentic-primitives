---
name: authoring-agents-md
description: Use when authoring, reviewing, or setting up an `AGENTS.md` file (the open "README for agents" format) and wiring it to Claude Code, which reads `CLAUDE.md` not `AGENTS.md`. Trigger phrases include "write an AGENTS.md", "author agents.md", "create AGENTS.md", "set up AGENTS.md", "AGENTS.md best practices", "AGENTS.md vs CLAUDE.md", "symlink CLAUDE.md to AGENTS.md", "make AGENTS.md canonical", "how does Claude use CLAUDE.md", "nested AGENTS.md", "monorepo agent instructions", "agents.md spec", "agent instructions file". Covers the agents.md spec, the canonical AGENTS.md-source-of-truth + symlinked-CLAUDE.md setup, Claude Code's CLAUDE.md load order and `@import` rules, and monorepo nesting. Do NOT use for authoring a Claude skill (use `authoring-skills`), for general CLAUDE.md auto-memory/rules configuration beyond the AGENTS.md bridge (see Claude Code memory docs), or for slash commands and hooks.
placement: "Meta-skill. Lives in `plugins/<meta-plugin>/skills/authoring-agents-md/` or repo-local `.claude/skills/authoring-agents-md/`. It teaches how to author an agent-instructions artifact, so it belongs at the meta level alongside `authoring-skills`, not among domain skills."
---

# Authoring AGENTS.md

## Overview

`AGENTS.md` is an open Markdown format, "a README for agents", that gives coding agents a single, predictable place for build steps, test commands, conventions, and guardrails that would clutter a human README. It is stewarded by the Agentic AI Foundation under the Linux Foundation and read by 60k+ projects across Codex, Cursor, Copilot, Aider, goose, Jules, Devin, Windsurf, Zed, and more. Claude Code is the notable exception: it reads `CLAUDE.md`, **not** `AGENTS.md`. This skill covers authoring a strong AGENTS.md, the canonical single-source-of-truth wiring (AGENTS.md is authoritative; CLAUDE.md is a symlink to it), how Claude Code discovers and loads instruction files, and how nesting resolves in monorepos.

## Outcomes we are looking for

### One source of truth, read by every agent
Signals: there is exactly one authored instructions file (`AGENTS.md`); `CLAUDE.md` resolves to the same bytes (symlink or thin `@AGENTS.md` import); editing AGENTS.md changes what every harness (Claude included) sees, with no second copy to drift.

### The file earns its place in context
Signals: AGENTS.md is concrete and skimmable (build/test/lint commands verifiable, conventions stated specifically); it stays well under ~200 lines so Claude loads it in full with high adherence; no marketing prose or restated README.

### Hierarchy resolves predictably
Signals: in a monorepo, the nearest AGENTS.md to the edited file wins and subproject files are scoped to their subtree; contributors can predict which instructions apply where; no contradictory rules across levels.

### The Claude bridge is portable and durable
Signals: the CLAUDE.md ↔ AGENTS.md link survives a fresh clone and works cross-platform (or its Windows caveat is documented); `/init` augments rather than forks the source of truth.

## Principles

1. **AGENTS.md is canonical; CLAUDE.md points at it.** Author one file. Make `CLAUDE.md` a symlink to `AGENTS.md` so the two can never diverge. Every other agent already reads AGENTS.md natively; the symlink is the single adaptation Claude Code needs. This is a deliberate choice over maintaining parallel files: duplication is the failure mode, not a feature.

2. **Claude Code reads CLAUDE.md, not AGENTS.md: bridge, never duplicate.** Two sanctioned bridges exist: a `ln -s AGENTS.md CLAUDE.md` symlink (preferred: zero content, zero drift), or a `CLAUDE.md` whose first line is `@AGENTS.md` (the fallback, and the only option on Windows without Developer Mode). Both keep AGENTS.md authoritative. Writing the same content into both files by hand is the anti-pattern this skill exists to prevent. The symlink is preferred for a second reason beyond Windows: it is resolved at the filesystem level, so Claude opens AGENTS.md as the root file and AGENTS.md's own `@imports` keep the full four-hop recursion budget. The `@AGENTS.md` import spends one of those four hops just to bridge, leaving three for AGENTS.md's nested imports. This only matters when AGENTS.md itself imports deeply, but on that axis the symlink is strictly better.

3. **Write for an agent that acts, not a human who reads.** Prefer exact, runnable commands (`uv run pytest`, `just qa`) over prose. Specific beats vague: "API handlers live in `src/api/handlers/`" outlive "keep files organized." The file is loaded as context, not enforced config, so clarity and concreteness directly raise adherence.

4. **Keep it short enough to load in full.** Claude Code loads ancestor CLAUDE.md files in full at launch and targets <200 lines per file; longer files consume context and reduce adherence. Cut anything an agent would not act on. If content is large, factor structure-heavy or path-specific detail into the subtree where it applies (nested AGENTS.md), not the root.

5. **Nearest file wins; scope instructions to where they apply.** Agents read the closest AGENTS.md in the directory tree, so per-subproject files carry tailored instructions for their subtree. Claude mirrors this: subdirectory `CLAUDE.md` files load on demand when Claude reads files there. Put root-wide truth at the root, subproject truth in the subproject.

6. **Standard Markdown, no schema.** AGENTS.md has no required fields, so use whatever headings serve the project. Common sections: project overview, build/test/lint commands, code style, testing instructions, security considerations, commit/PR conventions, deployment. Pick the ones an agent needs; omit the rest.

7. **Treat it as living documentation.** Update AGENTS.md when an agent makes the same mistake twice, when review catches something it should have known, or when a convention changes. A stale instructions file misroutes every agent that reads it.

## Anti-patterns

- **Two hand-maintained files.** A real `AGENTS.md` and a separately-edited `CLAUDE.md` with overlapping content. They drift within a week; agents get contradictory guidance depending on which they read.
- **Content written into CLAUDE.md with AGENTS.md as an afterthought (or absent).** Inverts the canonical direction, so every non-Claude harness then reads stale or missing instructions.
- **A symlink committed on a repo with Windows contributors and no fallback noted.** Clones fail to materialize the link without Developer Mode/Admin; those contributors silently lose the instructions.
- **A 400-line AGENTS.md at the root.** Loads in full, burns context, and adherence drops. Subproject detail belongs in nested files; deep procedures belong in skills or path-scoped rules.
- **Vague directives.** "Format code properly", "test your changes", "keep it clean." Not verifiable, so not actionable: the agent cannot tell whether it complied.
- **README content copy-pasted in.** AGENTS.md is the *extra* context agents need (build steps, conventions), not a restatement of the human-facing overview.
- **Contradictory rules across nested levels.** A root rule and a subproject rule that disagree; the agent picks arbitrarily. Reconcile, or scope each rule to the level where it is true.
- **Relying on AGENTS.md alone for Claude Code.** Without a `CLAUDE.md` bridge, Claude Code never reads the file at all: it does not look for `AGENTS.md`.

## Recommended tools and practices (as of 2026-06-15)

### For: one source of truth, read by every agent

- **Author `AGENTS.md` at the repo root; make `CLAUDE.md` a symlink to it.** `ln -s AGENTS.md CLAUDE.md`: zero duplicated bytes, impossible to drift. This is the canonical setup. Ladders up by guaranteeing every harness reads identical instructions. See `references/claude-integration.md`.
- **Use the `@AGENTS.md` import when symlinks are unavailable.** A `CLAUDE.md` containing `@AGENTS.md` (optionally followed by Claude-specific notes) keeps AGENTS.md authoritative without a filesystem link, required on Windows without Developer Mode. Ladders up by preserving portability. Note the cost: recursive imports cap at **four hops**, and the bridge import consumes one, leaving three for AGENTS.md's own nested imports (a symlink consumes none). For mixed-OS teams whose AGENTS.md has few or no nested imports, this cost is negligible and portability wins.
- **Commit the link and document the Windows caveat** in a one-line comment or contributing note. Ladders up by making the bridge survive a fresh clone everywhere.

### For: the file earns its place in context

- **Lead with runnable commands.** Build, test, lint, run: exact invocations the agent can paste. Ladders up by making the most-used content immediately actionable.
- **Keep the root file under ~200 lines.** Trim anything an agent would not act on. Ladders up by ensuring Claude loads it in full with high adherence.
- **Borrow the section menu, not all sections.** Project overview, build/test commands, code style, testing, security, commit/PR conventions, deployment: include only those that change agent behavior. See `references/agents-md-spec.md`.

### For: hierarchy resolves predictably

- **Ship one AGENTS.md per subproject in monorepos.** Tailored instructions live nearest the code they govern; nearest-file-wins does the routing. Ladders up by scoping rules to where they are true. See `references/agents-md-spec.md`.
- **Keep root rules root-wide.** Anything contradicted by a subproject belongs in that subproject's file, not the root. Ladders up by eliminating cross-level contradictions.

### For: the Claude bridge is portable and durable

- **Run `/init` to augment, not fork.** In a repo that already has AGENTS.md, `/init` reads it and folds relevant parts into the generated CLAUDE.md; prefer keeping AGENTS.md canonical and adding only Claude-specific notes below an `@AGENTS.md` import. Ladders up by preventing a second source of truth. See `references/claude-integration.md`.
- **Verify with `/memory`.** After wiring, `/memory` lists the loaded instruction files; confirm CLAUDE.md (resolving to AGENTS.md) appears. Ladders up by proving the bridge works before relying on it.

## References

- `references/agents-md-spec.md`: the agents.md format, recommended sections, monorepo nesting/precedence, and the supporting-tool ecosystem.
- `references/claude-integration.md`: how Claude Code discovers and loads CLAUDE.md (load order, full-tree walk, `@import` four-hop limit, subdirectory on-demand loading), the symlink vs `@AGENTS.md` decision, the Windows caveat, and `/init`/`/memory` behavior.
- `references/agents-md-template.md`: a starter AGENTS.md with the common sections, ready to fill in.
- https://agents.md/ (canonical spec)
- https://code.claude.com/docs/en/memory (Claude Code memory / CLAUDE.md behavior)

## Continual improvement

File drift, gaps, or proposed updates at
https://github.com/AgentParadise/agentic-primitives/issues
