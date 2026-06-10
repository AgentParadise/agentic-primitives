# Interactive-tmux Workspace Provider

A workspace image bundling **claude**, **codex**, and **gemini** interactive
CLIs plus `tmux`, designed to be driven from the host via
`docker exec <container> tmux send-keys` / `tmux capture-pane`. Sibling to
the existing `claude-cli` provider; neither replaces the other.

## Why it exists

`providers/workspaces/claude-cli` drives Claude in non-interactive (`-p`)
mode, which is leaving the Max plan in ~5 days. The interactive transport
(tmux pane + host-side `docker exec`) was validated in EXP-01..04 of this
repo's experiment series and survives on the subscription plan. This
provider packages that transport as a real provider next to `claude-cli`.

## Build

Same convention as every other provider in this repo:

```bash
uv run scripts/build-provider.py interactive-tmux
# or
just build-provider interactive-tmux
```

Produces `agentic-workspace-interactive-tmux:latest` (and a version tag
matching the pinned `CLAUDE_CLI_VERSION` in the Dockerfile).

## Host-side driver

`driver/interactive_tmux.py` is a single-file Python 3.11+ driver (stdlib
only) exposing five primitives that hide the per-agent quirks:

```python
from interactive_tmux import InteractiveTmuxWorkspace
from pathlib import Path

ws = InteractiveTmuxWorkspace.start_workspace(
    name="my-workspace",
    host_auth={
        "claude": Path("~/.claude").expanduser(),
        "codex":  Path("~/.codex").expanduser(),
        "gemini": Path("~/.gemini").expanduser(),
    },
)

ws.send_message("claude", "Refactor lib/foo.py to use dataclasses.")
ws.await_completion("claude", timeout=120)
text = ws.capture_response("claude")
ws.stop()
```

### Making the import resolve

The driver is a single file, not a package on PyPI and not exposed via
`pyproject.toml` yet. `from interactive_tmux import …` only resolves if
`providers/workspaces/interactive-tmux/driver/` is on `sys.path`. Pick one:

```bash
# Option A — set PYTHONPATH for the run (recommended for ad-hoc scripts):
PYTHONPATH=providers/workspaces/interactive-tmux/driver python3 my_script.py
```

```python
# Option B — prepend at the top of your script (works from any cwd):
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(
    "providers/workspaces/interactive-tmux/driver"
).resolve()))
from interactive_tmux import InteractiveTmuxWorkspace
```

Consumers outside this repo (e.g. Syntropic137) should vendor
`driver/interactive_tmux.py` or import it by absolute path until a wheel
ships.

### CLI shim

A CLI shim is bundled for shell-script consumers. **The shim paths below
are relative to `providers/workspaces/interactive-tmux/` — `cd` there
first**, or substitute the absolute path to `driver/interactive_tmux.py`:

```bash
cd providers/workspaces/interactive-tmux/
python3 driver/interactive_tmux.py start  --name w1
python3 driver/interactive_tmux.py send   --name w1 --agent gemini --text "..."
python3 driver/interactive_tmux.py await  --name w1 --agent gemini --timeout 60
python3 driver/interactive_tmux.py capture --name w1 --agent gemini
python3 driver/interactive_tmux.py stop   --name w1
```

## Rust driver (alternative implementation)

A parity-faithful Rust port of the driver lives at
[`driver-rs/`](driver-rs/) and ships as a single static binary `itmux`.
The protocol, per-agent matrix, structured-result shape, and on-disk
workspace registry (`/tmp/interactive-tmux-workspaces/<name>.json`) are
byte-compatible with the Python driver, so a Rust `start` round-trips
with a Python `stop` and vice versa.

Why pick it: no Python interpreter on the consumer's PATH, no
`PYTHONPATH` shim, and ~25× faster cold start per invocation when an
orchestrator drives many `send`/`await`/`capture` cycles back-to-back.
Not a behavioural fork — same EXP-01..04 friction encodings, same
readiness predicates, same `AwaitResult` JSON shape.

```bash
# Build (release):
cd providers/workspaces/interactive-tmux/driver-rs/
cargo build --release
# Binary path (honours CARGO_TARGET_DIR if set):
ls target/release/itmux

# Same subcommand surface as the Python CLI shim:
target/release/itmux start    --name w1
target/release/itmux send     --name w1 --agent gemini --text "..."
target/release/itmux await    --name w1 --agent gemini --timeout 60
target/release/itmux capture  --name w1 --agent gemini
target/release/itmux exec     --name w1 -- bash -lc 'ls /workspace'
target/release/itmux stop     --name w1
```

`itmux exec` is the only addition over the Python surface — it shells
out to `docker exec` for ad-hoc commands in the workspace container
(useful for liveness checks without going through tmux).

Parity smoke: `bash scripts/smoke-rs.sh` (mirrors `scripts/smoke.sh`,
auto-builds the release binary on first run). Per-agent transcripts
land at `runs/smoke-rs-<agent>.txt` so you can diff against the
Python smoke's outputs.

Implementation notes and the full per-agent matrix encoding live at
[`driver-rs/README.md`](driver-rs/README.md).

## Per-agent matrix (encoded in the driver — callers should not need this)

| Concern    | Claude                                                                 | Codex                                                                                  | Gemini                                                       |
|------------|-------------------------------------------------------------------------|----------------------------------------------------------------------------------------|--------------------------------------------------------------|
| Launch     | `claude` + Enter                                                        | `codex --no-alt-screen` + Enter, then `1` Enter (trust), then `Escape` (hooks review)  | `gemini` + Enter                                             |
| Submit     | `send-keys -l <text>` then `send-keys Enter`                           | `send-keys -l <text>` then `send-keys C-j C-m` (first-send gotcha — see EXP-02)        | `send-keys -l <text>` then `send-keys Enter` (never `C-m`)   |
| Readiness  | No `esc to interrupt` + `? for shortcuts` footer visible (3-signal)     | No `• Working` marker + idle indicator (`▌`) visible                                   | `Type your message` prompt indicator visible                 |
| Auth mount | **Both** `~/.claude/` and `~/.claude.json` — see below                  | `~/.codex/`                                                                            | `~/.gemini/` (settings.json auto-patched to disable folderTrust) |

## Claude auth: the `.credentials.json` vs `.claude.json` answer

EXP-01 and EXP-04 disagreed on where Claude's OAuth tokens live. The
disagreement was resolved empirically in EXP-05a (sibling probe on
`agentprims-exp02`, full 2×2 mount matrix; report:
`experiments/EXP-05a-claude-auth-matrix.md` on `agentprims-lab`). The
finding is unambiguous: **Claude needs BOTH `~/.claude/` AND
`~/.claude.json` mounted to start an authenticated interactive
session.** Either alone is insufficient.

EXP-05a's mount matrix (N=2 runs per cell):

| Mounts provided           | Auth outcome                                                |
|---------------------------|-------------------------------------------------------------|
| none                      | Needs login (OAuth required)                                |
| only `~/.claude/`         | `Claude configuration file not found at /home/agent/.claude.json` → Needs login |
| only `~/.claude.json`     | Session UI starts but `Not logged in · Please run /login` on submit |
| both                      | **Authenticated start, no login step, prompts execute**     |

Per-file roles:

- `~/.claude/.credentials.json` holds the actual OAuth tokens
  (`claudeAiOauth.{accessToken, refreshToken, expiresAt, scopes,
  subscriptionType, rateLimitTier}`). **Without it, Claude falls back to
  API Usage Billing (Sonnet) instead of Max plan (Opus 4.7).**
- `~/.claude.json` (a file at `$HOME`, peer of the `~/.claude/`
  directory, NOT inside it) is config/metadata: `oauthAccount`
  (uuid/email/org), onboarding markers (`hasCompletedOnboarding`,
  `theme`, `projects.<path>.hasTrustDialogAccepted`), `installMethod`.
  EXP-05a confirms `~/.claude.json` carries **no token material**, but
  Claude refuses to start an authenticated session without it.

The driver handles both: it copies `~/.claude/.credentials.json` into a
throwaway dir AND synthesises a `~/.claude.json` that carries the host's
`oauthAccount` through plus pre-seeds the workspace path in the trust
map. The `host_auth["claude"]` parameter takes the host directory
(`~/.claude`); the driver finds `~/.claude.json` next to it
automatically. Consumers reimplementing this mount layout (e.g. without
the driver) must mount both, side by side, at `$HOME` inside the
container.

### Synthetic `~/.claude.json` fallback (this provider's stance)

EXP-05a's matrix above measures the OS-level question ("what must be
mounted?"). This provider answers a layered question on top: even when
the host has no `~/.claude.json` of its own, the driver **always
synthesizes one inside the container**. The synthesized file carries
onboarding-skip markers, the workspace's project-trust map, and (when
available) the host's `oauthAccount` metadata. It carries **no token
material** — tokens are read only from the host's
`~/.claude/.credentials.json`, which MUST exist.

Practical consequence for consumers:

| Host state                                | Driver behavior                                                                                  |
|-------------------------------------------|--------------------------------------------------------------------------------------------------|
| `~/.claude/` exists, `~/.claude.json` too | both copied; matches EXP-05a "both" cell (authenticated, no wizards)                            |
| `~/.claude/` exists, `~/.claude.json` not | `~/.claude/.credentials.json` copied; `~/.claude.json` **synthesized** inside the container — functionally equivalent to EXP-05a "both" |
| `~/.claude/.credentials.json` missing     | `prepare_host_auth` raises `FileNotFoundError`                                                  |

So callers do NOT need to author `~/.claude.json` themselves; the
synthetic fallback is the supported path. Consumers that want strict
byte-for-byte parity with the host's `~/.claude.json` should ensure both
files exist on the host before calling — the driver still mounts the
host file when it's present (it never overrides it).

## Running from inside another container (docker-out-of-docker)

When the driver itself runs inside a container (e.g. an integrator like
Syntropic137 spawning a workspace from their own container), `$HOME`
does NOT point at the operator's credentials — it's the calling
container's home (`/root` or `/home/<container-user>`). Without the env
vars below, every agent slot defaults to `None` and `start_workspace`
fails with `no enabled agents (host_auth empty)`.

Mount the operator's credentials into the calling container at any
path, then point the driver at them via env vars:

| Env var              | Purpose                                                          |
|----------------------|------------------------------------------------------------------|
| `ITMUX_CLAUDE_HOME`  | Path to the host `~/.claude/` directory (overrides `$HOME/.claude`) |
| `ITMUX_CLAUDE_JSON`  | Path to the host `~/.claude.json` file (overrides `$HOME/.claude.json`) |
| `ITMUX_CODEX_HOME`   | Path to the host `~/.codex/` directory (overrides `$HOME/.codex`)   |
| `ITMUX_GEMINI_HOME`  | Path to the host `~/.gemini/` directory (overrides `$HOME/.gemini`) |

`ITMUX_CLAUDE_JSON` is separate from `ITMUX_CLAUDE_HOME` because the
two paths may not be siblings inside the calling container — the host's
`~/.claude/` and `~/.claude.json` are usually mounted independently.

`$HOME` discovery is still the default when an env var is not set, so
existing host callers are unaffected. Setting an env var to a missing
path yields the same "agent disabled" outcome as not setting it (the
override is opt-in; the driver does not silently fall back to `$HOME`
when an explicit override is supplied).

Python API equivalents (for callers wiring `host_auth` themselves):

```python
ws = InteractiveTmuxWorkspace.start_workspace(
    name="my-ws",
    host_auth={
        "claude": Path("/mnt/host-claude"),
        "codex":  Path("/mnt/host-codex"),
        "gemini": Path("/mnt/host-gemini"),
    },
    host_claude_dotjson=Path("/mnt/host-claude.json"),  # explicit dotjson
)
```

The same `host_claude_dotjson` kwarg exists on
`InteractiveTmuxProvider(default_host_claude_dotjson=)` and on the
provider's `__init__` defaults (which read the env vars automatically).

## Loading Claude Code plugins into the workspace

Plugins for the in-container `claude` TUI must be passed at launch via
`claude --plugin-dir <path>`. The driver builds one such flag per entry.
**`~/.claude.json`'s `installedPlugins` field is silently ignored by the
tmux-driven TUI** — proven by Syntropic137's workflow-skills bridge
experiment (`docs/plans/workflow-skills.md` §9). The `--plugin-dir` flag
is the only mechanism that actually loads plugins.

| Config surface                          | How to set                                        |
|-----------------------------------------|---------------------------------------------------|
| `ITMUX_CLAUDE_PLUGIN_DIRS` env var      | Colon-separated list of container-side paths (like `$PATH`) |
| `start_workspace(claude_plugin_dirs=)`  | `list[Path]` — Python API equivalent              |
| `InteractiveTmuxProvider(default_claude_plugin_dirs=)` | Adapter constructor kwarg          |

```bash
export ITMUX_CLAUDE_PLUGIN_DIRS=/opt/skills:/opt/observability
python3 driver/interactive_tmux.py start --name w1
# launches: claude --plugin-dir /opt/skills --plugin-dir /opt/observability
```

```python
ws = InteractiveTmuxWorkspace.start_workspace(
    name="w1",
    host_auth={"claude": Path("~/.claude").expanduser()},
    claude_plugin_dirs=[Path("/opt/skills"), Path("/opt/observability")],
)
```

The paths are container-side — the caller must already have arranged for
them to exist inside the workspace container (typical setup: the
integrator bind-mounts a host directory in at the same path). Paths with
spaces and other shell-special characters are quoted with `shlex.quote`
so they survive the tmux send-keys path.

Codex and Gemini ignore `claude_plugin_dirs` (no equivalent CLI flag);
the signature parity exists for future agent additions.

## Credentials are NEVER baked or committed

`docker run` mounts throwaway host-side copies. The image contains zero
credential bytes. The `runs/` directory is shell-script output (transcripts
of model responses) and is safe to commit; the credentials themselves
never leave `/tmp/interactive-tmux-*` on the host.

## Smoke test

Pre-reqs (also enforced in `scripts/smoke.sh`'s header — pulled forward
here so consumers don't have to read the script first):

- Image `agentic-workspace-interactive-tmux:latest` is built (run the
  Build step above first; the smoke script does not build for you).
- The host has all three agent CLIs authed:
  - `~/.claude/.credentials.json` exists (run `claude` once to login),
    plus `~/.claude.json` present at `$HOME` (see auth section above).
  - `~/.codex/auth.json` exists (run `codex` once to login).
  - `~/.gemini/` exists with valid `GEMINI_API_KEY` env or settings.
- `docker` is on `PATH` and the user can `docker run` without `sudo`.

Then:

```bash
bash providers/workspaces/interactive-tmux/scripts/smoke.sh
```

Starts a workspace, sends one echo-token prompt per agent, captures the
response, verifies each token appears in its transcript. Writes
`runs/smoke-<agent>.txt` files as evidence.

## Startup readiness & structured results

`start_workspace` and `await_completion` both return structured results
shaped to mirror `agentic_isolation.ExecuteResult`. EXP-05's codex
cross-review (M1 + M3) flagged that the prior bare-bool returns and
warning-only startup misses made the provider hard to integrate.

- `InteractiveTmuxWorkspace.start_workspace(..., strict_startup=True)`
  (the default) raises `StartupReadinessError` if any enabled agent's
  pane fails to reach `is_ready()` within `startup_timeout_s`. The
  exception carries `.startup_status: dict[agent, AwaitResult]` so
  callers can see exactly which pane failed and why.
- `strict_startup=False` returns the workspace anyway and populates
  `ws.startup_status` with the per-agent `AwaitResult`s for inspection.
  The bundled `scripts/smoke.sh` CLI defaults to lax (and echoes the
  status as JSON) so a missed gemini gate doesn't fail the whole smoke,
  but Python callers should keep the strict default for orchestrator
  safety.
- `ws.await_completion(agent, timeout=…)` now returns an `AwaitResult`
  with `ready / timed_out / reason / duration_ms / stable_polls_observed
  / pane`. Existing call sites can read `.ready` for the old boolean.
  Failure modes are now distinguishable: `reason="timeout_never_ready"`
  vs `"timeout_unstable"` vs `"error"`.

### `WorkspaceProvider` adapter for `agentic_isolation`

If you're already orchestrating with `agentic_isolation.WorkspaceProvider`
(create / destroy / execute / write_file / read_file / file_exists), use
the adapter at
`agentic_isolation.providers.interactive_tmux.InteractiveTmuxProvider` —
it satisfies the protocol on top of this provider's start/send/await/
capture. The underlying driver workspace stays reachable on
`workspace._handle` for the richer prompt round-trip API:

```python
from agentic_isolation.providers.interactive_tmux import InteractiveTmuxProvider
from agentic_isolation.config import WorkspaceConfig

provider = InteractiveTmuxProvider()
ws = await provider.create(WorkspaceConfig(working_dir="/workspace"))
res = await provider.execute(ws, "echo hello")
assert res.exit_code == 0 and res.stdout.strip() == "hello"
await provider.write_file(ws, "note.txt", "from adapter")
assert await provider.file_exists(ws, "note.txt")
assert (await provider.read_file(ws, "note.txt")) == "from adapter"

ws._handle.send_message("claude", "ping")
result = ws._handle.await_completion("claude", timeout=60)
print(result.reason, result.duration_ms)

await provider.destroy(ws)
```

## What this provider does NOT do (today)

- **Stream partial responses.** The API is poll-then-capture. A
  structured event stream / token-level partial-output contract is the
  next API surface to add (tracked as future work for Syntropic137
  integration); poll-then-capture is the v1.
- **Reconnect to a running workspace from a different driver process.**
- **Plugin baking.** The three CLIs run as humans run them; plugin
  participation through the interactive transport is a separate arc.
- **Plumb every `WorkspaceConfig` field through `create()`.** The
  `InteractiveTmuxProvider` adapter honors `image`, `working_dir`, and
  `labels["agents"]`; the rest (mounts, secrets, env, security, limits)
  are not yet plumbed because this driver does its own bind-mount layout
  for credentials. Adding pass-through is tracked alongside the streaming
  roadmap.

## See also

- `experiments/EXP-05-interactive-tmux-provider.md` — design,
  hypothesis, run evidence, verdict.
- `experiments/LAB-PLAN.md` (on `ntm/agentprims/cc_1`) — the broader
  lab roadmap.
- `experiments/EXP-01-claude-tmux-workspace.md` and friends — per-agent
  protocol validation that this provider is the integration of.
