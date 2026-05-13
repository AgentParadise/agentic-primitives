# Workspace Injection Contract — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the agentic-primitives workspace injection contract (new entrypoint section + Python helper + docs) plus a coordinated env-var rename in agentic-domain-runner so both repos speak the same `AGENTIC_WORKSPACE_*` vocabulary.

**Architecture:** A new entrypoint section reads from a read-only bind-mount at `/etc/agentic/workspace/` and three optional env vars (`AGENTIC_WORKSPACE_CONTEXT`, `_PLUGINS`, `_AGENTS`), then copies content into `/workspace/CLAUDE.md` + `/workspace/.agentic-plugins/<name>/` + `~/.claude/agents/<name>.md`. Existing plugin discovery (`AGENTIC_PLUGIN_FLAGS`) gets appended-to, never replaced. A `WorkspaceFiles` Python helper exposes `bind_mount()` + `inject()` primitives. A canonical `docs/workspace.md` + ADR-035 + README "Workspace" section make the contract discoverable.

**Tech Stack:** Bash (entrypoint), Python (helper + tests), docker-py (≥7.0), pytest, Docker for integration tests.

**Spec:** `docs/superpowers/specs/2026-05-12-workspace-injection-contract-design.md`

**Branch (this repo, agentic-primitives):** `feat/workspace-injection-contract` (already created).

**Sibling branch (agentic-domain-runner):** `feat/workspace-env-rename` (Phase A — create at the start of Task A.1).

---

## File Map (decisions locked here)

### Phase A — agentic-domain-runner (sibling repo at `/Users/neural/Code/HomeLab/agentic-domain-runner`)

Mechanical renames `AGENTIC_DOMAIN_*` → `AGENTIC_WORKSPACE_*` and path `/etc/agentic/domain/` → `/etc/agentic/workspace/`.

Files to modify:
- `src/runner/mod.rs` — env var exports
- `src/adapters/bind_mount_stager.rs` — env var names + bind-mount target path
- `tests/smoke.rs` — any assertions on env var names (search to verify scope)
- `docs/superpowers/specs/2026-05-12-per-domain-context-injection-design.md` — text references
- `docs/adrs/012-bind-mount-file-staging.md` — path string in narrative
- `docs/adrs/013-per-task-docker-volume.md` — env var refs
- `docs/handoff-from-agentic-domain-runner-v2.md` — env var table
- `examples/domains/homelab/CLAUDE.md` — narrative mentions of env vars
- `STATUS.md` / `README.md` / `CLAUDE.md` — search for stale references

### Phase B — agentic-primitives entrypoint

- Modify: `providers/workspaces/claude-cli/scripts/entrypoint.sh` — insert new section 5.5 between existing sections 5 and 6
- Create: `tests/integration/test_entrypoint_workspace_injection.py` — 6 integration tests against the built image

### Phase C — agentic-primitives Python helper

- Create: `lib/python/agentic_isolation/agentic_isolation/workspace_files.py` — `WorkspaceFiles` class
- Modify: `lib/python/agentic_isolation/agentic_isolation/__init__.py` — export the class
- Create: `lib/python/agentic_isolation/tests/test_workspace_files.py` — 3 unit tests

### Phase D — agentic-primitives docs

- Create: `docs/workspace.md` — canonical workspace reference (≤200 lines)
- Modify: `README.md` — add concise `## Workspace` section linking `docs/workspace.md`
- Create: `docs/adrs/035-workspace-injection-contract.md` — ADR following `docs/adrs/000-adr-template.md` format

### Phase E — release + runner pickup (cross-repo)

- Build + tag a new workspace image
- Update `agentic-domain-runner`'s `examples/domains/homelab/domain.toml` to reference the new tag (separate small PR after Phases A–D land)
- Re-run the previously-blocked live smoke from `agentic-domain-runner` (`live_claude_sees_domain_claude_md`) to verify end-to-end

---

# Phase A — Env-var rename in agentic-domain-runner

Goal: rename `AGENTIC_DOMAIN_*` → `AGENTIC_WORKSPACE_*` and `/etc/agentic/domain/` → `/etc/agentic/workspace/` everywhere in the runner repo so both repos share one vocabulary. Tests stay green.

### Task A.1: Create branch and audit references

**Files:**
- All files in `/Users/neural/Code/HomeLab/agentic-domain-runner` (audit only)

- [ ] **Step 1: Create feature branch**

```bash
cd /Users/neural/Code/HomeLab/agentic-domain-runner
git checkout -b feat/workspace-env-rename
```

- [ ] **Step 2: Audit `AGENTIC_DOMAIN` occurrences**

```bash
grep -rn 'AGENTIC_DOMAIN' --include='*.rs' --include='*.md' --include='*.toml' .
```

Expected: ~6–10 hits across `src/runner/mod.rs`, `src/adapters/bind_mount_stager.rs`, `docs/adrs/012-bind-mount-file-staging.md`, `docs/adrs/013-per-task-docker-volume.md`, `docs/handoff-from-agentic-domain-runner-v2.md`, the spec, and possibly `STATUS.md`.

- [ ] **Step 3: Audit `/etc/agentic/domain` path occurrences**

```bash
grep -rn '/etc/agentic/domain' --include='*.rs' --include='*.md' --include='*.toml' .
```

Expected: a small number of hits in `src/adapters/bind_mount_stager.rs` (the `Mount::bind` target string) and the ADR/spec/handoff docs.

- [ ] **Step 4: No commit yet — just confirm scope is small**

### Task A.2: Rename env vars in runner code

**Files:**
- Modify: `src/runner/mod.rs`
- Modify: `src/adapters/bind_mount_stager.rs`
- Modify: `src/ports/file_stager.rs` (comments only, if any reference the old name)

- [ ] **Step 1: Replace env var names in `src/runner/mod.rs`**

Search for the env-var push block (committed in `2df9bb2` per the runner's git log). Change:

```rust
req.env.push(("AGENTIC_DOMAIN".into(), req.domain.clone()));
```

to:

```rust
req.env.push(("AGENTIC_WORKSPACE".into(), req.domain.clone()));
```

If `AGENTIC_TASK_ID`, `AGENTIC_SESSION_ID`, `AGENTIC_RUNNER_URL`, `AGENTIC_RUNNER_READ_TOKEN` are also pushed: leave them. Those are not part of this rename — they're runner-side identity vars, orthogonal to the workspace contract.

- [ ] **Step 2: Replace env var names in `src/adapters/bind_mount_stager.rs`**

Change the env tuples in `stage()`:

```rust
let env = vec![
    ("AGENTIC_WORKSPACE_CONTEXT".into(), plan.context_rel.to_string_lossy().into_owned()),
    ("AGENTIC_WORKSPACE_PLUGINS".into(), plugin_names.join(":")),
    // NOTE: AGENTIC_ALLOWED_TOOLS dropped per workspace-injection-contract spec §4.
    // Tool restrictions belong inside subagent/plugin definitions, not as a separate env.
];
```

`AGENTIC_ALLOWED_TOOLS` is intentionally removed — that field on `StagingPlan` is no longer used. Decide between (a) removing the field from `StagingPlan` entirely, or (b) keeping it as deprecated. **(a)** is cleaner; the spec is explicit that allowed_tools moves out of the contract.

If choosing (a):
- Remove `pub allowed_tools: Vec<String>` from `src/ports/file_stager.rs::StagingPlan`
- Remove the corresponding field from `Domain::staging_plan()` in `src/domains/mod.rs`
- Remove `pub allowed_tools: Vec<String>` from `Domain` if no other code reads it (grep first)
- Update unit tests in `src/adapters/bind_mount_stager.rs::tests` to drop the field

- [ ] **Step 3: Rename the bind-mount target path**

In `src/adapters/bind_mount_stager.rs::stage()`, change:

```rust
Mount::bind(plan.domain_dir.clone(), "/etc/agentic/domain", true)
```

to:

```rust
Mount::bind(plan.domain_dir.clone(), "/etc/agentic/workspace", true)
```

- [ ] **Step 4: Run unit tests — must stay green**

```bash
cargo test --lib
```

Expected: same number of tests as before (allowed_tools test should be removed or updated). All green.

- [ ] **Step 5: Run smoke tests — must stay green**

```bash
cargo test --test smoke
```

Expected: 55 smoke tests, all green. The smoke suite doesn't assert env var names directly.

- [ ] **Step 6: Commit**

```bash
git add src/
git commit -m "refactor(workspace): rename AGENTIC_DOMAIN_* env vars to AGENTIC_WORKSPACE_*

Coordinated with agentic-primitives workspace-injection-contract spec.

- AGENTIC_DOMAIN_CONTEXT → AGENTIC_WORKSPACE_CONTEXT
- AGENTIC_DOMAIN_PLUGINS → AGENTIC_WORKSPACE_PLUGINS
- AGENTIC_ALLOWED_TOOLS removed entirely (tool restrictions live inside
  subagent/plugin definitions per spec §4)
- /etc/agentic/domain/ bind-mount target renamed to /etc/agentic/workspace/

StagingPlan loses its allowed_tools field; Domain loses its allowed_tools
field. Unit tests updated.

Identity env vars (AGENTIC_TASK_ID/SESSION_ID/RUNNER_URL/READ_TOKEN) are
unchanged — they're runner-specific identity, not part of the workspace
contract."
```

### Task A.3: Update docs/specs/ADRs in the runner repo

**Files:**
- Modify: `docs/superpowers/specs/2026-05-12-per-domain-context-injection-design.md`
- Modify: `docs/adrs/012-bind-mount-file-staging.md`
- Modify: `docs/adrs/013-per-task-docker-volume.md`
- Modify: `docs/handoff-from-agentic-domain-runner-v2.md`
- Modify: `examples/domains/homelab/CLAUDE.md`
- Modify: `STATUS.md`, `README.md`, `CLAUDE.md` (root)

- [ ] **Step 1: Mechanical replace across docs**

```bash
cd /Users/neural/Code/HomeLab/agentic-domain-runner

# env var names
git ls-files '*.md' '*.toml' | xargs sed -i '' \
    -e 's/AGENTIC_DOMAIN_CONTEXT/AGENTIC_WORKSPACE_CONTEXT/g' \
    -e 's/AGENTIC_DOMAIN_PLUGINS/AGENTIC_WORKSPACE_PLUGINS/g' \
    -e 's|/etc/agentic/domain|/etc/agentic/workspace|g'
```

Note: macOS `sed` uses `-i ''`; on Linux drop the empty string.

- [ ] **Step 2: Hand-review for prose that needs broader rewording**

Some docs may use prose like "the domain bind-mount" — that's referring to the path, not the env var, and after the rename it should read "the workspace bind-mount". Manually scan:

```bash
git diff --stat
git diff docs/ examples/
```

Apply prose adjustments where the surrounding sentence reads awkwardly.

- [ ] **Step 3: Update the `AGENTIC_ALLOWED_TOOLS` references in docs**

The spec, ADRs, and handoff doc mention `AGENTIC_ALLOWED_TOOLS` as an exported env var. That env var is now removed. Update each reference to explain the new model: tool restrictions live inside subagent frontmatter (`tools: [...]`) or plugin permissions. Specifically:

- `docs/handoff-from-agentic-domain-runner-v2.md` — env var table: drop the `AGENTIC_ALLOWED_TOOLS` row; add a one-sentence note pointing at Claude's subagents docs (`https://code.claude.com/docs/en/sub-agents.md`) for the replacement mechanism.
- `docs/superpowers/specs/2026-05-12-per-domain-context-injection-design.md` §4.3 (allowed_tools) and §8.1 (env exports): same rewrite.
- `docs/adrs/012-bind-mount-file-staging.md` and `013-per-task-docker-volume.md`: usually just the env-var name — sed should have handled it. Confirm.

- [ ] **Step 4: Confirm `cargo test` still green after doc edits**

```bash
cargo test --lib && cargo test --test smoke
```

Expected: still green (docs don't affect tests; sanity-check).

- [ ] **Step 5: Commit**

```bash
git add docs/ examples/ STATUS.md README.md CLAUDE.md
git commit -m "docs: sync to AGENTIC_WORKSPACE_* env vars and /etc/agentic/workspace/ path

Coordinated with agentic-primitives workspace-injection-contract.
Replaces all AGENTIC_DOMAIN_* references and the bind-mount path
in the per-domain-context-injection spec, ADRs 012/013, Voice OS
handoff v2, homelab CLAUDE.md, and top-level status/readme files.

AGENTIC_ALLOWED_TOOLS references removed; tool restrictions now live
inside subagent frontmatter and plugin permissions (spec §4)."
```

### Task A.4: Push branch, open PR, merge

- [ ] **Step 1: Push and open PR**

```bash
git push -u origin feat/workspace-env-rename
```

PR title: `refactor(workspace): rename AGENTIC_DOMAIN_* to AGENTIC_WORKSPACE_*`

PR body (paste into Gitea): summarize the two commits + link to the agentic-primitives spec for context.

- [ ] **Step 2: Merge with `--no-ff` (matching prior workflow)**

After the PR is approved:

```bash
git checkout main
git pull --ff-only
git merge --no-ff feat/workspace-env-rename -m "Merge feat/workspace-env-rename: AGENTIC_WORKSPACE_* vocabulary

Coordinated with agentic-primitives workspace-injection-contract."
git push origin main
git branch -d feat/workspace-env-rename
```

**Phase A exit criteria:** runner's `main` speaks `AGENTIC_WORKSPACE_*` everywhere, 64 unit + 55 smoke + 1 OpenAPI all green, `AGENTIC_ALLOWED_TOOLS` removed.

---

# Phase B — Entrypoint composition in agentic-primitives

Goal: add section 5.5 to the workspace entrypoint per spec §5. New behavior is purely additive — when `/etc/agentic/workspace/` is bind-mounted, files get composed into the agent-visible workspace. When not, nothing happens.

### Task B.1: Write the first failing integration test (context copy)

**Files:**
- Create: `tests/integration/test_entrypoint_workspace_injection.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_entrypoint_workspace_injection.py`:

```python
"""Integration tests for the workspace injection entrypoint section.

Mirrors the pattern in test_entrypoint_lsp_settings.py — runs the
real workspace container against a synthetic /etc/agentic/workspace/
bind-mount and asserts the resulting /workspace/ + ~/.claude/agents
state.

See spec: docs/superpowers/specs/2026-05-12-workspace-injection-contract-design.md
"""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

IMAGE = "agentic-workspace-claude-cli:latest"


def _run(args: list[str], extra_mounts: list[str] | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run an arbitrary command in the workspace container with a tmpfs
    home dir (matches LSP test pattern). Optionally bind-mount extra
    paths and pass env vars. Returns the completed process."""
    cmd = [
        "docker", "run", "--rm",
        "--tmpfs=/home/agent:rw,exec,nosuid,size=128m,uid=1000,gid=1000",
    ]
    for m in extra_mounts or []:
        cmd.extend(["-v", m])
    for k, v in (env or {}).items():
        cmd.extend(["-e", f"{k}={v}"])
    cmd.append(IMAGE)
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


@pytest.mark.integration
def test_entrypoint_copies_workspace_context_md(tmp_path: Path):
    """Bind-mount a workspace dir with a CLAUDE.md; the entrypoint must
    copy it verbatim to /workspace/CLAUDE.md."""
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    (workspace_dir / "CLAUDE.md").write_text("# Test workspace\n\nHello from the test.\n")

    result = _run(
        ["cat", "/workspace/CLAUDE.md"],
        extra_mounts=[f"{workspace_dir}:/etc/agentic/workspace:ro"],
    )

    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "Test workspace" in result.stdout
    assert "Hello from the test" in result.stdout
```

- [ ] **Step 2: Run the test — should FAIL**

```bash
pytest tests/integration/test_entrypoint_workspace_injection.py::test_entrypoint_copies_workspace_context_md -v
```

Expected: FAIL with `assert "Test workspace" in result.stdout` — the entrypoint doesn't yet do the copy, so `/workspace/CLAUDE.md` won't exist and `cat` will fail.

- [ ] **Step 3: No commit yet — we'll commit after implementation makes the test pass.**

### Task B.2: Implement section 5.5 in the entrypoint

**Files:**
- Modify: `providers/workspaces/claude-cli/scripts/entrypoint.sh`

- [ ] **Step 1: Locate the insertion point**

Open `providers/workspaces/claude-cli/scripts/entrypoint.sh`. Find the comment header:

```bash
# -----------------------------------------------------------------------------
# 6. Execute CMD
# -----------------------------------------------------------------------------
```

Insert the new section **above** that line.

- [ ] **Step 2: Add section 5.5 verbatim from spec §5**

Paste the block (copying from `docs/superpowers/specs/2026-05-12-workspace-injection-contract-design.md` §5 — the bash code block beginning with `# 5.5 Workspace Context Composition`).

The exact code to paste:

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
    ctx_src="${INJECT_MOUNT}/${AGENTIC_WORKSPACE_CONTEXT:-${INJECT_DEFAULT_CONTEXT}}"
    if [ -f "${ctx_src}" ]; then
        cp "${ctx_src}" "${INJECT_TARGET_CONTEXT}"
        chmod 644 "${INJECT_TARGET_CONTEXT}"
    fi

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

- [ ] **Step 3: Rebuild the workspace image**

```bash
# Canonical build (uses scripts/build-provider.py under the hood — stages
# the build context the Dockerfile expects). Raw `docker build` against
# providers/workspaces/claude-cli/ does NOT work; see docs/issues/002.
just build-workspace-claude-cli
```

Expected: clean build, no shellcheck warnings on the new section.

- [ ] **Step 4: Run the first test — should now PASS**

```bash
pytest tests/integration/test_entrypoint_workspace_injection.py::test_entrypoint_copies_workspace_context_md -v
```

Expected: PASS.

- [ ] **Step 5: Verify the existing LSP-settings test still passes**

```bash
pytest tests/integration/test_entrypoint_lsp_settings.py -v
```

Expected: PASS. The new section is purely additive.

- [ ] **Step 6: Commit**

```bash
git add providers/workspaces/claude-cli/scripts/entrypoint.sh \
        tests/integration/test_entrypoint_workspace_injection.py
git commit -m "feat(workspace): entrypoint section 5.5 — workspace context composition

Implements spec §5 — file injection from a bind-mounted
/etc/agentic/workspace/ into the agent-visible workspace.

When the bind-mount is present, copies:
  - CLAUDE.md → /workspace/CLAUDE.md (verbatim)
  - plugins/<name>/ → /workspace/.agentic-plugins/<name>/, appending
    --plugin-dir to AGENTIC_PLUGIN_FLAGS (existing baked-in plugins
    stay intact)
  - agents/<name>.md → ~/.claude/agents/<name>.md (loose subagents;
    plugin-bundled subagents load automatically via --plugin-dir)

First integration test (test_entrypoint_copies_workspace_context_md)
covers the CLAUDE.md path. Remaining tests come in the next commit."
```

### Task B.3: Add remaining integration tests

**Files:**
- Modify: `tests/integration/test_entrypoint_workspace_injection.py`

For each new test below, follow the TDD cycle: write the test, run to confirm pass (the implementation already exists), then commit.

- [ ] **Step 1: Add plugin-copy test**

Append to the test file:

```python
@pytest.mark.integration
def test_entrypoint_copies_workspace_plugins(tmp_path: Path):
    """A plugin under /etc/agentic/workspace/plugins/<name>/ with a valid
    manifest should be copied to /workspace/.agentic-plugins/<name>/ and
    its --plugin-dir flag appended to AGENTIC_PLUGIN_FLAGS."""
    ws = tmp_path / "workspace"
    plugin = ws / "plugins" / "demo-plugin" / ".claude-plugin"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text('{"name":"demo-plugin","version":"0.1.0"}\n')

    result = _run(
        ["sh", "-c", "ls /workspace/.agentic-plugins/ && echo SEP && echo \"$AGENTIC_PLUGIN_FLAGS\""],
        extra_mounts=[f"{ws}:/etc/agentic/workspace:ro"],
    )

    assert result.returncode == 0, f"container failed: {result.stderr}"
    listing, _, flags = result.stdout.partition("SEP")
    assert "demo-plugin" in listing
    assert "--plugin-dir /workspace/.agentic-plugins/demo-plugin" in flags
```

Run it:

```bash
pytest tests/integration/test_entrypoint_workspace_injection.py::test_entrypoint_copies_workspace_plugins -v
```

Expected: PASS.

- [ ] **Step 2: Add loose-subagent test**

Append:

```python
@pytest.mark.integration
def test_entrypoint_copies_loose_subagents(tmp_path: Path):
    """A loose subagent at /etc/agentic/workspace/agents/<name>.md should
    be copied to ~/.claude/agents/<name>.md verbatim."""
    ws = tmp_path / "workspace"
    agents = ws / "agents"
    agents.mkdir(parents=True)
    (agents / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: Test reviewer\ntools: [Read]\n---\n\nYou are a test.\n"
    )

    result = _run(
        ["cat", "/home/agent/.claude/agents/reviewer.md"],
        extra_mounts=[f"{ws}:/etc/agentic/workspace:ro"],
    )

    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "name: reviewer" in result.stdout
    assert "You are a test" in result.stdout
```

Run:

```bash
pytest tests/integration/test_entrypoint_workspace_injection.py::test_entrypoint_copies_loose_subagents -v
```

Expected: PASS.

- [ ] **Step 3: Add plugin-filter test**

Append:

```python
@pytest.mark.integration
def test_entrypoint_filters_plugins_by_env(tmp_path: Path):
    """AGENTIC_WORKSPACE_PLUGINS=foo:bar should copy only foo+bar, not
    a third plugin baz that's also present."""
    ws = tmp_path / "workspace"
    for name in ["foo", "bar", "baz"]:
        d = ws / "plugins" / name / ".claude-plugin"
        d.mkdir(parents=True)
        (d / "plugin.json").write_text(f'{{"name":"{name}","version":"0.1.0"}}\n')

    result = _run(
        ["ls", "/workspace/.agentic-plugins/"],
        extra_mounts=[f"{ws}:/etc/agentic/workspace:ro"],
        env={"AGENTIC_WORKSPACE_PLUGINS": "foo:bar"},
    )

    assert result.returncode == 0, f"container failed: {result.stderr}"
    listing = set(result.stdout.split())
    assert "foo" in listing
    assert "bar" in listing
    assert "baz" not in listing, f"baz should be filtered out, listing={listing}"
```

Run:

```bash
pytest tests/integration/test_entrypoint_workspace_injection.py::test_entrypoint_filters_plugins_by_env -v
```

Expected: PASS.

- [ ] **Step 4: Add no-bind-mount-skipped test**

Append:

```python
@pytest.mark.integration
def test_entrypoint_skips_when_no_workspace_mount():
    """Without /etc/agentic/workspace/ bind-mounted, the new section is a
    no-op: /workspace/CLAUDE.md does not exist and AGENTIC_PLUGIN_FLAGS
    contains only the baked-in plugins (observability, sdlc, workspace)."""
    result = _run(
        ["sh", "-c", "test -f /workspace/CLAUDE.md && echo HAS_CTX || echo NO_CTX; echo \"FLAGS=$AGENTIC_PLUGIN_FLAGS\""],
    )

    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "NO_CTX" in result.stdout, f"unexpected /workspace/CLAUDE.md: {result.stdout}"
    # Baked-in plugins should still be present in the flags.
    assert "--plugin-dir /opt/agentic/plugins/observability" in result.stdout
```

Run:

```bash
pytest tests/integration/test_entrypoint_workspace_injection.py::test_entrypoint_skips_when_no_workspace_mount -v
```

Expected: PASS.

- [ ] **Step 5: Add invalid-plugin-skipped test**

Append:

```python
@pytest.mark.integration
def test_entrypoint_skips_invalid_plugin_dir(tmp_path: Path):
    """A 'plugin' directory lacking .claude-plugin/plugin.json must NOT
    be copied and must NOT be added to AGENTIC_PLUGIN_FLAGS."""
    ws = tmp_path / "workspace"
    (ws / "plugins" / "garbage").mkdir(parents=True)
    # No .claude-plugin/plugin.json inside garbage/

    result = _run(
        ["sh", "-c", "ls /workspace/.agentic-plugins/ 2>&1 || true; echo \"FLAGS=$AGENTIC_PLUGIN_FLAGS\""],
        extra_mounts=[f"{ws}:/etc/agentic/workspace:ro"],
    )

    assert result.returncode == 0
    assert "garbage" not in result.stdout
```

Run:

```bash
pytest tests/integration/test_entrypoint_workspace_injection.py::test_entrypoint_skips_invalid_plugin_dir -v
```

Expected: PASS.

- [ ] **Step 6: Add contract-test that baked-in flags survive**

Append:

```python
@pytest.mark.integration
def test_entrypoint_appends_to_agentic_plugin_flags_does_not_replace(tmp_path: Path):
    """When a per-workspace plugin is injected, AGENTIC_PLUGIN_FLAGS must
    contain BOTH the baked-in plugins AND the new one — appending, not
    replacing."""
    ws = tmp_path / "workspace"
    d = ws / "plugins" / "extra" / ".claude-plugin"
    d.mkdir(parents=True)
    (d / "plugin.json").write_text('{"name":"extra","version":"0.1.0"}\n')

    result = _run(
        ["sh", "-c", "echo \"$AGENTIC_PLUGIN_FLAGS\""],
        extra_mounts=[f"{ws}:/etc/agentic/workspace:ro"],
    )

    assert result.returncode == 0
    flags = result.stdout
    # Baked-in plugins present
    assert "/opt/agentic/plugins/observability" in flags
    assert "/opt/agentic/plugins/sdlc" in flags
    assert "/opt/agentic/plugins/workspace" in flags
    # New per-workspace plugin appended
    assert "/workspace/.agentic-plugins/extra" in flags
```

Run:

```bash
pytest tests/integration/test_entrypoint_workspace_injection.py::test_entrypoint_appends_to_agentic_plugin_flags_does_not_replace -v
```

Expected: PASS.

- [ ] **Step 7: Run the full new test file**

```bash
pytest tests/integration/test_entrypoint_workspace_injection.py -v
```

Expected: 6 passing.

- [ ] **Step 8: Commit**

```bash
git add tests/integration/test_entrypoint_workspace_injection.py
git commit -m "test(workspace): integration coverage for section 5.5

Six tests against the built workspace image:
  - test_entrypoint_copies_workspace_context_md
  - test_entrypoint_copies_workspace_plugins
  - test_entrypoint_copies_loose_subagents
  - test_entrypoint_filters_plugins_by_env
  - test_entrypoint_skips_when_no_workspace_mount
  - test_entrypoint_skips_invalid_plugin_dir
  - test_entrypoint_appends_to_agentic_plugin_flags_does_not_replace

Mirrors the existing tests/integration/test_entrypoint_lsp_settings.py
pattern (docker run --rm with tmpfs home + optional bind-mounts + env)."
```

**Phase B exit criteria:** 6 new integration tests pass; existing LSP test passes; entrypoint script change is purely additive.

---

# Phase C — `WorkspaceFiles` Python helper

Goal: ship the `WorkspaceFiles` class per spec §6 so Python orchestrators can use a shared library for bind-mount + inject staging.

### Task C.1: Write the failing unit tests

**Files:**
- Create: `lib/python/agentic_isolation/tests/test_workspace_files.py`

- [ ] **Step 1: Create the test file**

```python
"""Unit tests for agentic_isolation.workspace_files.WorkspaceFiles.

Run with: cd lib/python/agentic_isolation && uv run pytest tests/test_workspace_files.py -v
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_bind_mount_descriptor_shape(tmp_path: Path):
    """bind_mount() returns a docker.types.Mount with the expected
    source/target/type/read_only fields."""
    from agentic_isolation.workspace_files import WorkspaceFiles

    client = MagicMock()
    wf = WorkspaceFiles(client=client)
    mount = wf.bind_mount(tmp_path, "/etc/agentic/workspace", read_only=True)

    # docker.types.Mount stores its config in a dict-like .source/.target
    # accessible attributes; verify either attribute or the internal _data dict.
    # The library represents the mount internally as a serializable dict —
    # we check the dict representation.
    raw = dict(mount)
    assert raw["Target"] == "/etc/agentic/workspace"
    assert raw["Source"] == str(tmp_path.resolve())
    assert raw["Type"] == "bind"
    assert raw["ReadOnly"] is True


def test_bind_mount_resolves_relative_paths(tmp_path: Path, monkeypatch):
    """Relative host_path is resolved to an absolute path in the mount
    descriptor (Docker rejects relative bind sources)."""
    from agentic_isolation.workspace_files import WorkspaceFiles

    # Create a real subdir then chdir into the temp dir so a relative
    # path can be resolved.
    sub = tmp_path / "sub"
    sub.mkdir()
    monkeypatch.chdir(tmp_path)

    wf = WorkspaceFiles(client=MagicMock())
    mount = wf.bind_mount(Path("sub"), "/etc/agentic/workspace", read_only=True)

    raw = dict(mount)
    assert Path(raw["Source"]).is_absolute()
    assert raw["Source"] == str(sub.resolve())


def test_inject_archives_and_calls_put_archive():
    """inject() should tar the supplied bytes under the target basename
    and call docker.client.containers.get(id).put_archive(parent_dir, tar)."""
    from agentic_isolation.workspace_files import WorkspaceFiles

    container = MagicMock()
    client = MagicMock()
    client.containers.get.return_value = container

    wf = WorkspaceFiles(client=client)
    wf.inject("ctr-123", "/workspace/CLAUDE.md", b"hello world\n")

    # Verify lookup + put_archive call shape
    client.containers.get.assert_called_once_with("ctr-123")
    assert container.put_archive.called
    args, kwargs = container.put_archive.call_args
    # First positional: parent dir in container
    assert args[0] == "/workspace"
    # Second positional or 'data' kwarg: bytes — must be a tar archive
    archive_bytes = args[1] if len(args) > 1 else kwargs["data"]
    assert archive_bytes[:4] != b""  # non-empty
    # Quick sanity: tar archives start with the filename bytes in the
    # header at offset 0 — the basename should appear in the first 100 bytes.
    assert b"CLAUDE.md" in archive_bytes[:200]
```

- [ ] **Step 2: Run — must FAIL (module doesn't exist yet)**

```bash
cd lib/python/agentic_isolation
uv run pytest tests/test_workspace_files.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agentic_isolation.workspace_files'`.

### Task C.2: Implement `WorkspaceFiles`

**Files:**
- Create: `lib/python/agentic_isolation/agentic_isolation/workspace_files.py`

- [ ] **Step 1: Write the module**

```python
"""WorkspaceFiles — primitive for staging files into a workspace container.

Two complementary modes:

  bind_mount(host, ctr, read_only) -> docker.types.Mount
    Host-resident static content. Returns a Mount descriptor the caller
    passes to client.containers.create(mounts=[...]). Cheap, no copy.

  inject(container_id, ctr_path, content: bytes) -> None
    Generated / object-storage / remote-daemon content. Streams a
    single-file tar archive into a (created, not yet started) container.

See: docs/superpowers/specs/2026-05-12-workspace-injection-contract-design.md §6
"""

from __future__ import annotations

import io
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import docker
    import docker.types


@dataclass
class WorkspaceFiles:
    """Stage files into a workspace container before it starts.

    `client` is a docker.DockerClient. The helper does not own the
    client — callers pass in whatever client they're already using.
    """

    client: "docker.DockerClient"

    def bind_mount(
        self,
        host_path: Path,
        container_path: str,
        read_only: bool = True,
    ) -> "docker.types.Mount":
        """Build a Mount descriptor for `containers.create(mounts=[...])`.

        Relative host_paths are resolved to absolute paths (Docker rejects
        relative bind sources). The descriptor is a plain ``docker.types.Mount``
        the caller hands to the docker SDK unmodified.
        """
        from docker.types import Mount

        return Mount(
            target=container_path,
            source=str(Path(host_path).resolve()),
            type="bind",
            read_only=read_only,
        )

    def inject(
        self,
        container_id: str,
        container_path: str,
        content: bytes,
    ) -> None:
        """Stream ``content`` into the container as a single-file tar archive
        at ``container_path``.

        Must be called after ``containers.create()`` and before
        ``container.start()`` — the put_archive API requires the container
        to exist but works regardless of running state.
        """
        target = Path(container_path)
        parent = str(target.parent)
        basename = target.name

        # Build an in-memory tar containing one file.
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name=basename)
            info.size = len(content)
            info.mtime = int(time.time())
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(content))
        archive = buf.getvalue()

        container = self.client.containers.get(container_id)
        container.put_archive(parent, archive)
```

- [ ] **Step 2: Run tests — should now PASS**

```bash
cd lib/python/agentic_isolation
uv run pytest tests/test_workspace_files.py -v
```

Expected: 3 passing.

- [ ] **Step 3: Confirm the existing test suite still passes**

```bash
uv run pytest -v
```

Expected: existing tests + 3 new = all green.

- [ ] **Step 4: Commit**

```bash
cd /Users/neural/Code/AgentParadise/agentic-primitives
git add lib/python/agentic_isolation/agentic_isolation/workspace_files.py \
        lib/python/agentic_isolation/tests/test_workspace_files.py
git commit -m "feat(isolation): WorkspaceFiles helper — bind_mount + inject primitives

New module agentic_isolation.workspace_files implementing spec §6.

  bind_mount(host, ctr, read_only) -> docker.types.Mount
    Host-resident static content. Resolves relative paths to absolute.

  inject(container_id, ctr_path, content: bytes) -> None
    Generated / remote-fetched content. Streams a single-file tar
    archive via docker.put_archive(). Works after create_container,
    before start_container — and against remote daemons / K8s.

Three unit tests cover the Mount descriptor shape, relative-path
resolution, and the put_archive call shape with a mocked client."
```

### Task C.3: Export from the package

**Files:**
- Modify: `lib/python/agentic_isolation/agentic_isolation/__init__.py`

- [ ] **Step 1: Add export**

Open `lib/python/agentic_isolation/agentic_isolation/__init__.py`. After the existing imports (look for the existing `from .workspace import ...` or similar), append:

```python
from .workspace_files import WorkspaceFiles  # noqa: F401
```

If the file already has an `__all__` list, add `"WorkspaceFiles"` to it.

- [ ] **Step 2: Add an export test**

Open `lib/python/agentic_isolation/tests/test_package_exports.py`. Find the existing assertion list and add `WorkspaceFiles`:

```python
def test_workspace_files_exported():
    import agentic_isolation
    assert hasattr(agentic_isolation, "WorkspaceFiles")
```

- [ ] **Step 3: Run**

```bash
cd lib/python/agentic_isolation
uv run pytest tests/test_package_exports.py::test_workspace_files_exported -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
cd /Users/neural/Code/AgentParadise/agentic-primitives
git add lib/python/agentic_isolation/agentic_isolation/__init__.py \
        lib/python/agentic_isolation/tests/test_package_exports.py
git commit -m "feat(isolation): export WorkspaceFiles from package root"
```

**Phase C exit criteria:** `from agentic_isolation import WorkspaceFiles` works; 3 unit tests + 1 export test green.

---

# Phase D — Documentation deliverables

Goal: make the contract discoverable. Three new docs + a README update.

### Task D.1: Write `docs/workspace.md`

**Files:**
- Create: `docs/workspace.md`

- [ ] **Step 1: Write the file**

```markdown
# The Workspace

The workspace is the isolation + observability boundary between an
orchestrator and the AI agent it runs. Every Claude task spawned by
agentic-domain-runner, every Syntropic137 workflow phase, every
future Codex/Gemini job runs inside one of these.

This page is the canonical reference for what the workspace does
and what it exposes. For the design rationale, see
[`docs/adrs/035-workspace-injection-contract.md`](adrs/035-workspace-injection-contract.md)
and the design spec at
[`docs/superpowers/specs/2026-05-12-workspace-injection-contract-design.md`](superpowers/specs/2026-05-12-workspace-injection-contract-design.md).

## What the workspace is

A container image — `agentic-workspace-claude-cli:<tag>` today, more
provider variants later — with an entrypoint that prepares the
agent's environment before exec'ing the orchestrator's CMD.

The entrypoint owns three responsibilities:

1. **Inject** orchestrator-supplied context.
2. **Isolate** the agent's effects (tmpfs, read-only mounts, network
   whitelisting).
3. **Observe** what the agent did (git hooks → JSONL on stderr,
   stream-json on stdout, output artifacts on disk).

This page focuses on **(1) inject** since that's the part with a
documented contract. Isolate and observe are status quo.

## Inject — what the orchestrator puts in

### Bind-mount layout

```
/etc/agentic/workspace/        (orchestrator bind-mounts here, read-only)
  CLAUDE.md                      optional, project-level agent context
  plugins/<name>/                optional, zero or more Claude plugins
    .claude-plugin/plugin.json
    skills/, commands/, hooks/, agents/
  agents/<name>.md               optional, loose subagents
```

The orchestrator constructs whatever subset it needs. Missing files /
missing directories are silently skipped — backwards-compatible.

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
| `/workspace/.agentic-plugins/<name>/` | Copy of each enabled plugin tree. |
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

(Status quo, no changes from this work.)

- **Git hooks** — workspace ships `prepare-commit-msg`; observability
  plugin ships `post-commit`, `pre-push`, `post-merge`,
  `post-rewrite`, `post-checkout`. Both sets are symlinked into
  `~/.git-hooks` and activated via `git config --global core.hooksPath`.
- **JSONL on stderr** — the observability plugin emits structured
  events: every tool use, prompt, completion. Orchestrators merge
  stderr into stdout and parse.
- **Stream-json on stdout** — when the orchestrator invokes
  `claude -p --output-format stream-json --verbose`, every turn
  (tool_use, tool_result, token usage, total cost) lands on stdout
  as JSONL.
- **Output artifacts** — agent writes to `/workspace/artifacts/output/`,
  orchestrator collects from the bind-mounted host path after exit.

## Python helper

For orchestrators that prefer a library import over hand-constructing
the mount + env:

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

The bind-mount path is cheap and works when the orchestrator and
Docker daemon share a filesystem. The inject path works against any
daemon (remote, K8s) and is the right choice when content is
generated per-task.

## Pointers

- Design spec: [`docs/superpowers/specs/2026-05-12-workspace-injection-contract-design.md`](superpowers/specs/2026-05-12-workspace-injection-contract-design.md)
- ADR: [`docs/adrs/035-workspace-injection-contract.md`](adrs/035-workspace-injection-contract.md)
- Entrypoint script: [`providers/workspaces/claude-cli/scripts/entrypoint.sh`](../providers/workspaces/claude-cli/scripts/entrypoint.sh)
- Python helper: [`lib/python/agentic_isolation/agentic_isolation/workspace_files.py`](../lib/python/agentic_isolation/agentic_isolation/workspace_files.py)
```

- [ ] **Step 2: Commit**

```bash
git add docs/workspace.md
git commit -m "docs: canonical docs/workspace.md reference

Single-page orientation for what the workspace is and what it does.
Covers inject (contract this PR adds), isolate (status quo), and
observe (status quo). Links design spec, ADR-035, entrypoint, and
Python helper for deeper reads."
```

### Task D.2: Update top-level README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Find an appropriate insertion point**

Open `README.md`. After the existing intro/install section and before any deep-dive sections, insert:

```markdown
## Workspace

`agentic-primitives` ships the workspace image — the controlled boundary every AI agent runs inside. The workspace has three responsibilities:

1. **Inject** orchestrator-supplied context (`CLAUDE.md`, plugins, subagents) via a bind-mount + three optional env vars.
2. **Isolate** the agent's effects (tmpfs home, read-only context mount, network whitelisting).
3. **Observe** what the agent did (git hooks → JSONL, stream-json on stdout, output artifacts).

See [`docs/workspace.md`](docs/workspace.md) for the canonical reference, [`docs/adrs/035-workspace-injection-contract.md`](docs/adrs/035-workspace-injection-contract.md) for the design decisions, and [`providers/workspaces/claude-cli/scripts/entrypoint.sh`](providers/workspaces/claude-cli/scripts/entrypoint.sh) for the source of truth.
```

- [ ] **Step 2: Trim any now-duplicated workspace content**

Search for any pre-existing workspace prose in the README that overlaps with `docs/workspace.md`:

```bash
grep -n -A 3 -i 'workspace' README.md | head -40
```

If anything in the README repeats what's now in `docs/workspace.md`, remove it from the README. The README's job is signposting.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): focused Workspace section linking docs/workspace.md

The README points; the canonical reference lives at docs/workspace.md."
```

### Task D.3: Write ADR-035

**Files:**
- Create: `docs/adrs/035-workspace-injection-contract.md`

- [ ] **Step 1: Read the template**

```bash
cat docs/adrs/000-adr-template.md
```

Match its section structure.

- [ ] **Step 2: Write the ADR**

```markdown
# ADR-035 — Workspace injection contract

**Date:** 2026-05-12
**Status:** Accepted

## Context

Multiple orchestrators (agentic-domain-runner, Syntropic137, future Codex/Gemini wrappers) each need to hand a workspace its context, plugins, and subagents before the agent starts. Before this ADR, each orchestrator reinvented the staging mechanism: agentic-domain-runner with a bind-mount + a Rust FileStager port; Syntropic137 with `docker cp`-based `inject_files()`. Both worked but neither was shared.

agentic-primitives is the right home for the cross-orchestrator contract because it owns the workspace image — the only layer that can see what's inside `/opt/agentic/plugins/` and the only layer whose entrypoint runs inside every workspace, regardless of which orchestrator launched it.

## Decision

The agentic-primitives workspace image exposes a small **inbound injection contract** that all orchestrators target:

- A read-only bind-mount at `/etc/agentic/workspace/` carries orchestrator-supplied content: `CLAUDE.md`, `plugins/<name>/`, `agents/<name>.md`.
- Three optional env vars (`AGENTIC_WORKSPACE_CONTEXT`, `AGENTIC_WORKSPACE_PLUGINS`, `AGENTIC_WORKSPACE_AGENTS`) control filtering and the context filename.
- The entrypoint copies into `/workspace/CLAUDE.md`, `/workspace/.agentic-plugins/<name>/`, and `~/.claude/agents/<name>.md`, and appends to `AGENTIC_PLUGIN_FLAGS`.
- Tool restrictions live inside subagent frontmatter (`tools: [...]`) or plugin permissions — not as a separate env-var concept.
- Identity vars (task id, session id, runner URL, tokens) are NOT part of the contract — those are orchestrator-specific.
- A `WorkspaceFiles` Python helper exposes `bind_mount()` + `inject()` primitives for callers who prefer a library import to hand-constructing the mount + env.

## Consequences

- One contract, multiple consumers. agentic-domain-runner already implements its side in Rust (`FileStager` port + `BindMountFileStager`). Syntropic137 can adopt the Python helper to standardize its own staging.
- New orchestrators don't reinvent the seam — they target the contract.
- Tool-restriction policy travels with the subagent or plugin that enforces it, not in a separate env-var concept. Less drift, more cohesion.
- The contract is small enough to fit on one page (`docs/workspace.md`) — discoverable, learnable.

## Alternatives Considered

- **Bake everything into the workspace image at build time.** Rejected — would require a separate image per workspace profile and image rebuilds per content change.
- **Have each orchestrator implement its own injection.** Rejected — leads to drift and inconsistent agent experiences.
- **Add `AGENTIC_WORKSPACE_ALLOWED_TOOLS` env var.** Rejected per spec §4 — tool restrictions belong inside subagent or plugin definitions where the policy travels with the agent that enforces it.
- **Add identity vars (`AGENTIC_TASK_ID`, etc.) to the contract.** Rejected — those are orchestrator-specific. Adding them would bind the workspace image to a single orchestrator's data model.

## References

- Design spec: [`docs/superpowers/specs/2026-05-12-workspace-injection-contract-design.md`](../superpowers/specs/2026-05-12-workspace-injection-contract-design.md)
- Plan: [`docs/superpowers/plans/2026-05-12-workspace-injection-contract.md`](../superpowers/plans/2026-05-12-workspace-injection-contract.md)
- Sibling spec (consumer side, already merged): [agentic-domain-runner per-domain context injection](https://gitea.neuralempowerment.xyz/HomeLab/agentic-domain-runner/src/branch/main/docs/superpowers/specs/2026-05-12-per-domain-context-injection-design.md)
- Claude subagents reference: https://code.claude.com/docs/en/sub-agents.md
- ADR-033 — plugin-native workspace images (precedent)
- ADR-027 — provider workspace images (precedent)
```

- [ ] **Step 3: Commit**

```bash
git add docs/adrs/035-workspace-injection-contract.md
git commit -m "docs: ADR-035 — workspace injection contract"
```

**Phase D exit criteria:** `docs/workspace.md`, `README.md`, and `docs/adrs/035-workspace-injection-contract.md` all in place and consistent.

---

# Phase E — Release + runner pickup

Goal: bump the workspace image, point the runner at it, run the previously-blocked live smoke.

### Task E.1: Push branch, open PR, merge

- [ ] **Step 1: Run all tests one more time**

```bash
cd /Users/neural/Code/AgentParadise/agentic-primitives
pytest tests/integration/test_entrypoint_workspace_injection.py -v
cd lib/python/agentic_isolation && uv run pytest -v && cd ../..
```

Expected: all green.

- [ ] **Step 2: Push**

```bash
git push -u origin feat/workspace-injection-contract
```

- [ ] **Step 3: Open PR**

Title: `feat: workspace injection contract — entrypoint + Python helper + docs`

Body: link to spec, plan, ADR-035; summarize the three commits; note Phase A (env rename in runner) is a coordinated prerequisite that must merge first.

- [ ] **Step 4: After approval, merge with `--no-ff` and push to main**

```bash
git checkout main
git pull --ff-only
git merge --no-ff feat/workspace-injection-contract -m "Merge feat/workspace-injection-contract"
git push origin main
git branch -d feat/workspace-injection-contract
```

### Task E.2: Build and tag the new workspace image

- [ ] **Step 1: Decide on a version tag**

Read the current image's version label:

```bash
docker inspect agentic-workspace-claude-cli:latest --format '{{.Config.Labels}}' | tr ',' '\n'
```

Pick the next tag (e.g., if `latest` aliases `0.7.x`, tag `0.8.0`). Conventions live in the workspace image's `Dockerfile` — match.

- [ ] **Step 2: Build and tag**

```bash
cd /Users/neural/Code/AgentParadise/agentic-primitives
just build-workspace-claude-cli   # tags `latest` + the bundled Claude CLI version
# (or: uv run scripts/build-provider.py claude-cli)
```

`docker build -t ... providers/workspaces/claude-cli` does NOT work
— the Dockerfile expects a staged build context that the script
above produces. See docs/issues/002.

- [ ] **Step 3: (Optional) Push to the registry**

If the project uses GHCR or a private registry, push both tags. Otherwise leave at local only.

### Task E.3: Bump the runner's image reference and re-run the live smoke

**Files:**
- Modify: `/Users/neural/Code/HomeLab/agentic-domain-runner/examples/domains/homelab/domain.toml`

- [ ] **Step 1: Create a small bump branch in the runner**

```bash
cd /Users/neural/Code/HomeLab/agentic-domain-runner
git checkout main && git pull --ff-only
git checkout -b chore/bump-workspace-image-0.8.0
```

- [ ] **Step 2: Update the image tag**

Open `examples/domains/homelab/domain.toml`. Find the `image = "...":` line. Change to:

```toml
image = "agentic-workspace-claude-cli:0.8.0"
```

- [ ] **Step 3: Run the previously-blocked live smoke**

The test `live_claude_sees_domain_claude_md` (referenced in spec §9 Phase D) was blocked because Claude refused to read `/etc/agentic/workspace/CLAUDE.md` due to path-safety heuristics. Now that the entrypoint copies the content into `/workspace/CLAUDE.md`, Claude treats it as in-scope.

Find the test name in `tests/smoke.rs` (it was added during the earlier merged feature) or write a new one if it's not already there. Run:

```bash
ANTHROPIC_API_KEY="$(grep '^ANTHROPIC_API_KEY' .env | cut -d= -f2-)" \
    cargo test --test smoke -- --ignored live_claude_sees
```

Expected: the test passes — Claude reports the first H1 of the homelab CLAUDE.md.

- [ ] **Step 4: Commit and push**

```bash
git add examples/domains/homelab/domain.toml
git commit -m "chore: bump workspace image to 0.8.0 (workspace injection contract)

Pulls in agentic-primitives' new entrypoint section 5.5 so
/workspace/CLAUDE.md is composed from /etc/agentic/workspace/CLAUDE.md.
Unblocks the previously-skipped live Claude smoke."
git push -u origin chore/bump-workspace-image-0.8.0
```

- [ ] **Step 5: Open PR, merge after approval**

Same `--no-ff` workflow as Phase A.

**Phase E exit criteria:** workspace image 0.8.0 tagged, runner main references it, `live_claude_sees_domain_claude_md` passes against the real image.

---

## Self-review notes

Spec coverage:
- §2 workspace responsibility → Phase D (workspace.md describes inject/isolate/observe)
- §3 bind-mount layout → Task B.2 + Task D.1
- §4 env vars → Task B.2 + Task D.1
- §5 entrypoint actions → Task B.2 (script) + B.3 (tests)
- §6 Python helper → Phase C
- §7 conventions → Captured in ADR-035 (Task D.3) and docs/workspace.md (Task D.1)
- §8 testing → Tasks B.3 (integration) + C.1 (unit)
- §9 phasing → Phases A–E map 1:1
- §10 out-of-scope → Captured in ADR-035 alternatives and docs/workspace.md

Type / name consistency:
- `WorkspaceFiles` (class), `bind_mount` (method), `inject` (method) — used consistently across spec §6, plan Task C.1/C.2, docs/workspace.md.
- `INJECT_MOUNT` / `INJECT_TARGET_*` / `INJECT_DEFAULT_*` — entrypoint constants used consistently in spec §5 and Task B.2 script.
- `AGENTIC_WORKSPACE_CONTEXT` / `_PLUGINS` / `_AGENTS` — env var names used consistently across spec §4, Task B.2 script, Task B.3 tests, Task D.1 workspace.md.

Known intentional simplifications:
- Phase E.3 assumes the runner's `live_claude_sees_domain_claude_md` test exists. If it doesn't yet, write it as part of the bump PR — a thin test that POSTs a homelab task asking Claude to echo the first heading of `/workspace/CLAUDE.md` and asserts the response.
- `__inject_names` helper is intentionally not exported. If a future test wants to assert the helper's behavior in isolation, expose it via a separate `_test_helpers.sh` source file. YAGNI for now.

End of plan.
