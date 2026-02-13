---
title: "ADR-033: Plugin-Native Workspace Images"
status: proposed
created: 2026-02-12
updated: 2026-02-12
author: Neural
tags: [architecture, plugins, docker, isolation, observability, validation]
---

# ADR-033: Plugin-Native Workspace Images

## Status

**Proposed**

- Created: 2026-02-12
- Author(s): Neural
- Related: ADR-027 (Provider-Based Workspace Images), ADR-029 (Simplified Event System), ADR-032 (V2 Simplified Structure)

## Context

### The Plugin Migration

The repo migrated from a primitives-based architecture to a plugin-based architecture (ADR-032). Locally, plugins are installed via `claude plugin install` and register their hooks, skills, and commands through `hooks.json` and `plugin.json`. This works well.

However, the Docker workspace images (ADR-027) were built **before** this migration. They still use the old approach:

1. Hooks are copied as loose files into `/opt/agentic/hooks/`
2. `entrypoint.sh` manually writes `~/.claude/settings.json` with hardcoded absolute paths to each hook handler
3. Env vars are listed explicitly in the entrypoint (`GITHUB_TOKEN`, `GIT_AUTHOR_NAME`, etc.)
4. No concept of "plugins" exists inside the container

This creates **two divergent code paths** for the same functionality:

| Concern | Local (Plugin) | Docker (Current) |
|---|---|---|
| Hook registration | `hooks.json` with `${CLAUDE_PLUGIN_ROOT}` | Hardcoded paths in `entrypoint.sh` |
| Hook discovery | Claude Code plugin system | Manual `settings.json` generation |
| Env vars / secrets | `os.getenv()` from shell | Must be explicitly listed in entrypoint |
| Adding a new plugin | `claude plugin install` | Modify Dockerfile + entrypoint |
| Observability hooks | `workspace` plugin `hooks.json` | Hardcoded in `settings.json` |
| Security hooks | `sdlc` plugin `hooks.json` | Same hooks, different registration path |

### The Env Var Problem

Tools like the Firecrawl scraper need API keys (`FIRECRAWL_API_KEY`). Locally, they inherit from the shell environment. In Docker isolation, the orchestrator must explicitly pass each env var via `-e` flags or `WorkspaceConfig.secrets`.

Today there is no way for a tool or plugin to declare "I need these env vars" — the `agentic-isolation` library's `WorkspaceConfig` accepts `secrets` and `environment` dicts, but the caller must know what to pass. This leads to:

- Tools that work locally but silently fail in Docker (missing env vars)
- The entrypoint hardcoding knowledge of specific env vars
- No standard discovery mechanism

The `agentic-settings` library attempted to solve this with a Pydantic-based config discovery layer, but it added a dependency into every tool's runtime. With the plugin architecture, a simpler declarative approach is possible.

### Observability Must Be Preserved

The workspace plugin's hooks (`workspace/hooks/handlers/`) emit structured JSONL events via `agentic_events.EventEmitter` to stderr. These events are the **primary observability mechanism** for the agent engineering framework:

- `session_started` / `session_completed` — session lifecycle
- `tool_execution_started` / `tool_execution_completed` — tool-level tracing
- `security_decision` — allow/block audit trail
- `agent_stopped` / `subagent_stopped` — agent lifecycle
- `context_compacted` — context window management
- `system_notification` — system-level alerts
- `user_prompt_submitted` — prompt tracking

These events are captured by the agent runner and stored in TimescaleDB. The Docker image currently has `agentic_events` pre-installed as a wheel, and hooks import it with a `try/except ImportError` fallback (graceful degradation when running locally without the package).

**Any new architecture must preserve this event emission pipeline.** Plugins that emit events must have `agentic_events` available in their Python path, whether running locally or in Docker.

## Decision

### 1. Load Plugins via `--plugin-dir` in Docker

Claude Code supports loading plugins from arbitrary filesystem paths using the `--plugin-dir` flag:

```bash
claude --plugin-dir /opt/agentic/plugins/sdlc \
       --plugin-dir /opt/agentic/plugins/workspace \
       -p "do something"
```

This is the correct mechanism for Docker because:
- **In-place loading** — plugins are used directly from `/opt/agentic/plugins/`, not copied to a cache directory
- **No tmpfs conflict** — `/opt/agentic/plugins/` is a persistent path that survives the tmpfs mount on `/home/agent`
- **`${CLAUDE_PLUGIN_ROOT}`** is set by Claude Code automatically at runtime, resolving to the plugin's actual directory
- **No registration step** — unlike `claude plugin install` (which copies to `~/.claude/plugins/cache/` and would be wiped by tmpfs), `--plugin-dir` works without any setup

Why other approaches don't work in Docker:

| Approach | Problem |
|---|---|
| `claude plugin install` | Copies to `~/.claude/plugins/cache/` — wiped by tmpfs every container start |
| Pre-populating `~/.claude/settings.json` with `enabledPlugins` | Also wiped by tmpfs, and requires plugins in cache first |
| Symlinks from `~/.claude/` to `/opt/agentic/` | Fragile, requires entrypoint to recreate links every start |
| **`--plugin-dir`** | **Works in-place, no caching, no tmpfs issue** |

### 2. Plugin Layout in the Image

Plugins are copied as complete, self-contained directories into the Docker image:

```
/opt/agentic/plugins/
├── sdlc/                    # Security hooks, commit, review, QA
│   ├── .claude-plugin/
│   │   └── plugin.json
│   ├── hooks/
│   │   ├── hooks.json
│   │   └── handlers/
│   │       └── pre-tool-use.py
│   ├── commands/
│   ├── skills/
│   └── ...
└── workspace/               # Observability hooks
    ├── .claude-plugin/
    │   └── plugin.json
    ├── hooks/
    │   ├── hooks.json
    │   └── handlers/
    │       ├── post-tool-use.py
    │       ├── session-start.py
    │       ├── session-end.py
    │       ├── stop.py
    │       ├── subagent-stop.py
    │       └── notification.py
    └── ...
```

**Self-containment constraint**: All files referenced by a plugin must be inside its directory. Claude Code does not follow `../` references outside the plugin root. This is already true for our plugins — hooks reference `${CLAUDE_PLUGIN_ROOT}/hooks/handlers/...` which resolves within the plugin directory.

### 3. Simplified Entrypoint

The entrypoint builds `--plugin-dir` flags dynamically and passes them through to the CMD:

```bash
#!/bin/bash
set -e

# --- 1. Git configuration (unchanged) ---
if [ -n "${GIT_AUTHOR_NAME}" ]; then
    git config --global user.name "${GIT_AUTHOR_NAME}"
    git config --global user.email "${GIT_AUTHOR_EMAIL:-agent@agentic.local}"
fi

# --- 2. GitHub credentials (unchanged) ---
if [ -n "${GITHUB_TOKEN}" ]; then
    git config --global credential.helper store
    echo "https://x-access-token:${GITHUB_TOKEN}@github.com" > ~/.git-credentials
    chmod 600 ~/.git-credentials
fi

# --- 3. Build plugin flags ---
PLUGIN_ARGS=""
for plugin_dir in /opt/agentic/plugins/*/; do
    if [ -f "$plugin_dir.claude-plugin/plugin.json" ]; then
        PLUGIN_ARGS="$PLUGIN_ARGS --plugin-dir $plugin_dir"
    fi
done

# --- 4. Workspace directories (unchanged) ---
mkdir -p /workspace/artifacts/input /workspace/artifacts/output /workspace/repos

# --- 5. Execute CMD with plugin flags ---
exec "$@" $PLUGIN_ARGS
```

The entrypoint **no longer**:
- Writes `~/.claude/settings.json` with hardcoded hook paths
- Knows about specific env vars beyond baseline (git, GitHub)
- Hardcodes which hooks exist or where they are

The plugin system handles all of that via `hooks.json` and `${CLAUDE_PLUGIN_ROOT}`.

### 4. Plugin Env Var Declaration

Add a `requires_env` field to `plugin.json` so plugins can declare what environment variables their tools and hooks need:

```json
{
  "name": "research",
  "version": "1.0.0",
  "description": "Research tools for AI agents",
  "requires_env": {
    "FIRECRAWL_API_KEY": {
      "description": "Firecrawl API key for web scraping. Get from: https://firecrawl.dev",
      "required": false,
      "secret": true
    }
  }
}
```

Fields:
- **`required`**: If `true`, the workspace refuses to start without this var. If `false`, the tool degrades gracefully.
- **`secret`**: If `true`, the value is masked in logs and passed via `WorkspaceConfig.secrets` (not `environment`).
- **`description`**: Human-readable description for onboarding, error messages, and validation output.

### 5. Isolation Layer Auto-Forwards Declared Env Vars

`agentic-isolation` reads plugin manifests and auto-forwards matching env vars from the host into the container:

```python
@dataclass
class WorkspaceConfig:
    # ... existing fields ...

    # Plugin directories to mount/load
    plugins: list[str] = field(default_factory=list)
```

The Docker provider, when given plugin paths:
1. Reads each plugin's `plugin.json` for `requires_env`
2. For `secret: true` vars — reads from host env, passes via `-e` (into `WorkspaceConfig.secrets`)
3. For `secret: false` vars — reads from host env, passes via `-e` (into `WorkspaceConfig.environment`)
4. For `required: true` vars — raises a clear error if not set on the host
5. For `required: false` vars — skips silently if not set
6. Adds `--plugin-dir` flags to the command

The tool inside the container just does `os.getenv("FIRECRAWL_API_KEY")` — works identically in both local and Docker modes.

### 6. Observability Preserved via Python Path

The event emission architecture is unchanged. `agentic_events` is installed as a system package in the Docker image (via wheel, same as today). Hook handlers import it with graceful fallback:

```python
try:
    from agentic_events import EventEmitter
    emitter = EventEmitter(session_id=session_id, output=sys.stderr)
except ImportError:
    emitter = None  # Graceful degradation locally
```

The event flow:

```
Hook handler (loaded via --plugin-dir)
    → EventEmitter (agentic_events, installed as wheel)
        → JSONL to stderr
            → Captured by agent runner (agentic-isolation stream())
                → TimescaleDB / dashboard
```

In Docker: `agentic_events` is always available (pre-installed wheel).
Locally: Hooks degrade gracefully via `try/except ImportError`.

### 7. Dockerfile Changes

```dockerfile
# OLD approach:
# COPY hooks/ /opt/agentic/hooks/

# NEW approach: Copy plugin directories as-is
COPY plugins/ /opt/agentic/plugins/

# Set permissions
RUN chmod -R 755 /opt/agentic/plugins \
    && find /opt/agentic/plugins -name "*.py" -exec chmod 755 {} \; \
    && find /opt/agentic/plugins -name "*.sh" -exec chmod 755 {} \; \
    && chown -R agent:agent /opt/agentic/plugins

# Install Python packages (agentic-events wheel, same as today)
COPY packages/*.whl /tmp/packages/
RUN uv pip install --system --break-system-packages --no-cache /tmp/packages/*.whl \
    && rm -rf /tmp/packages
```

### 8. Plugin Validation Command

A `validate_plugin` command provides automated checks that a plugin is correctly structured and will work in both local and Docker environments. This catches issues at development time rather than at runtime in production.

#### Validation Checks

The validator runs these checks against a plugin directory:

**Structure checks:**

| Check | Rule | Severity |
|---|---|---|
| Manifest exists | `.claude-plugin/plugin.json` must exist | ERROR |
| Manifest valid JSON | Must parse without errors | ERROR |
| Required fields | `name`, `version`, `description` present | ERROR |
| Version format | Must be valid semver | WARN |
| hooks.json valid | If `hooks/hooks.json` exists, must be valid JSON | ERROR |
| Hook handlers exist | Every command referenced in `hooks.json` must exist on disk | ERROR |

**Self-containment checks (critical for Docker `--plugin-dir`):**

| Check | Rule | Severity |
|---|---|---|
| No parent traversal | No `../` references in `hooks.json` commands | ERROR |
| No absolute paths | No `/absolute/path` references (must use `${CLAUDE_PLUGIN_ROOT}`) | ERROR |
| Uses CLAUDE_PLUGIN_ROOT | Hook commands should reference `${CLAUDE_PLUGIN_ROOT}` | WARN |
| No external imports | Python handlers should not `import` from paths outside the plugin (except stdlib and declared dependencies) | WARN |

**Env var checks:**

| Check | Rule | Severity |
|---|---|---|
| requires_env format | Each entry has `description`, `required`, `secret` fields | ERROR |
| Secret vars not defaulted | `secret: true` vars should not have a `default` field | WARN |
| Env vars documented | Every `os.getenv()` call in handler code has a matching `requires_env` entry | WARN |

**Observability checks (for plugins with hooks):**

| Check | Rule | Severity |
|---|---|---|
| Event emitter pattern | Hook handlers that process tool events should emit via `agentic_events` | WARN |
| Stderr for events | `EventEmitter` output should be `sys.stderr`, not `sys.stdout` | ERROR |
| Fail-open pattern | Hook handlers should catch exceptions and fail open (not block on error) | WARN |
| Stdout for decisions | Only security decisions (block/deny) should write to stdout | WARN |

**Security hook checks (for plugins with PreToolUse handlers):**

| Check | Rule | Severity |
|---|---|---|
| Dangerous patterns covered | Must block `rm -rf /`, `chmod 777 /`, force push, etc. | WARN |
| Safe commands allowed | Must allow `ls`, `git status`, `echo`, etc. | ERROR |
| Spoofed test passing | Run the existing `validate_security-hooks` test suite against the handler | ERROR |

#### Implementation

The validator is a standalone Python script that can run in CI, locally, or inside Docker:

```bash
# Validate a single plugin
python3 scripts/validate-plugin.py plugins/sdlc/

# Validate all plugins
python3 scripts/validate-plugin.py plugins/*/

# Validate with Docker-specific checks (stricter)
python3 scripts/validate-plugin.py --mode docker plugins/sdlc/

# CI mode: exit non-zero on any ERROR
python3 scripts/validate-plugin.py --strict plugins/*/
```

Output format:

```
Validating plugin: sdlc (1.0.0)
  [PASS] .claude-plugin/plugin.json exists
  [PASS] Manifest has required fields (name, version, description)
  [PASS] hooks/hooks.json is valid JSON
  [PASS] All hook handlers exist on disk
  [PASS] No parent traversal (../) in hook paths
  [PASS] No absolute paths in hook commands
  [PASS] All hooks use ${CLAUDE_PLUGIN_ROOT}
  [PASS] EventEmitter outputs to stderr
  [PASS] Handlers follow fail-open pattern
  [PASS] Security hooks block dangerous commands (8/8)
  [PASS] Security hooks allow safe commands (4/4)
  [WARN] No requires_env declared (ok if no env vars needed)

Result: 11 passed, 1 warning, 0 errors
```

#### Skill Command

The validator is also exposed as a plugin skill so it can be run interactively:

```
/sdlc:validate-plugin plugins/sdlc/
```

This complements the existing `/sdlc:validate_security-hooks` command, which tests hook behavior specifically. The new command validates the full plugin structure.

#### CI Integration

The validator runs in CI as a pre-merge check:

```yaml
# .github/workflows/validate-plugins.yml
- name: Validate plugins
  run: python3 scripts/validate-plugin.py --strict plugins/*/
```

This prevents merging plugins that would fail in Docker (e.g., a hook with an absolute path that works locally but breaks with `--plugin-dir`).

## Consequences

### Benefits

1. **Single code path** — plugins work identically in local and Docker via `--plugin-dir`, eliminating drift
2. **No tmpfs conflict** — `--plugin-dir` loads plugins in-place from `/opt/agentic/plugins/`, no cache directory needed
3. **Env var discovery** — tools declare what they need in `plugin.json`, isolation layer provides it, `os.getenv()` just works
4. **Observability preserved** — `workspace` plugin's event emission via `agentic_events` is unchanged
5. **Automated validation** — structural, self-containment, env var, observability, and security checks catch issues before production
6. **Extensibility** — adding a new plugin to the image = copying its directory, no Dockerfile/entrypoint changes
7. **Dead code removal** — `agentic-security`, `agentic-settings`, and `agentic-adapters` can be removed

### Risks

1. **`--plugin-dir` flag stability** — this is a Claude Code CLI flag; if it changes in a future version, the entrypoint breaks. Mitigated by pinning Claude Code version in the Dockerfile.
2. **Flag ordering** — `$PLUGIN_ARGS` must be appended in the right position relative to other CLI flags. The entrypoint appends after `"$@"` which should work for `claude -p "prompt"` but needs testing with other subcommands.
3. **Build context staging** — the build script (`scripts/build-provider.py`) needs to stage plugin directories instead of individual hook files.

### Migration Path

1. **Phase 1**: Create `scripts/validate-plugin.py` with structural and self-containment checks. Run against existing plugins to establish baseline.
2. **Phase 2**: Add `requires_env` to `plugin.json` spec. Update existing plugins that need env vars (e.g., research/firecrawl). Add env var checks to validator.
3. **Phase 3**: Update `agentic-isolation` `WorkspaceConfig` to accept `plugins` list, read `requires_env`, auto-forward env vars.
4. **Phase 4**: Rebuild Dockerfile to `COPY plugins/` and update entrypoint to use `--plugin-dir`. Remove hardcoded `settings.json` generation.
5. **Phase 5**: Update `scripts/build-provider.py` to stage plugins instead of hooks.
6. **Phase 6**: Remove `agentic-security`, `agentic-settings`, `agentic-adapters` from `lib/python/`.
7. **Phase 7**: Add `validate-plugins` CI check to `.github/workflows/`.

### Packages to Remove

| Package | Reason |
|---|---|
| `agentic-security` | Validators inlined in SDLC plugin, `SecurityPolicy` class unused |
| `agentic-settings` | Replaced by `requires_env` in `plugin.json` |
| `agentic-adapters` | Built for Agent SDK, no longer used (CLI-based architecture) |

### Packages to Keep

| Package | Reason |
|---|---|
| `agentic-events` | Core observability — used by `workspace` plugin hooks, installed as wheel in Docker |
| `agentic-isolation` | Core execution — provides `AgenticWorkspace`, Docker/local providers, gains plugin awareness |
