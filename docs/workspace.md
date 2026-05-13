# The Workspace

The workspace is the isolation + observability boundary between an
orchestrator and the AI agent it runs. Every Claude task spawned by
[agentic-domain-runner](https://gitea.neuralempowerment.xyz/HomeLab/agentic-domain-runner),
every Syntropic137 workflow phase, every future Codex / Gemini job runs
inside one of these.

This page is the canonical reference for what the workspace does and what
it exposes. For the design rationale see
[`docs/adrs/035-workspace-injection-contract.md`](adrs/035-workspace-injection-contract.md);
for the full design see
[`docs/superpowers/specs/2026-05-12-workspace-injection-contract-design.md`](superpowers/specs/2026-05-12-workspace-injection-contract-design.md).

## What the workspace is

A container image — today `agentic-workspace-claude-cli:<tag>`, more
provider variants later — with an entrypoint that prepares the agent's
environment before exec'ing the orchestrator's CMD.

The entrypoint owns three responsibilities:

1. **Inject** orchestrator-supplied context.
2. **Isolate** the agent's effects (tmpfs, read-only mounts, network
   whitelisting).
3. **Observe** what the agent did (git hooks → JSONL on stderr,
   stream-json on stdout, output artifacts on disk).

This page focuses on **(1) inject** since that's the part with a
documented contract. Isolate and observe are status quo and described
briefly below.

## Inject — what the orchestrator puts in

### Bind-mount layout

The orchestrator bind-mounts a directory at `/etc/agentic/workspace/`
(read-only). The entrypoint reads from it.

```
/etc/agentic/workspace/        (orchestrator bind-mounts here, read-only)
  CLAUDE.md                      optional, project-level agent context
  plugins/<name>/                optional, zero or more Claude plugins
    .claude-plugin/plugin.json
    skills/, commands/, hooks/, agents/
  agents/<name>.md               optional, loose subagents (frontmatter + body)
```

All three are optional. Missing files or missing directories are silently
skipped — backwards-compatible with deployments that don't yet bind-mount
anything.

### Env vars (all optional)

| Name | Purpose |
|---|---|
| `AGENTIC_WORKSPACE_CONTEXT` | Path inside `/etc/agentic/workspace/` for the context file. Default `CLAUDE.md`. |
| `AGENTIC_WORKSPACE_PLUGINS` | Colon-separated plugin names to enable. Default: all valid. |
| `AGENTIC_WORKSPACE_AGENTS` | Colon-separated loose-subagent names. Default: all valid. |

That's the **entire** workspace contract. Three optional env vars + one
bind-mount path.

## What the agent sees

After the entrypoint runs:

| Path | Origin |
|---|---|
| `/workspace/CLAUDE.md` | Copy of the selected context file. |
| `/workspace/.agentic-plugins/<name>/` | Copy of each enabled per-workspace plugin tree. |
| `/workspace/artifacts/input/` | Created (or orchestrator-bind-mounted). |
| `/workspace/artifacts/output/` | Created (or orchestrator-bind-mounted). |
| `~/.claude/agents/<name>.md` | Copy of each enabled loose subagent. |
| `$AGENTIC_PLUGIN_FLAGS` | Pre-built `--plugin-dir` string covering baked-in + per-workspace plugins. |

## Tool restrictions live inside agents and plugins

The workspace contract deliberately has **no `AGENTIC_WORKSPACE_ALLOWED_TOOLS`**
env var. Tool restrictions belong inside subagent frontmatter
(`tools: [Read, Bash, ...]`) or plugin permission settings — the policy
ships with the agent that enforces it. See Claude's
[subagents docs](https://code.claude.com/docs/en/sub-agents.md).

## Observe — what comes out

Status quo, no changes from the injection contract:

- **Git hooks** — workspace ships `prepare-commit-msg`; the observability
  plugin ships `post-commit`, `pre-push`, `post-merge`, `post-rewrite`,
  `post-checkout`. Both sets are symlinked into `~/.git-hooks` and
  activated via `git config --global core.hooksPath`.
- **JSONL on stderr** — the observability plugin emits structured events
  (every tool use, prompt, completion). Orchestrators merge stderr into
  stdout and parse.
- **Stream-json on stdout** — when the orchestrator invokes
  `claude -p --output-format stream-json --verbose`, every turn (tool_use,
  tool_result, token usage, total cost) lands on stdout as JSONL.
- **Output artifacts** — agent writes to `/workspace/artifacts/output/`;
  orchestrator collects from the bind-mounted host path after exit.

## Python helper

For orchestrators that prefer a library import over hand-constructing the
mount + env:

```python
from agentic_isolation import WorkspaceFiles

wf = WorkspaceFiles(client=docker_client)

# Bind-mount mode (host-resident content)
mount = wf.bind_mount(workspace_dir, "/etc/agentic/workspace", read_only=True)
container = client.containers.create(image, mounts=[mount], ...)

# Inject mode (generated content)
container = client.containers.create(image, ...)
wf.inject(container.id, "/etc/agentic/workspace/CLAUDE.md", composed_bytes)
container.start()
```

The bind-mount path is cheap and works when orchestrator and Docker
daemon share a filesystem. The inject path works against any daemon
(remote, K8s) — the right choice when content is generated per-task.

## Building the workspace image

```bash
# Canonical:
just build-workspace-claude-cli

# Or via the script directly:
uv run scripts/build-provider.py claude-cli
```

The build tags `agentic-workspace-claude-cli:latest` plus a version tag
matching the bundled Claude CLI release.

## Pointers

- **Design spec:** [`docs/superpowers/specs/2026-05-12-workspace-injection-contract-design.md`](superpowers/specs/2026-05-12-workspace-injection-contract-design.md)
- **ADR:** [`docs/adrs/035-workspace-injection-contract.md`](adrs/035-workspace-injection-contract.md)
- **Implementation plan:** [`docs/superpowers/plans/2026-05-12-workspace-injection-contract.md`](superpowers/plans/2026-05-12-workspace-injection-contract.md)
- **Entrypoint script (source of truth for behavior):** [`providers/workspaces/claude-cli/scripts/entrypoint.sh`](../providers/workspaces/claude-cli/scripts/entrypoint.sh)
- **Python helper:** [`lib/python/agentic_isolation/agentic_isolation/workspace_files.py`](../lib/python/agentic_isolation/agentic_isolation/workspace_files.py)
- **Integration tests:** [`tests/integration/test_entrypoint_workspace_injection.py`](../tests/integration/test_entrypoint_workspace_injection.py)
- **Sibling spec (consumer side, runner):** [agentic-domain-runner per-domain context injection design](https://gitea.neuralempowerment.xyz/HomeLab/agentic-domain-runner/src/branch/main/docs/superpowers/specs/2026-05-12-per-domain-context-injection-design.md)
