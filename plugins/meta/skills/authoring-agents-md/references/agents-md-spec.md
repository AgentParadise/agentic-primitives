# The AGENTS.md format

Source: https://agents.md/ (the canonical spec), stewarded by the Agentic AI
Foundation under the Linux Foundation, with contributions from OpenAI, Google,
Cursor, Amp, and Factory. This file distills the spec as of 2026-06-15.

## What it is and why it exists

AGENTS.md is "a README for agents: a dedicated, predictable place to provide
the context and instructions to help AI coding agents work on your project."

The split with README.md is intentional:

- **README.md** serves humans: quick start, description, contribution guide.
- **AGENTS.md** serves agents: the extra, sometimes detailed context an agent
  needs (build steps, tests, conventions) that would clutter a human README.

Keeping them separate keeps the README focused on contributors while giving
agents precise, machine-actionable guidance in a known location.

## Format

Standard Markdown. **No required fields, no schema.** From the spec: "AGENTS.md
is just standard Markdown. Use any headings you like; the agent simply parses
the text you provide." Choose the sections that change agent behavior; omit the
rest.

## Recommended sections

Popular choices (use the ones that apply):

- **Project overview**: what the project is, in two or three lines.
- **Build and test commands**: exact, runnable invocations.
- **Code style guidelines**: formatter, lint rules, naming conventions.
- **Testing instructions**: how to run the suite, what must pass.
- **Security considerations**: secret handling, sensitive paths.
- **Commit message and pull request guidelines**: conventional commits, PR
  template expectations.
- **Deployment steps**: if agents are expected to deploy or release.

## Nested AGENTS.md (monorepos)

Multiple AGENTS.md files can coexist in a hierarchy. Agents "automatically read
the nearest file in the directory tree, so the closest one takes precedence and
every subproject can ship tailored instructions." The OpenAI monorepo ships 88
nested files as the canonical example.

Precedence, exactly: **the closest AGENTS.md to the edited file wins; explicit
user chat prompts override everything.** Put repo-wide truth at the root and
subproject-specific truth in each subproject's file. Do not duplicate a rule at
multiple levels: scope it to the level where it is true.

Many agents will also "attempt to execute relevant programmatic checks and fix
failures before finishing the task," so listing the check commands directly is
high-leverage.

## Ecosystem (who reads it natively)

60,000+ open-source projects use AGENTS.md. Supporting tools include OpenAI
Codex, Google Jules, Factory, Aider, goose, VS Code, Cognition Devin,
Windsurf, GitHub Copilot, Cursor, RooCode, and Zed.

**Claude Code is the exception**: it reads `CLAUDE.md`, not `AGENTS.md`. See
`claude-integration.md` for the bridge.

## Best practices (from the spec)

1. **Create at the repository root.** Many agents can scaffold one on request.
2. **Conflict resolution:** closest file wins; explicit chat prompts override.
3. **Automation:** agents attempt relevant programmatic checks and fix failures
   before finishing, so list those checks.
4. **Living documentation:** update it as the project changes.
5. **Monorepo structure:** one file per subproject for tailored instructions.
