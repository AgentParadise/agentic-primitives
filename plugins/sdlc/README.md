# SDLC Plugin

Software Development Lifecycle primitives for Claude Code agents.

## Skills
- **commit** — Structured commit message generation
- **review** — Code review assistance
- **pre-commit-qa** — Pre-commit quality assurance checks
- **qa-setup** — QA environment setup
- **testing-expert** — Testing strategy and implementation
- **prioritize** — PR/issue prioritization
- **centralized-configuration** — Infrastructure configuration management
- **browser** — Headless browser automation via Playwright CLI (UI testing, visual QA, scraping)

## Commands
- **merge** — Git merge workflow
- **push** — Git push workflow
- **review** — Code review command
- **fetch** — Fetch and prioritize PRs/issues
- **merge-cycle** — Full merge cycle workflow
- **worktree** — Manage git worktrees in isolated sibling directory
- **validate-install** — Validate plugin installation, hooks, and security protections
- **browser** — Direct browser automation (open, interact, screenshot)
- **browser:ui-review** — Parallel QA validation against YAML user stories

## Agents
- **browser-qa-agent** — QA validation agent that executes user stories with step-by-step screenshots and structured PASS/FAIL reporting

## Hooks
Security hooks, validators (bash, file, PII), and git hooks (pre-push, post-commit, etc.)

## Browser Automation

The browser automation primitive provides headless browser control for SDLC workflows. Built on `playwright-cli`.

### Dependencies

- `playwright-cli` — Playwright CLI wrapper (must be installed separately)

### Components

| Layer | Primitive | Purpose |
|-------|-----------|---------|
| Skill | `browser/SKILL.md` | Core browser automation capability |
| Command | `browser.md` | Direct browser interaction slash command |
| Command | `browser_ui-review.md` | Parallel QA validation orchestrator |
| Agent | `browser-qa-agent.md` | Isolated QA agent for user story execution |

### Maturity Model

| Level | Description | Status |
|-------|-------------|--------|
| L1 | Single-page screenshot | ✅ Ready |
| L2 | Multi-step interaction flows | ✅ Ready |
| L3 | Parallel user story validation | ✅ Ready |
| L4 | Visual regression diffing | 🔜 Planned |
| L5 | Continuous monitoring | 🔜 Planned |

### Examples

See `examples/justfile-browser` for ready-to-use recipes and `examples/user-stories-sample.yaml` for YAML story format.
