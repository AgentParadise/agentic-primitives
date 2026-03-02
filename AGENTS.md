# AGENTS.md

## What Is This

Agentic Primitives — atomic building blocks for AI agent systems. This repo contains Claude Code plugins and Python libraries that provide reusable capabilities (SDLC, research, workspace management, observability, etc.) for agent-powered workflows.

## Repo Structure

```
plugins/                  ← Claude Code plugins
  sdlc/                     SDLC automation (PR, review, test)
  workspace/                Workspace management
  research/                 Web research capabilities
  meta/                     Meta/self-improvement
  docs/                     Documentation generation
  notifications/            Notification handling
  observability/            Logging & monitoring
lib/python/               ← Python packages
  agentic_events/           Event bus
  agentic_isolation/        Sandboxing
  agentic_logging/          Structured logging
providers/                ← Workspace providers (Docker, local)
.claude-plugin/           ← Marketplace config + root plugin settings
docs/                     ← ADRs, guides
tests/                    ← Test suite
```

## Plugin Structure

Every plugin must follow this layout:

```
plugins/<name>/
├── .claude-plugin/plugin.json  ← REQUIRED: name, version, description
├── hooks/hooks.json            ← Hook definitions
├── hooks/handlers/             ← Hook handler scripts
├── commands/                   ← Slash commands (optional)
├── skills/                     ← Skills (optional)
├── agents/                     ← Agent definitions (optional)
├── README.md
└── CHANGELOG.md
```

## Common Tasks

**Add a plugin:**
1. Create `plugins/<name>/` with `plugin.json` and `hooks/hooks.json`
2. Register in `.claude-plugin/marketplace.json`
3. Add to root README tables
4. `just qa-fix` → PR

**Update a plugin:**
1. Bump version in `plugin.json` + update `CHANGELOG.md`
2. `just qa-fix` → PR

**QA:**
- `just qa` — full validation suite
- `just qa-fix` — full suite + auto-format

**Tests:**
- `uv run pytest`

## Conventions

- **Commits:** Conventional (`feat:`, `fix:`, `docs:`, `chore:`, etc.)
- **Python:** Use `uv`, never `pip`
- **Architecture decisions:** Document in `docs/adrs/`
- **Reference:** [Claude Code Plugin Docs](https://docs.anthropic.com/en/docs/claude-code/plugins)
