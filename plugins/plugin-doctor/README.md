# 🩺 plugin-doctor

Warns you when installed `agentic-primitives` plugins have newer versions available. Checked at most once a week. Never updates anything on its own — it only tells Claude, who asks you.

## How it works

On `SessionStart`, plugin-doctor:

1. Checks `~/.claude/plugin-doctor/state.json` for when it last refreshed the marketplace catalog.
2. If that was 7+ days ago (or never), runs `claude plugin marketplace update agentic-primitives` to refresh the local catalog cache, then records the new check time — regardless of whether the refresh succeeded, so a network hiccup costs one missed week, not a retry loop.
3. Compares every installed `agentic-primitives` plugin's version (read from `~/.claude/plugins/cache/agentic-primitives/<plugin>/<version>/`) against the catalog version (read from `~/.claude/plugins/marketplaces/agentic-primitives/plugins/<plugin>/.claude-plugin/plugin.json`).
4. If anything's outdated, tells Claude via `additionalContext` — Claude will mention it early in the conversation and ask if you want to update. It will never run `claude plugin update` without you explicitly agreeing.

Only `agentic-primitives`-sourced plugins are checked — not other marketplaces.

## Install

```bash
claude plugin install plugin-doctor@agentic-primitives --scope user
```

## Updating manually

If you don't want to wait for the weekly check:

```bash
claude plugin marketplace update agentic-primitives
claude plugin update <name>@agentic-primitives
```
