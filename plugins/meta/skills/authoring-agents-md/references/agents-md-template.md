# Starter AGENTS.md template

Copy the block below to the repo root as `AGENTS.md`, then delete sections that
do not apply and replace the placeholders. Keep it under ~200 lines so Claude
loads it in full. Then wire Claude Code per `claude-integration.md`
(`ln -s AGENTS.md CLAUDE.md`, or an `@AGENTS.md` import on Windows).

Lead with runnable commands; cut anything an agent would not act on.

```markdown
# <Project Name>

<One or two lines: what this project is and what an agent should know first.>

## Setup

\`\`\`bash
<install deps, e.g. uv sync, npm install, just bootstrap>
\`\`\`

## Build / test / lint

\`\`\`bash
<build command>
<test command, e.g. uv run pytest>
<lint/format command, e.g. just qa-fix>
\`\`\`

Run these checks and fix failures before finishing a task.

## Project layout

- `<dir>/`: <what lives here>
- `<dir>/`: <what lives here>

## Conventions

- <Specific, verifiable rule, e.g. "2-space indentation">
- <e.g. "API handlers live in `src/api/handlers/`">
- <Commit style, e.g. "Conventional commits: feat:, fix:, docs:, chore:">

## Testing

- <How to run the suite, what must pass before a PR>

## Security

- <Secret handling, sensitive paths, what never to commit>

## Pull requests

- <PR expectations: title format, required checks, review gates>
```

## Monorepo note

For a monorepo, place a tailored `AGENTS.md` in each subproject with only the
instructions specific to that subtree. The nearest file to an edited file wins,
so the root file should hold repo-wide truth and each subproject file should
hold its own build/test/convention overrides, never duplicate a rule across
levels.
