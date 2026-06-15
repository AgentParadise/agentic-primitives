# Wiring AGENTS.md to Claude Code

Source: https://code.claude.com/docs/en/memory (Claude Code memory docs) as of
2026-06-15. Claude Code reads `CLAUDE.md`, **not** `AGENTS.md`. To keep
AGENTS.md the single source of truth, bridge CLAUDE.md to it.

## The two sanctioned bridges

### Symlink (preferred, canonical setup)

```bash
ln -s AGENTS.md CLAUDE.md
```

Zero duplicated content; the two files literally cannot diverge. Commit the
symlink. Use this whenever you do not need Claude-specific instructions beyond
what AGENTS.md already says.

### `@AGENTS.md` import (fallback, and the Windows option)

When you need Claude-only additions, or when symlinks are unavailable, make
`CLAUDE.md` a thin file that imports AGENTS.md and appends Claude-specific notes:

```markdown
@AGENTS.md

## Claude Code

Use plan mode for changes under `src/billing/`.
```

Claude loads the imported file at session start, then appends the rest. This
keeps AGENTS.md authoritative while letting CLAUDE.md carry a small Claude-only
tail.

### Windows caveat

On Windows, creating a symlink requires Administrator privileges or Developer
Mode. **Use the `@AGENTS.md` import on repos with Windows contributors** (or
document the requirement). A committed symlink will not materialize on a plain
Windows clone.

## How Claude Code discovers and loads CLAUDE.md

- **Full-tree walk upward.** Claude walks up the directory tree from the current
  working directory, loading every `CLAUDE.md` and `CLAUDE.local.md` it finds
  along the way. There is **no fixed level cap** on this ancestor walk: running
  in `foo/bar/` loads `foo/bar/CLAUDE.md`, `foo/CLAUDE.md`, and so on up to root.
- **Ancestors load in full at launch.** Files above the cwd are concatenated
  into context immediately, ordered filesystem-root → cwd (so the closest file
  is read last and effectively wins on conflicts).
- **Subdirectories load on demand.** `CLAUDE.md` files *below* the cwd are not
  loaded at launch; they load when Claude reads files in those subdirectories.
  This mirrors AGENTS.md nearest-file-wins behavior in a monorepo.

### Load order / precedence (broadest → most specific)

1. **Managed policy**: `/Library/Application Support/ClaudeCode/CLAUDE.md`
   (macOS), `/etc/claude-code/CLAUDE.md` (Linux/WSL),
   `C:\Program Files\ClaudeCode\CLAUDE.md` (Windows). Org-wide; cannot be
   excluded.
2. **User**: `~/.claude/CLAUDE.md`. Personal, all projects.
3. **Project**: `./CLAUDE.md` or `./.claude/CLAUDE.md`. Team-shared via VCS.
   This is where the AGENTS.md bridge lives.
4. **Local**: `./CLAUDE.local.md`. Personal, gitignored.

### `@import` syntax and the four-hop limit

CLAUDE.md can pull in other files with `@path/to/file`. Relative paths resolve
against the importing file. Imported files can themselves import, to a
**maximum recursion depth of four hops**. (This four-hop import limit is the
real number behind the common "five levels deep" misconception: the ancestor
directory walk itself is uncapped.) Imports are expanded into context at launch,
so an `@AGENTS.md` import loads the full AGENTS.md every session.

### Why this favors the symlink

The four-hop budget counts depth from the file Claude opens, and this is the
decisive difference between the two bridges:

- **Symlink:** `CLAUDE.md` *is* AGENTS.md at the filesystem level (same inode).
  Claude opens AGENTS.md as the root file (hop 0), so AGENTS.md's own `@imports`
  get the full four hops beneath it.
- **`@AGENTS.md` import:** CLAUDE.md is the root (hop 0) and AGENTS.md is hop 1.
  Nested imports inside AGENTS.md now have only three hops left. The bridge
  spends one hop just to reach AGENTS.md.

So `@AGENTS.md` → `@a` → `@b` → `@c` → `@d` overflows under the import bridge but
not under the symlink. This only bites when AGENTS.md itself imports deeply; for
a flat AGENTS.md with no nested imports there is no practical difference, and the
import's cross-platform portability is the deciding factor instead.

## `/init` and `/memory`

- **`/init`** in a repo that already has `AGENTS.md` reads it and folds the
  relevant parts into the generated CLAUDE.md (it also reads `.cursorrules`,
  `.devin/rules/`, `.windsurfrules`). To keep AGENTS.md canonical, prefer the
  `@AGENTS.md` import over letting `/init` fork a parallel copy.
- **`/memory`** lists every CLAUDE.md / CLAUDE.local.md / rule file loaded in the
  session. After wiring, run it to confirm CLAUDE.md (resolving to AGENTS.md)
  appears and is loaded.

## Notes that affect authoring

- CLAUDE.md is delivered as a user message (context), **not** enforced
  configuration: specificity raises adherence, but nothing guarantees
  compliance. For hard enforcement, use hooks or managed settings, not the file.
- Target **under 200 lines** per file; longer files reduce adherence. Splitting
  via `@import` aids organization but does **not** reduce context: imported
  files still load in full at launch.
- Block-level HTML comments (`<!-- ... -->`) in CLAUDE.md are stripped before
  injection, so they cost no context, useful for maintainer notes. (They are
  preserved inside code blocks.)
- Project-root CLAUDE.md survives `/compact` (re-read from disk); nested
  subdirectory files reload only when Claude next reads a file there.
