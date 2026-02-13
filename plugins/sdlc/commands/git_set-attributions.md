---
description: Configure git commit and PR attribution (empty = hide Claude attribution)
argument-hint: "[commit-text] [pr-text]"
allowed-tools: Read, Edit, Write
---

# Set Attributions

Configure the `attribution` setting in Claude Code to control the co-authored-by text on commits and PRs.

## Arguments

- `$1` — Commit attribution text (use `""` or `empty` to hide)
- `$2` — PR attribution text (use `""` or `empty` to hide)
- No arguments — set both to empty (hide all attribution)

## Instructions

1. Read the current attribution settings from `.claude/settings.json` (project) or `~/.claude/settings.json` (global)
2. If no arguments provided, set both `commit` and `pr` to `""` (hides attribution)
3. If arguments provided, set the values accordingly
4. The `attribution` field goes in `settings.json`:

```json
{
  "attribution": {
    "commit": "",
    "pr": ""
  }
}
```

- `""` (empty string) = hide attribution entirely
- Any other string = use that as the attribution text
- Omitting the field = use Claude Code's default attribution

5. Ask the user whether to apply to **project** (`.claude/settings.json`) or **global** (`~/.claude/settings.json`)
6. Merge the `attribution` key into the existing settings without overwriting other fields
