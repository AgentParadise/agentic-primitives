---
description:
globs:
alwaysApply: true
---
# Agentic Primitives

Atomic building blocks for AI agent systems. Claude Code plugins + Python libraries for reusable agent capabilities (SDLC, research, workspace management, observability, notifications).

> **For fresh agent sessions:** The workspace contract is documented at
> [`docs/workspace.md`](docs/workspace.md). It describes how the workspace
> image takes inbound context (CLAUDE.md, plugins, subagents) via a
> bind-mount at `/etc/agentic/workspace/` and three `AGENTIC_WORKSPACE_*`
> env vars, then composes them into `/workspace/`. The entrypoint script
> at [`providers/workspaces/claude-cli/scripts/entrypoint.sh`](providers/workspaces/claude-cli/scripts/entrypoint.sh)
> (section 5.5) is the source of truth for behavior;
> [ADR-035](docs/adrs/035-workspace-injection-contract.md) is the decision
> record. The sibling consumer (the agentic-domain-runner) is at
> `/Users/neural/Code/HomeLab/agentic-domain-runner`.

## Repo Structure

```
plugins/                  ← Claude Code plugins
  sdlc/                     SDLC automation (PR, review, test)
  workspace/                Workspace lifecycle + observability hooks
  research/                 Web research capabilities
  meta/                     Meta/self-improvement tools
  docs/                     Documentation generation
  notifications/            Push notifications (ntfy, macOS, Pushover)
  observability/            Full-spectrum JSONL event emission
lib/python/               ← Python packages
  agentic_events/           Session recording & playback
  agentic_isolation/        Docker workspace sandboxing
  agentic_logging/          Structured logging
providers/                ← Workspace providers (Docker, local)
.claude-plugin/           ← Marketplace config (marketplace.json)
docs/                     ← ADRs, guides
tests/                    ← Test suite
```

## Plugin Structure

Every plugin must have `.claude-plugin/plugin.json`. Other dirs are optional.

```
plugins/<name>/
├── .claude-plugin/plugin.json  ← REQUIRED: name, version, description
├── hooks/hooks.json            ← Hook definitions (optional)
├── hooks/handlers/             ← Hook handler scripts (optional)
├── commands/                   ← Slash commands (optional)
├── skills/                     ← Skills (optional)
├── agents/                     ← Agent definitions (optional)
├── README.md
└── CHANGELOG.md
```

**plugin.json schema:** Only `name` is required. Valid fields: `name`, `version`, `description`, `author`, `homepage`, `repository`, `license`, `keywords`, `commands`, `agents`, `skills`, `hooks`, `mcpServers`, `outputStyles`, `lspServers`. Unknown keys cause install failures.

## Common Tasks

**Add a plugin:**
1. Create `plugins/<name>/.claude-plugin/plugin.json`
2. Add hooks, commands, skills, agents as needed
3. **Register in `.claude-plugin/marketplace.json`** ← required for `claude plugin install`
4. Add to root `README.md` install table + feature matrix
5. `just qa-fix` → PR with conventional commit

**Update a plugin:**
1. Make changes
2. Bump version in `.claude-plugin/plugin.json` (CI enforces version bump on content changes)
3. Update `CHANGELOG.md`
4. `just qa-fix` → PR

**QA:**
- `just qa` — full validation suite
- `just qa-fix` — full suite + auto-format

**Tests:**
- `uv run pytest`

## Conventions

- **Commits:** Conventional format — `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`
- **Python:** Use `uv`, never `pip`
- **Architecture decisions:** Document in `docs/adrs/`
- **Plugin docs:** [Claude Code Plugins](https://code.claude.com/docs/en/plugins.md) · [Reference](https://code.claude.com/docs/en/plugins-reference.md) · [Marketplaces](https://code.claude.com/docs/en/plugin-marketplaces.md)
