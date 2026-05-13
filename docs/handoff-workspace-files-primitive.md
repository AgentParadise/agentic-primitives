# Handoff: WorkspaceFiles primitive for agentic-primitives

**From:** agentic-domain-runner (`feat/per-domain-context-injection` branch)
**To:** Whoever picks up the agentic-primitives entrypoint + primitives work
**Date:** 2026-05-12

## Why this matters

Two consumers want the same workspace-file-staging shape:

1. **agentic-domain-runner** (this homelab project) — host-resident static files (per-domain `CLAUDE.md`, plugins) need to land at known paths inside the workspace container before `claude` starts. Uses **bind-mount + entrypoint copy** today.
2. **Syntropic137** (the larger platform) — generated CLAUDE.md + MinIO-fetched plugins land via `docker cp` / archive PUT after `create_container`, before `start_container`. Uses **`inject_files()`** today.

Both work. Neither is general. Both are reinvented per-consumer. Promoting the contract into `agentic-primitives` lets future orchestrators (Codex-driven, Gemini-driven, K8s-backed) target a single primitive.

## Scope

Add two **first-class file-staging primitives** to agentic-primitives, plus the matching workspace-entrypoint contract that both downstream consumers rely on.

### 1. `WorkspaceFiles.bind_mount(host_path, container_path, read_only)`

For host-resident static content. Cheap, no orchestrator-side state, requires shared filesystem between orchestrator and Docker daemon.

### 2. `WorkspaceFiles.inject(container_path, bytes)`

For generated / object-storage / remote-daemon content. Post-`create_container`, pre-`start_container`. Works regardless of where the daemon runs.

### 3. The workspace entrypoint contract

The runner already bind-mounts the per-domain dir at `/etc/agentic/domain/` and exports a few env vars. The entrypoint must compose the runner's per-domain files into `/workspace/` so Claude's path-safety heuristic doesn't block them. **This is the missing piece blocking agentic-domain-runner's homelab smoke from passing end-to-end.**

## What lands in agentic-primitives

### `providers/workspaces/claude-cli/scripts/entrypoint.sh`

After the existing plugin discovery block, add (specified verbatim in [agentic-domain-runner spec §8.2](https://gitea.neuralempowerment.xyz/HomeLab/agentic-domain-runner/src/branch/feat/per-domain-context-injection/docs/superpowers/specs/2026-05-12-per-domain-context-injection-design.md) and [ADR-013](https://gitea.neuralempowerment.xyz/HomeLab/agentic-domain-runner/src/branch/feat/per-domain-context-injection/docs/adrs/013-per-task-docker-volume.md)):

```bash
# -----------------------------------------------------------------------------
# Per-domain context composition (agentic-domain-runner integration)
# -----------------------------------------------------------------------------
# The orchestrator bind-mounts the domain's directory at /etc/agentic/domain
# read-only and sets AGENTIC_DOMAIN_CONTEXT + AGENTIC_DOMAIN_PLUGINS +
# AGENTIC_ALLOWED_TOOLS. Compose the agent-visible /workspace/CLAUDE.md
# (preamble + domain content) and copy plugin trees into /workspace/.agentic-plugins/.

if [ -d "/etc/agentic/domain" ]; then
    AGENTIC_CONTEXT_REL="${AGENTIC_DOMAIN_CONTEXT:-CLAUDE.md}"
    AGENTIC_CONTEXT_SRC="/etc/agentic/domain/${AGENTIC_CONTEXT_REL}"

    if [ -f "${AGENTIC_CONTEXT_SRC}" ]; then
        cat > /workspace/CLAUDE.md <<EOF
<!-- BEGIN AGENTIC RUNNER PREAMBLE (system-managed, do not edit) -->

You are running inside an Agentic Domain Runner workspace.

- Domain: \`${AGENTIC_DOMAIN:-unknown}\`
- Task ID: \`${AGENTIC_TASK_ID:-(none)}\`
- Session ID: \`${AGENTIC_SESSION_ID:-(unknown)}\`

**Cross-session context** — If this task has prior sessions, this is your
own past work. Read it before doing anything irreversible:

- \`/workspace/TASK.md\` — your running notes from prior sessions.
  You own this file. Update it as you work.
- \`GET ${AGENTIC_RUNNER_URL:-(unset)}/tasks/${AGENTIC_TASK_ID}/transcript\`
  Full chronological transcript across every session of this task.
- \`GET ${AGENTIC_RUNNER_URL:-(unset)}/tasks/${AGENTIC_TASK_ID}/summary\`
  Cost + tool-use rollup.

Use bearer token from \`AGENTIC_RUNNER_READ_TOKEN\`. This token is
read-only — you cannot create or cancel tasks with it.

<!-- END AGENTIC RUNNER PREAMBLE -->

EOF
        cat "${AGENTIC_CONTEXT_SRC}" >> /workspace/CLAUDE.md
        chmod 600 /workspace/CLAUDE.md
    fi

    # Per-domain plugins. AGENTIC_DOMAIN_PLUGINS is a colon-separated list
    # of plugin directory names under /etc/agentic/domain/plugins/.
    if [ -n "${AGENTIC_DOMAIN_PLUGINS:-}" ]; then
        mkdir -p /workspace/.agentic-plugins
        IFS=':' read -ra _plugins <<< "${AGENTIC_DOMAIN_PLUGINS}"
        for plugin in "${_plugins[@]}"; do
            src="/etc/agentic/domain/plugins/${plugin}"
            if [ -d "${src}" ]; then
                cp -a "${src}" "/workspace/.agentic-plugins/${plugin}"
                AGENTIC_PLUGIN_FLAGS="${AGENTIC_PLUGIN_FLAGS} --plugin-dir /workspace/.agentic-plugins/${plugin}"
            fi
        done
        export AGENTIC_PLUGIN_FLAGS
    fi

    # Per-domain allowed_tools. Space-separated env → repeated --allowedTools
    # flags the cmd wrapper can shell-expand into the claude invocation.
    if [ -n "${AGENTIC_ALLOWED_TOOLS:-}" ]; then
        AGENTIC_ALLOWED_FLAGS=""
        for tool in ${AGENTIC_ALLOWED_TOOLS}; do
            AGENTIC_ALLOWED_FLAGS="${AGENTIC_ALLOWED_FLAGS} --allowedTools ${tool}"
        done
        export AGENTIC_ALLOWED_FLAGS
    fi
fi
```

The homelab domain.toml's `cmd` wrapper would then expand `$AGENTIC_ALLOWED_FLAGS` alongside `$AGENTIC_PLUGIN_FLAGS`:

```toml
cmd = ["sh", "-c", "exec claude -p --dangerously-skip-permissions $AGENTIC_PLUGIN_FLAGS $AGENTIC_ALLOWED_FLAGS \"$@\"", "wrapper"]
```

### `lib/python/agentic_isolation/workspace_files.py` (or similar)

Promote a `WorkspaceFiles` helper offering both staging modes:

```python
class WorkspaceFiles:
    """Stage files into a workspace container before it starts.

    Two staging modes, complementary:
      - bind_mount(): host-resident static content, no copy cost
      - inject(): generated content / remote-fetched content, works
        against remote Docker daemons too
    """

    def bind_mount(self, host_path: Path, container_path: str, read_only: bool = True) -> Mount: ...

    def inject(self, container_id: str, container_path: str, content: bytes) -> None:
        """Streams a tar archive into the running container via the Docker
        archive API. Must be called after create_container, before start.
        """
        ...
```

agentic-domain-runner consumes `bind_mount` via its Rust port (`FileStager` trait in `src/ports/file_stager.rs`). Syntropic137 consumes `inject` via its existing `WorkspaceProvisionHandler`. Both should target the **same conventions** documented here so a single workspace image works for both.

### Conventions (the actual primitive)

- Per-domain content lands at **`/etc/agentic/domain/`** read-only.
- Generated / per-session content lands directly in **`/workspace/`**.
- The entrypoint owns the composition of `/workspace/CLAUDE.md` from preamble + content.
- Per-domain plugins live at **`/workspace/.agentic-plugins/<plugin-name>/`** with `--plugin-dir` flags appended to `AGENTIC_PLUGIN_FLAGS`.
- Env-var contract (orchestrator → entrypoint):
  - `AGENTIC_DOMAIN_CONTEXT` (path relative to `/etc/agentic/domain/`)
  - `AGENTIC_DOMAIN_PLUGINS` (colon-separated plugin names)
  - `AGENTIC_ALLOWED_TOOLS` (space-separated tool names)
  - `AGENTIC_DOMAIN`, `AGENTIC_TASK_ID`, `AGENTIC_SESSION_ID` (identity)
  - `AGENTIC_RUNNER_URL`, `AGENTIC_RUNNER_READ_TOKEN` (callback)

## Why both modes (don't pick one)

| Property | `bind_mount` | `inject` |
|---|---|---|
| Content lives on | Orchestrator host filesystem | Anywhere (memory, MinIO, generated) |
| Setup cost | Zero (Docker reads from host FS) | Tar stream over Docker API |
| Works against remote Docker daemon | No | Yes |
| Works against K8s pod | No (volumes only) | Yes (via kubectl cp equivalent) |
| Content-addressed (SHA-pinned) | Caller's responsibility | Easy |
| Generated content (interpolated CLAUDE.md) | Awkward (write temp file first) | Natural |

Pick `bind_mount` when you have a static host path and a local Docker daemon. Pick `inject` when content is dynamic or the daemon is remote. Most homelab orchestrators want `bind_mount`; most cloud orchestrators want `inject`.

## Acceptance criteria

1. agentic-primitives `providers/workspaces/claude-cli/scripts/entrypoint.sh` composes `/workspace/CLAUDE.md` from the preamble + the bind-mounted per-domain content when `/etc/agentic/domain/CLAUDE.md` exists.
2. agentic-primitives `providers/workspaces/claude-cli/scripts/entrypoint.sh` copies per-domain plugins into `/workspace/.agentic-plugins/<name>/` and appends `--plugin-dir` flags to `AGENTIC_PLUGIN_FLAGS`.
3. The `WorkspaceFiles` helper exposes both `bind_mount` and `inject` with the conventions above.
4. agentic-domain-runner's `live_claude_sees_domain_claude_md` smoke (currently disabled because Claude's path-safety refuses `/etc/agentic/`) passes against the updated workspace image. Verifies the composition lands `/workspace/CLAUDE.md` with both the preamble and homelab's domain content concatenated.
5. Syntropic137's existing `inject_files()` path can be re-expressed in terms of `WorkspaceFiles.inject()` without regression.

## How to verify locally

```bash
# 1. Build the updated workspace image
cd /Users/neural/Code/AgentParadise/agentic-primitives
docker build -t agentic-workspace-claude-cli:dev providers/workspaces/claude-cli

# 2. Use it from the runner
cd /Users/neural/Code/HomeLab/agentic-domain-runner
# In examples/domains/homelab/domain.toml, temporarily change:
#   image = "agentic-workspace-claude-cli:dev"

# 3. Run the runner with credentials loaded
cargo build --release
DOMAIN_RUNNER_BIND=127.0.0.1:8788 \
DOMAIN_RUNNER_AUTH_TOKEN=full DOMAIN_RUNNER_READ_TOKEN=read \
DOMAIN_RUNNER_STORE_URL=sqlite:/tmp/smoke.db \
DOMAIN_RUNNER_DOMAINS_DIR=examples/domains \
./target/release/agentic-domain-runner &

# 4. Ask Claude what's in its CLAUDE.md — it should now see the domain content
curl -s -X POST -H "Authorization: Bearer full" -H 'content-type: application/json' \
  -d '{"prompt":"Read /workspace/CLAUDE.md and reply with the first H1 heading only."}' \
  http://127.0.0.1:8788/domains/homelab/tasks
# Poll the session; expected output: "# Homelab domain"
```

## Pointers

- **agentic-domain-runner branch with the bind-mount side wired up**: `feat/per-domain-context-injection` at https://gitea.neuralempowerment.xyz/HomeLab/agentic-domain-runner
- **Spec**: `docs/superpowers/specs/2026-05-12-per-domain-context-injection-design.md` on that branch
- **ADR-012** (bind-mount vs inject_files reasoning): `docs/adrs/012-bind-mount-file-staging.md`
- **ADR-013** (per-task volume + preamble composition): `docs/adrs/013-per-task-docker-volume.md`
- **Voice OS handoff v2** (downstream context for what this enables): `docs/handoff-from-agentic-domain-runner-v2.md`

## Scope discipline

This is **only the workspace-file-staging primitive**. Out of scope:

- Anything about how plugins are *fetched* (the orchestrator's concern; agentic-domain-runner uses bind-mount, Syntropic137 uses MinIO).
- Anything about how the content is *generated* (orchestrator's concern; agentic-domain-runner uses static files, Syntropic137 interpolates).
- Anything about K8s adaptation (future work; `inject` is the seam that enables it but no K8s code lands here).
- Anything about open-code / Codex / Gemini orchestrators (future work; same seam).

The primitive is the *contract*, not the implementations.
