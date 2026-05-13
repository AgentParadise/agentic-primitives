# Workspace Injection Contract — Design

**Date:** 2026-05-12
**Status:** Draft — awaiting user review
**Owner:** @neuralempowerment
**Sibling spec:** [`agentic-domain-runner`'s per-domain context injection](https://gitea.neuralempowerment.xyz/HomeLab/agentic-domain-runner/src/branch/main/docs/superpowers/specs/2026-05-12-per-domain-context-injection-design.md) (already merged; this work fulfills the workspace-image side of that contract).

## 1. Goal

Extend the `agentic-workspace-claude-cli` image's entrypoint with a small, universal **file injection** primitive so any orchestrator — agentic-domain-runner, Syntropic137, future Codex/Gemini wrappers — can hand a workspace its context, plugins, and subagents through one shared mechanism. Plus a Python helper for orchestrators that prefer a library import to writing the mount + env construction themselves.

## 2. Workspace Responsibility (the full picture)

The workspace image is the **isolation + observability boundary** between an orchestrator and a Claude agent. Things cross the wall in both directions, and `agentic-primitives` owns the wall and the mechanisms for both directions. This work extends the **inbound** side; the wall itself and the **outbound** side are status quo and unchanged.

```
                  agentic-primitives owns this entire boundary
                  ┌──────────────────────────────────────────┐
   orchestrator   │              workspace container         │   orchestrator
   ─────────────► │  inbound (this spec)                     │   reads
       writes     │    /etc/agentic/workspace/ (read-only)   │   stdout/stderr
                  │      → CLAUDE.md, plugins, agents        │   ◄────────
                  │                                          │
                  │  the wall                                │
                  │    tmpfs /home/agent (wipes on restart)  │
                  │    read-only context mount               │
                  │    network mode + whitelist              │
                  │    per-task volume at /workspace         │
                  │                                          │
                  │  outbound (status quo, unchanged)        │
                  │    git hooks → JSONL on stderr           │
                  │    --output-format stream-json on stdout │
                  │    /workspace/artifacts/output/          │
                  └──────────────────────────────────────────┘
```

### Inbound — context injection (what this spec adds)

| Need | Mechanism | Owner |
|---|---|---|
| Project-level context for the main agent | Bind-mount + entrypoint copy → `/workspace/CLAUDE.md` | agentic-primitives entrypoint |
| Per-workspace plugins (skills, commands, hooks, subagents) | Bind-mount + entrypoint copy → `/workspace/.agentic-plugins/<name>/` + `--plugin-dir` | agentic-primitives entrypoint |
| Loose per-workspace subagents (not packaged in a plugin) | Bind-mount + entrypoint copy → `~/.claude/agents/<name>.md` | agentic-primitives entrypoint |
| Input artifacts | Bind-mount → `/workspace/artifacts/input/` directly | orchestrator (no entrypoint action) |
| Per-workspace env vars (`PORT_FOO`, `DEBUG`, …) | `docker create --env` | orchestrator (no entrypoint action) |
| Network / internet locking | Docker network mode + whitelisting | orchestrator (no entrypoint action) |

### The wall — isolation (status quo)

- Tmpfs `/home/agent` (state wiped on restart).
- Read-only `/etc/agentic/workspace/` mount (agent can't tamper with its own context).
- Network mode + whitelist (orchestrator decides at `docker create`).
- Per-task named volume at `/workspace` (cross-session state stays inside the wall — orchestrator's choice whether to attach one).

### Outbound — observability (status quo)

- **Git hooks composed at startup** — workspace ships `prepare-commit-msg` (operator Co-authored-by attribution); observability plugin ships `post-commit`, `pre-push`, `post-merge`, `post-rewrite`, `post-checkout`. Entrypoint symlinks both sets into `~/.git-hooks` and sets `git config --global core.hooksPath`, so every repo cloned inside the container emits commit events automatically.
- **Observability plugin emits JSONL to stderr** — every tool use, prompt, completion.
- **`claude -p --output-format stream-json --verbose`** when orchestrator opts in — every turn (tool_use, tool_result, token usage, total cost) lands on stdout as JSONL.
- **Output artifacts** — agent writes to `/workspace/artifacts/output/`, orchestrator collects from the bind-mounted host path after container exit.

## 3. Bind-Mount Layout (orchestrator → container)

```
/etc/agentic/workspace/                      (read-only, entrypoint reads)
  CLAUDE.md                                    optional, project-level context
  plugins/                                     optional, zero or more plugins
    <plugin-name>/
      .claude-plugin/plugin.json               required (validates a plugin dir)
      skills/, commands/, hooks/, agents/      any combination
  agents/                                      optional, loose subagents
    <subagent-name>.md                         YAML frontmatter + system prompt

/workspace/artifacts/input/                  (read-only bind-mount, optional)
/workspace/artifacts/output/                 (read-write bind-mount, optional)
/workspace/                                  (per-task volume, optional)
```

Orchestrator constructs only `/etc/agentic/workspace/`. The other paths are existing conventions (artifacts subdirs already created by entrypoint section 5; per-task volume is the orchestrator's choice).

## 4. Env Vars the Entrypoint Reads

All optional. Sensible defaults for everything.

| Name | Purpose |
|---|---|
| `AGENTIC_WORKSPACE_CONTEXT` | Path inside `/etc/agentic/workspace/` for the main context file. Default `CLAUDE.md`. |
| `AGENTIC_WORKSPACE_PLUGINS` | Colon-separated plugin directory names under `/etc/agentic/workspace/plugins/` to enable. Default: all discovered. |
| `AGENTIC_WORKSPACE_AGENTS` | Colon-separated loose subagent base names under `/etc/agentic/workspace/agents/` to enable. Default: all discovered. |

That is the **entire** env-var contract introduced by this work. Three vars, all optional.

### What is deliberately NOT here

- **No `AGENTIC_WORKSPACE_ALLOWED_TOOLS`** — tool restrictions belong inside subagent frontmatter (`tools: [Read, Bash, ...]`) or inside plugin permission settings. Bundling them keeps the policy together with the agent that enforces it. Adding a separate env var would duplicate state and invite drift.
- **No `AGENTIC_ALLOWED_FLAGS` output** — same reason.
- **No identity env vars** (`AGENTIC_TASK_ID`, `AGENTIC_SESSION_ID`, `AGENTIC_RUNNER_URL`, etc.) — those are orchestrator-specific. The runner sets them on its containers; the workspace image doesn't know or care. They're part of each orchestrator's contract with its own agents, not part of the workspace contract.

## 5. Entrypoint Actions

New section `5.5 — Workspace Context Composition`, slotted between the existing section 5 (workspace directories) and section 6 (Execute CMD).

The script defines configuration constants at the top so paths and defaults appear once. Helper functions handle the two "filter list or discover all" patterns shared between plugins and agents.

```bash
# -----------------------------------------------------------------------------
# 5.5 Workspace Context Composition
# -----------------------------------------------------------------------------
# Universal inbound seam — copies orchestrator-supplied context, plugins,
# and subagents from /etc/agentic/workspace/ (bind-mounted read-only) into
# the agent-visible workspace + Claude config locations. Skips silently when
# the bind-mount is absent so existing deployments stay backwards-compatible.
#
# See: docs/workspace.md and ADR-035 for the contract this implements.

# --- Configuration constants ---------------------------------------------
readonly INJECT_MOUNT="/etc/agentic/workspace"
readonly INJECT_MOUNT_PLUGINS="${INJECT_MOUNT}/plugins"
readonly INJECT_MOUNT_AGENTS="${INJECT_MOUNT}/agents"

readonly INJECT_TARGET_CONTEXT="/workspace/CLAUDE.md"
readonly INJECT_TARGET_PLUGINS="/workspace/.agentic-plugins"
readonly INJECT_TARGET_AGENTS="${HOME}/.claude/agents"

readonly INJECT_DEFAULT_CONTEXT="CLAUDE.md"
readonly INJECT_PLUGIN_MANIFEST=".claude-plugin/plugin.json"

# --- Helpers --------------------------------------------------------------
# Echo each name in $1 (colon-separated) on its own line; if $1 is empty,
# fall back to all immediate children of directory $2 with optional suffix
# $3 stripped from the basenames.
__inject_names() {
    local explicit="$1" dir="$2" strip_ext="${3:-}"
    if [ -n "${explicit}" ]; then
        printf '%s\n' "${explicit}" | tr ':' '\n'
        return
    fi
    [ -d "${dir}" ] || return
    for f in "${dir}"/*${strip_ext}; do
        [ -e "${f}" ] || continue
        local base; base="$(basename "${f}")"
        [ -n "${strip_ext}" ] && base="${base%${strip_ext}}"
        printf '%s\n' "${base}"
    done
}

# --- Actions --------------------------------------------------------------
if [ -d "${INJECT_MOUNT}" ]; then
    # 1. Context (CLAUDE.md).
    ctx_src="${INJECT_MOUNT}/${AGENTIC_WORKSPACE_CONTEXT:-${INJECT_DEFAULT_CONTEXT}}"
    if [ -f "${ctx_src}" ]; then
        cp "${ctx_src}" "${INJECT_TARGET_CONTEXT}"
        chmod 644 "${INJECT_TARGET_CONTEXT}"
    fi

    # 2. Per-workspace plugins (appended to existing AGENTIC_PLUGIN_FLAGS
    # built by section 2 for baked-in plugins).
    if [ -d "${INJECT_MOUNT_PLUGINS}" ]; then
        mkdir -p "${INJECT_TARGET_PLUGINS}"
        while IFS= read -r plugin; do
            [ -n "${plugin}" ] || continue
            src="${INJECT_MOUNT_PLUGINS}/${plugin}"
            [ -f "${src}/${INJECT_PLUGIN_MANIFEST}" ] || continue
            cp -a "${src}" "${INJECT_TARGET_PLUGINS}/${plugin}"
            AGENTIC_PLUGIN_FLAGS="${AGENTIC_PLUGIN_FLAGS} --plugin-dir ${INJECT_TARGET_PLUGINS}/${plugin}"
        done < <(__inject_names "${AGENTIC_WORKSPACE_PLUGINS:-}" "${INJECT_MOUNT_PLUGINS}")
        export AGENTIC_PLUGIN_FLAGS
    fi

    # 3. Loose subagents (plugin-bundled subagents come along for free via
    # the --plugin-dir flag in action 2 — Claude auto-discovers them).
    if [ -d "${INJECT_MOUNT_AGENTS}" ]; then
        mkdir -p "${INJECT_TARGET_AGENTS}"
        while IFS= read -r agent; do
            [ -n "${agent}" ] || continue
            src="${INJECT_MOUNT_AGENTS}/${agent}.md"
            [ -f "${src}" ] || continue
            cp "${src}" "${INJECT_TARGET_AGENTS}/${agent}.md"
        done < <(__inject_names "${AGENTIC_WORKSPACE_AGENTS:-}" "${INJECT_MOUNT_AGENTS}" ".md")
    fi
fi
```

**Why this shape:**
- All paths are defined once at the top. Any future move of `/etc/agentic/workspace/` or `/workspace/.agentic-plugins/` is a single-line edit.
- The `__ws_names` helper collapses the two "filter via env var OR discover everything" patterns into one reusable function.
- Each action is then a tight read-loop driven by the helper's stream of names.
- `readonly` on the constants prevents accidental shadowing later in the script.
- Existing `AGENTIC_PLUGIN_FLAGS` (built by section 2 for baked-in plugins) is **appended to**, not replaced — baked-in plugins still load, per-workspace plugins layer on top.

## 6. Python Helper — `WorkspaceFiles`

Lives at `lib/python/agentic_isolation/workspace_files.py`. Class-based, sync methods. Library import only — no new process, no memory cost unless imported.

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import docker
import docker.types


@dataclass
class WorkspaceFiles:
    """Stage files into a workspace container before it starts.

    Two staging modes, complementary:
      bind_mount()  — host-resident static content; cheap, no copy
      inject()      — generated / object-storage content; works against
                      remote daemons + K8s pods (sync after create,
                      before start)
    """

    client: docker.DockerClient

    def bind_mount(
        self,
        host_path: Path,
        container_path: str,
        read_only: bool = True,
    ) -> docker.types.Mount:
        """Build a Mount descriptor for `container.create(mounts=[...])`."""
        return docker.types.Mount(
            target=container_path,
            source=str(host_path.resolve()),
            type="bind",
            read_only=read_only,
        )

    def inject(
        self,
        container_id: str,
        container_path: str,
        content: bytes,
    ) -> None:
        """Stream `content` as a single-file tar archive into the named
        container. Must be called after `container.create()` and before
        `container.start()`.
        """
        # tar the bytes, put_archive to the container.
        # (implementation detail; uses docker SDK's put_archive)
        ...
```

Scope discipline:

- **No high-level "stage everything for a workspace" method.** Orchestrators compose their own staging logic — they know whether they're loading a domain config (homelab) or a workflow definition (Syntropic137). The helper provides only the primitives.
- **No tar/untar helpers exposed.** `inject()` is the single API for archive-style staging; if a caller wants to inject a whole directory tree they build the tar themselves and call `inject()` with the archive bytes.
- **Sync only.** File staging is one-shot per container; no event-loop benefit.

## 7. Conventions (the actual durable primitive)

These conventions form the cross-orchestrator contract any future workspace consumer can target.

- Per-workspace content lands at **`/etc/agentic/workspace/`** read-only.
- Generated / per-session content lands directly in **`/workspace/`**.
- The entrypoint composes the agent-visible `/workspace/CLAUDE.md` as a verbatim copy from the bind-mount. No templating, no preamble. Orchestrators that want a preamble pre-compose it into the source file.
- Per-workspace plugins live at **`/workspace/.agentic-plugins/<plugin-name>/`** with `--plugin-dir` flags appended to `AGENTIC_PLUGIN_FLAGS`.
- Loose subagents land at **`~/.claude/agents/<name>.md`** (user scope, Claude's standard discovery path).
- Env-var contract: only `AGENTIC_WORKSPACE_CONTEXT` / `_PLUGINS` / `_AGENTS`. Three.

## 8. Testing Strategy

Pytest + `docker run --rm` against the built image, mirroring the existing `tests/integration/test_entrypoint_lsp_settings.py` pattern.

### 8.1 Integration tests (Docker required)

- `test_entrypoint_copies_workspace_context_md` — bind-mount a tmpdir with a known `CLAUDE.md`, run the container, assert `/workspace/CLAUDE.md` matches.
- `test_entrypoint_copies_workspace_plugins` — bind-mount with `plugins/foo/.claude-plugin/plugin.json`, assert `/workspace/.agentic-plugins/foo/` exists and `echo $AGENTIC_PLUGIN_FLAGS` includes `--plugin-dir /workspace/.agentic-plugins/foo`.
- `test_entrypoint_copies_loose_subagents` — bind-mount with `agents/reviewer.md`, assert `~/.claude/agents/reviewer.md` exists with same content.
- `test_entrypoint_filters_plugins_by_env` — bind-mount three plugins, set `AGENTIC_WORKSPACE_PLUGINS=foo:bar` (omitting `baz`), assert only foo+bar copied.
- `test_entrypoint_skips_when_no_workspace_mount` — no bind-mount, ensure existing behavior unchanged (no errors, no /workspace/CLAUDE.md, baked-in plugins still load).
- `test_entrypoint_skips_invalid_plugin_dir` — bind-mount a `plugins/garbage/` with no `.claude-plugin/plugin.json`, assert it's NOT copied (validates the discovery filter).

### 8.2 Unit tests for `WorkspaceFiles`

- `test_bind_mount_descriptor_shape` — call returns a `docker.types.Mount` with the expected source/target/type/read_only.
- `test_bind_mount_resolves_relative_paths` — relative host_path becomes absolute in the descriptor.
- `test_inject_archives_and_calls_put_archive` — use a mock `docker.DockerClient`; assert `put_archive` called with a tar containing the right path + bytes.

### 8.3 Contract test

- `test_entrypoint_appends_to_agentic_plugin_flags_does_not_replace` — bind-mount one per-workspace plugin, run the container, assert `$AGENTIC_PLUGIN_FLAGS` contains BOTH the baked-in plugins (observability, sdlc, workspace) AND the new one. Catches accidental clobbering.

## 9. Phasing

Coordinated two-repo rollout. Each phase ships green and is independently useful.

| Phase | Repo | Scope |
|-------|------|-------|
| **A — Env rename in `agentic-domain-runner`** | runner | Rename merged `AGENTIC_DOMAIN_*` env vars to `AGENTIC_WORKSPACE_*` to match the contract this spec defines. Also rename the bind-mount source path from `/etc/agentic/domain/` to `/etc/agentic/workspace/`. ~64 unit + 55 smoke stay green. Internal-only churn; no consumers depend on these names yet. |
| **B — Entrypoint composition** | agentic-primitives | Add section 5.5 to `providers/workspaces/claude-cli/scripts/entrypoint.sh`. Integration tests in 8.1. Backwards compatible — existing deployments without `/etc/agentic/workspace/` keep working. |
| **C — Python helper** | agentic-primitives | Add `lib/python/agentic_isolation/workspace_files.py` with `WorkspaceFiles` class. Unit tests in 8.2. Library import only — no behavior change for callers that don't import it. |
| **D — Image release + runner pickup** | both | Tag the new workspace image. agentic-domain-runner bumps the image tag in `examples/domains/homelab/domain.toml`. Re-run the `live_claude_sees_domain_claude_md` smoke (currently blocked by Claude's path-safety refusing `/etc/agentic/`) — should now pass because the entrypoint copies CLAUDE.md into `/workspace/` which Claude treats as in-scope. |

## 10. Out of Scope / Follow-up

- **Cron-loop stdin-keepalive** — the `claude -p --input-format stream-json --output-format stream-json` mode discovered in [`2026-05-12-keeping-claude-alive.md`](https://gitea.neuralempowerment.xyz/HomeLab/agentic-domain-runner_worktrees/20260512_experiments/docs/experiments/2026-05-12-keeping-claude-alive.md). That's a runner-side decision about *how to invoke* claude, not a workspace-image concern. Captured for the runner when it wants long-lived cron support.
- **Non-Claude provider workspaces** (Codex, Gemini) — each provider gets its own image with its own entrypoint. The convention names (`/etc/agentic/workspace/`, `CLAUDE.md`, `plugins/`, `agents/`) are claude-specific. A future `agentic-workspace-codex-cli` would carry its own equivalent (e.g. `CODEX.md`, `tools/`, etc.). Not a shared concept across images.
- **K8s / remote-Docker workspace backend** — `WorkspaceFiles.inject()` is the seam (works against any daemon, not just local). When we get there, no API changes needed; the orchestrator just swaps `docker.DockerClient` for a remote-aware one.
- **Per-domain scoped tokens** — captured as `agentic-domain-runner` issue [001](https://gitea.neuralempowerment.xyz/HomeLab/agentic-domain-runner/src/branch/main/docs/issues/001-per-domain-scoped-tokens.md). Runner concern, not workspace concern.
- **Output artifact post-processing inside the entrypoint** — out of scope. The agent writes to `/workspace/artifacts/output/`, the orchestrator collects after container exit. No entrypoint involvement.

## 11. Documentation Deliverables

The spec is the design artifact; production docs need three additions so a future reader doesn't have to dig through `docs/superpowers/specs/` to understand the workspace.

### 11.1 `docs/workspace.md` — canonical workspace doc (NEW)

A short page in the top-level `docs/` directory that's the single canonical reference for what the workspace is and what it does. Sections:

- **What the workspace is** — the isolation + observability boundary; one paragraph framing.
- **Inject / isolate / observe** — the three responsibilities described in §2 of this spec.
- **What you put in** — bind-mount layout + env vars from §3 and §4.
- **What lands inside** — the post-entrypoint state from §3 (file paths the agent sees).
- **What comes out** — the existing observability story (git hooks, JSONL stderr, stream-json stdout, output artifacts).
- **Pointers** — link to ADR-035 (the decision record), this spec (the design), and the entrypoint script (the source of truth for behavior).

Lives at `docs/workspace.md`. Keep tight — under 200 lines. The spec carries the detail; this page is the orientation.

### 11.2 README section — `## Workspace` (UPDATE)

Add a focused section to the top-level `README.md` that:

- Says what the workspace is in two sentences.
- Lists the three responsibilities (inject / isolate / observe).
- Links to `docs/workspace.md` as the canonical reference.
- Removes any deeper detail currently in the README that now belongs in `docs/workspace.md`.

The README's job is signposting; deep content lives elsewhere.

### 11.3 ADR-035 — Workspace injection contract (NEW)

`docs/adrs/035-workspace-injection-contract.md`. Captures the durable decisions:

- The workspace image is the cross-orchestrator isolation + observability boundary.
- Inbound injection happens through a single bind-mount at `/etc/agentic/workspace/` + three optional env vars.
- Tool restrictions live inside subagent / plugin definitions, not in a separate env-var concept.
- Identity vars (task id, session id, callback URLs, tokens) are orchestrator-specific and stay out of the workspace contract.
- `WorkspaceFiles.bind_mount` + `WorkspaceFiles.inject` are the two complementary staging primitives — bind-mount for host-resident static content, inject for generated / remote-fetched / cross-daemon content.

ADR template lives at `docs/adrs/000-adr-template.md`. Number 035 is the next available after the current 034.

### 11.4 Sibling-repo doc sync

`agentic-domain-runner` already has its consumer-side spec, plan, and ADRs (010–013) merged on `main`. When Phase A (env-rename) lands, those references update too:

- Runner spec §4 path string `/etc/agentic/domain/` → `/etc/agentic/workspace/`
- Runner spec / ADR-012 / ADR-013 env-var references `AGENTIC_DOMAIN_*` → `AGENTIC_WORKSPACE_*`
- Voice OS handoff v2 env-var table updated.

These are mechanical sed-style changes; captured in the implementation plan as Phase A.

## 12. Open Questions

None at time of writing. Update this section if review surfaces any.
