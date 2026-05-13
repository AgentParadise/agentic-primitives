# Memory Primitive + Doctor Design (Workspace Image)

**Status:** Draft
**Created:** 2026-05-13
**Author:** NeuralEmpowerment
**Related:** [ADR-036](../../adrs/036-memory-primitive-and-doctor.md), [ADR-035 Workspace Injection Contract](../../adrs/035-workspace-injection-contract.md)
**Sibling design doc:** [agentic-memory/docs/architecture/memory-contract.md](../../../../agentic-memory/docs/architecture/memory-contract.md)

## Summary

Add a **memory primitive** to the `agentic-workspace-claude-cli` image so any
orchestrator (agentic-domain-runner, Syntropic137, future) can attach a
memory backend (hindsight first, lossless-claw or others later) without
coupling to a specific provider. Pair it with a **doctor primitive** that
validates the contract is wired correctly, sniffs the backend is reachable,
and surfaces actionable diagnostics — automatically at container start
(soft-fail by default) and on-demand via a CLI subcommand.

The primitive extends the [Workspace Injection Contract](../../adrs/035-workspace-injection-contract.md)
(ADR-035) following the same shape: three env vars from the host, a baked-in
adapter layer inside the image, soft-fail-with-loud-logs as the default
posture.

## Goals

- **Provider-agnostic at the host layer.** Orchestrators set three env vars;
  they do not learn anything about hindsight specifics.
- **Adapter-driven at the image layer.** Per-provider translation logic lives
  in the image at `/opt/agentic/memory/<provider>/init.sh`, baked at build
  time.
- **Doctor as first-class diagnostic.** Misconfiguration must fail loud at
  the *human* layer, even when the workspace itself fails soft at the agent
  layer.
- **Backwards compatible.** A workspace that doesn't set `AGENTIC_MEMORY_PROVIDER`
  is unaffected. Existing orchestrators don't need to change.
- **Consistent with ADR-035 conventions.** Same env-var prefix, same
  entrypoint-section pattern, same soft-fail default.

## Non-goals

- **Defining the upstream memory backend** (hindsight, lossless-claw, …) —
  those are external services; this primitive only wires *into* them.
- **Stacking multiple providers.** One workspace, one memory provider for
  v1. Stacking is a future concern.
- **Cross-namespace recall configuration.** Hindsight's `recallAdditionalBanks`
  is config-file-only, not env-overridable; defer until the contract gains
  an `AGENTIC_MEMORY_CONFIG_JSON` consumer.
- **Namespace lifecycle (creation/deletion).** The adapter assumes the
  backend lazy-creates on first retain. Tear-down is operator-side.
- **Replacing or wrapping `claude doctor`.** This doctor is scoped to the
  memory contract, not the broader Claude CLI install.

## Design

### Layer 1 — The Memory Contract (host → workspace image)

Three required env vars from the host, three optional:

| Env var | Required | Meaning |
|---|---|---|
| `AGENTIC_MEMORY_PROVIDER` | yes (to opt in) | provider name — `hindsight`, `lossless-claw`, `none`, … |
| `AGENTIC_MEMORY_NAMESPACE` | yes | host-supplied scope identifier (task ID, workflow ID, …) |
| `AGENTIC_MEMORY_URL` | yes (network providers) | base URL of provider backend, reachable from container |
| `AGENTIC_MEMORY_NAMESPACE_KIND` | no, default `task` | semantic hint — `task` \| `domain` \| `workflow` \| `user` \| `session` \| `project` \| `custom` |
| `AGENTIC_MEMORY_AUTH` | no | provider-specific token (passed verbatim) |
| `AGENTIC_MEMORY_CONFIG_JSON` | no | adapter-specific config (JSON, escape hatch) |
| `AGENTIC_MEMORY_REQUIRED` | no, default `false` | if `true`, doctor failure exits the entrypoint non-zero. Default soft-fails. |

The host **never** sets provider-specific vars like `HINDSIGHT_BANK_ID`. That
mapping is the adapter's job.

### Layer 2 — Workspace image (the integration point)

#### Entrypoint extensions

Two new sections in
`providers/workspaces/claude-cli/scripts/entrypoint.sh`, after the existing
section 5.5 (workspace context composition):

**Section 5.6 — Memory adapter initialization**

```bash
# --- 5.6 Memory adapter initialization ---
if [ -n "${AGENTIC_MEMORY_PROVIDER:-}" ] && [ "${AGENTIC_MEMORY_PROVIDER}" != "none" ]; then
  adapter="/opt/agentic/memory/${AGENTIC_MEMORY_PROVIDER}/init.sh"
  if [ -f "${adapter}" ]; then
    echo "[entrypoint] memory adapter: ${AGENTIC_MEMORY_PROVIDER}"
    # shellcheck disable=SC1090
    if . "${adapter}"; then
      export AGENTIC_MEMORY_READY=1
    else
      echo "[entrypoint] memory adapter init failed; continuing without memory" >&2
    fi
  else
    echo "[entrypoint] no adapter for memory provider '${AGENTIC_MEMORY_PROVIDER}' (looked at ${adapter})" >&2
  fi
fi
```

**Section 5.7 — Memory doctor preflight**

```bash
# --- 5.7 Memory doctor preflight ---
if [ -n "${AGENTIC_MEMORY_PROVIDER:-}" ] && [ "${AGENTIC_MEMORY_PROVIDER}" != "none" ]; then
  # Run the doctor in --quick mode: minimal checks, machine-readable to stdout,
  # human-readable summary to stderr. Adds <1s to container startup.
  if ! /opt/agentic/memory/doctor --quick --json > /tmp/memory-doctor.json 2> /tmp/memory-doctor.log; then
    cat /tmp/memory-doctor.log >&2
    if [ "${AGENTIC_MEMORY_REQUIRED:-false}" = "true" ]; then
      echo "[entrypoint] AGENTIC_MEMORY_REQUIRED=true and doctor failed; exiting." >&2
      exit 1
    fi
    echo "[entrypoint] memory doctor reported issues (see /tmp/memory-doctor.log); continuing." >&2
  fi
fi
```

The doctor's full output stays on disk at `/tmp/memory-doctor.json` for later
inspection by humans or `claude doctor memory`.

#### Per-provider adapter scripts

Layout:

```
providers/workspaces/claude-cli/
└── memory/
    ├── doctor                              # CLI entry (executable)
    ├── doctor.py                           # Doctor implementation (Python)
    ├── hindsight/
    │   ├── init.sh                         # Translates AGENTIC_MEMORY_* → HINDSIGHT_*
    │   └── doctor.sh                       # Provider-specific health checks
    └── lossless-claw/                      # (placeholder for future)
        └── init.sh
```

`hindsight/init.sh` is the canonical example:

```bash
#!/usr/bin/env bash
# Hindsight adapter — translates AGENTIC_MEMORY_* contract → HINDSIGHT_* env.

set -e

export HINDSIGHT_API_URL="${AGENTIC_MEMORY_URL}"
[ -n "${AGENTIC_MEMORY_AUTH:-}" ] && export HINDSIGHT_API_TOKEN="${AGENTIC_MEMORY_AUTH}"

# Bank scoping: HINDSIGHT_BANK_ID env override only takes effect when
# dynamicBankId=false (verified in hindsight/bank.py:97).
export HINDSIGHT_DYNAMIC_BANK_ID=false
export HINDSIGHT_BANK_ID="${AGENTIC_MEMORY_NAMESPACE}"

# Optional rich config.
if [ -n "${AGENTIC_MEMORY_CONFIG_JSON:-}" ]; then
  mkdir -p "${HOME}/.hindsight"
  printf '%s' "${AGENTIC_MEMORY_CONFIG_JSON}" > "${HOME}/.hindsight/claude-code.json"
fi
```

Adapter scripts are **deliberately small** (~30 lines). The doctor is where
validation logic lives — not duplicated per-adapter.

### Layer 3 — The Doctor

#### Invocation surface

```sh
# 1. Automatic preflight at container start (section 5.7 entrypoint)
#    Runs --quick by default; ~1s of checks; soft-fails by default.
#    Behavior gated by AGENTIC_MEMORY_REQUIRED.

# 2. Explicit on-demand from inside the container or wrapper
/opt/agentic/memory/doctor [--quick] [--fix] [--json] [--verbose] [--provider PROVIDER]
```

Modes:

| Flag | Behavior |
|---|---|
| (default) | Full checks (env vars + adapter + backend health + bank reachability). Pretty output to stderr; exit 0/1/2. |
| `--quick` | Minimal preflight (env vars + adapter file exists + backend `/health` 200). Used by section 5.7. |
| `--fix` | Apply auto-correctable fixes. See "Auto-fix scope" below. Default is dry-run; pair with `--apply` to commit. |
| `--apply` | Commit `--fix` changes (no-op without `--fix`). |
| `--json` | Machine-readable JSON to stdout. Pretty text always goes to stderr. |
| `--verbose` | Include adapter source, env-var values (redacted), backend response bodies, timings. |
| `--provider <name>` | Override `AGENTIC_MEMORY_PROVIDER` for this invocation. Useful for testing. |

Exit codes:

- `0` — all checks pass
- `1` — warnings present (issues exist but not blocking — agent will run)
- `2` — failures present (backend unreachable, adapter missing, etc. — agent
  will run with `AGENTIC_MEMORY_READY` unset, retain/recall hooks won't
  function)

#### Checks performed

Standard checks (the contract layer — provider-agnostic):

1. **`env_contract`** — `AGENTIC_MEMORY_PROVIDER`, `AGENTIC_MEMORY_NAMESPACE`,
   and `AGENTIC_MEMORY_URL` (when provider isn't `none`) are all set.
2. **`namespace_well_formed`** — `AGENTIC_MEMORY_NAMESPACE` matches
   `[a-zA-Z0-9._:-]+`. No spaces, no slashes, no shell metacharacters.
3. **`provider_known`** — `AGENTIC_MEMORY_PROVIDER` matches a directory under
   `/opt/agentic/memory/`.
4. **`adapter_exists`** — `/opt/agentic/memory/<provider>/init.sh` is a file
   and executable.
5. **`config_json_valid`** — if `AGENTIC_MEMORY_CONFIG_JSON` is set, it parses
   as JSON.

Backend checks (require network — included in default, skipped in
`--quick`):

6. **`backend_dns`** — hostname in `AGENTIC_MEMORY_URL` resolves.
7. **`backend_health`** — `GET <url>/health` returns 200.

Provider-specific checks (delegated to adapter's `doctor.sh`):

8. **`provider_specific`** — adapter's `doctor.sh` runs additional checks
   relevant to that provider. For hindsight: bank existence (`GET /banks/<id>`
   returns 200 or 404 — 404 is fine, lazy-create on first retain).

#### Output schema (JSON)

```json
{
  "doctor_version": "1.0",
  "timestamp": "2026-05-13T01:42:00Z",
  "provider": "hindsight",
  "namespace": "task-abc",
  "status": "ok",
  "checks": [
    {
      "name": "env_contract",
      "status": "ok",
      "message": "All required env vars set."
    },
    {
      "name": "namespace_well_formed",
      "status": "ok",
      "value": "task-abc"
    },
    {
      "name": "provider_known",
      "status": "ok",
      "provider": "hindsight"
    },
    {
      "name": "adapter_exists",
      "status": "ok",
      "path": "/opt/agentic/memory/hindsight/init.sh"
    },
    {
      "name": "config_json_valid",
      "status": "skipped",
      "reason": "AGENTIC_MEMORY_CONFIG_JSON not set"
    },
    {
      "name": "backend_dns",
      "status": "ok",
      "host": "hindsight",
      "resolved_to": "172.18.0.4"
    },
    {
      "name": "backend_health",
      "status": "ok",
      "url": "http://hindsight:8888/health",
      "response_time_ms": 17
    },
    {
      "name": "provider_specific",
      "status": "ok",
      "details": {
        "bank_exists": false,
        "bank_will_lazy_create": true
      }
    }
  ],
  "warnings": [],
  "fixable": [],
  "exit_code": 0
}
```

Failure example (with auto-fixable issues):

```json
{
  "doctor_version": "1.0",
  "timestamp": "2026-05-13T01:42:00Z",
  "provider": "hindsight",
  "namespace": "task-abc",
  "status": "warning",
  "checks": [
    {
      "name": "namespace_well_formed",
      "status": "warn",
      "value": "task abc/v2",
      "message": "Namespace contains illegal characters (space, slash). Will be sanitized."
    },
    {
      "name": "backend_health",
      "status": "fail",
      "url": "http://hindsight:8888/health",
      "error": "connection refused"
    }
  ],
  "warnings": [
    {
      "code": "namespace_sanitization_required",
      "message": "AGENTIC_MEMORY_NAMESPACE='task abc/v2' will be sanitized to 'task-abc-v2'.",
      "fixable": true,
      "fix": "Set AGENTIC_MEMORY_NAMESPACE='task-abc-v2' explicitly."
    },
    {
      "code": "backend_unreachable",
      "message": "Hindsight backend at http://hindsight:8888 is unreachable.",
      "fixable": false,
      "fix": "Verify hindsight container is running and on the agentic-domain-runner Docker network."
    }
  ],
  "fixable": ["namespace_sanitization_required"],
  "exit_code": 2
}
```

#### Auto-fix scope

`--fix --apply` may auto-correct **client-side** issues:

- **Namespace sanitization** — strip illegal chars; result emitted as a
  suggested env var setting. Writes a `~/.agentic/memory.env` file with the
  corrected value (operator sources it themselves; we don't mutate the
  parent shell).
- **Config-file generation** — if `AGENTIC_MEMORY_CONFIG_JSON` is set,
  write it to the provider's expected path (e.g. `~/.hindsight/claude-code.json`).

`--fix` **never** mutates the backend:
- Does not create banks
- Does not change provider state
- Does not POST anything

This is deliberate. The doctor is a client-side validator, not an admin tool.
Backend-mutating operations belong in provider-specific CLIs (e.g.
`hindsight-cli`).

### Layer 4 — Python helper library

Add `lib/python/agentic_memory/` for shared validation logic the doctor
script uses:

```
lib/python/agentic_memory/
├── pyproject.toml
├── agentic_memory/
│   ├── __init__.py
│   ├── contract.py            # Env-var parsing + namespace validation
│   ├── doctor.py              # Check definitions + runner
│   ├── providers.py           # Provider registry (introspects /opt/agentic/memory/)
│   └── output.py              # JSON + pretty formatters
└── tests/
    ├── test_contract.py
    ├── test_doctor.py
    └── test_providers.py
```

`contract.py` exports a `MemoryContract` dataclass parsed from env vars.
`doctor.py` exports `Check` (one of N), `CheckResult` (ok / warn / fail /
skipped), and a `run_checks(...)` orchestrator. `output.py` handles pretty
text and JSON.

The shell script `/opt/agentic/memory/doctor` is a thin entry that
`exec python -m agentic_memory.doctor "$@"`.

## Adoption by consumers (host orchestrators)

### agentic-domain-runner

In `src/runner/mod.rs` near the existing `AGENTIC_*` injection (~line 171):

```rust
req.env.push(("AGENTIC_MEMORY_PROVIDER".into(), "hindsight".into()));
req.env.push(("AGENTIC_MEMORY_URL".into(), "http://hindsight:8888".into()));
let ns = req.agent_task_id.as_deref().unwrap_or(&task_id);
req.env.push(("AGENTIC_MEMORY_NAMESPACE".into(), ns.to_string()));
req.env.push(("AGENTIC_MEMORY_NAMESPACE_KIND".into(), "task".into()));
```

Four lines. The runner doesn't know what hindsight is — it just plumbs the
contract through.

### Syntropic137 (hypothetical, when ready)

Same env-var contract. Identity model differs:

```python
env["AGENTIC_MEMORY_PROVIDER"] = "hindsight"
env["AGENTIC_MEMORY_URL"] = "http://hindsight.syntropic.svc:8888"
env["AGENTIC_MEMORY_NAMESPACE"] = f"{workflow_id}::{phase}"
env["AGENTIC_MEMORY_NAMESPACE_KIND"] = "workflow"
```

### Hermes Agent

**Not applicable** — Hermes already has a native hindsight integration shipped
upstream (announced 2026-04-06; setup is `hermes memory setup`). Hermes wires
hindsight in via its own plugin slot, not via the agentic-workspace-claude-cli
image. This contract is for the *workspace-image* path; Hermes uses a
different path entirely.

## Implementation plan (sketch — full plan is a separate doc)

Phased:

1. **Phase 1 — Contract + doctor skeleton** (no provider adapters yet).
   - Add Python lib `lib/python/agentic_memory/` with contract parser and
     doctor framework.
   - Implement standard checks 1-7 (env, namespace, adapter, backend).
   - Add `/opt/agentic/memory/doctor` entry in the workspace image
     Dockerfile.
   - Section 5.7 entrypoint integration (calls doctor, soft-fails).
   - Integration test: `tests/integration/test_entrypoint_memory_doctor.py`.
2. **Phase 2 — Hindsight adapter** (first real provider).
   - Add `providers/workspaces/claude-cli/memory/hindsight/init.sh` +
     `doctor.sh`.
   - Section 5.6 entrypoint integration.
   - Integration test: `tests/integration/test_entrypoint_memory_hindsight.py`.
3. **Phase 3 — Adoption in agentic-domain-runner** (a separate PR in that
   repo).
4. **Phase 4 — `--fix` mode** (deferred until phases 1-3 stabilize).
5. **Phase 5 — Second provider adapter** (lossless-claw or whatever ships
   next).

## Open questions

These are deferred to the user before drafting the implementation plan:

1. **Should section 5.7 default to `--quick` or to a full preflight?**
   `--quick` adds <1s; full adds ~5-15s depending on backend latency. Quick
   misses some failure modes (DNS works but provider-specific check fails)
   but lets the container start faster.

   **Spec assumes `--quick`** for now. Open.

2. **Should `AGENTIC_MEMORY_REQUIRED=true` be the default for production
   deployments?** Soft-fail is friendly for development but masks
   misconfiguration in production. Could be opted into via a host-side
   policy (`agentic-domain-runner` sets `AGENTIC_MEMORY_REQUIRED=true` for
   production domains).

   **Spec assumes soft-fail default.** Open.

3. **Should the doctor JSON output be persisted somewhere durable (not just
   `/tmp/`)?** For audit trails, an `audit_logs` field on the hindsight bank
   could record doctor results. Out of scope for v1.

4. **Should there be a hindsight-specific check for `dynamicBankId=true`
   conflicting with `HINDSIGHT_BANK_ID`?** The adapter sets `dynamicBankId=false`
   explicitly via env, but if a `~/.hindsight/claude-code.json` exists with
   `dynamicBankId: true`, the env var is ignored (verified in
   `bank.py:97`). The doctor could warn about this.

   **Spec includes this as a provider-specific check (hindsight's doctor.sh)
   but doesn't auto-fix.** Open.

5. **Where does `claude doctor memory` route to?** A wrapper around
   `/opt/agentic/memory/doctor` from inside the Claude CLI? That couples
   Claude CLI to the memory primitive. Alternative: just document that
   users run `/opt/agentic/memory/doctor` directly.

   **Spec leaves Claude CLI out.** Run `/opt/agentic/memory/doctor`
   directly. Open.

## Test plan

Integration tests live at `tests/integration/`:

- `test_entrypoint_memory_doctor.py` — verifies section 5.7 fires, doctor
  reports correct status for various env-var combinations (all set / one
  missing / bad namespace / no backend), exit codes match spec.
- `test_entrypoint_memory_hindsight.py` — spawns a hindsight `external-pg`
  compose stack on a Docker network, joins workspace container, verifies
  end-to-end: section 5.6 sets `HINDSIGHT_BANK_ID`, section 5.7 doctor
  passes, retain → recall roundtrip via the plugin works.
- `lib/python/agentic_memory/tests/` — unit tests for each check.

## References

- [ADR-035 Workspace Injection Contract](../../adrs/035-workspace-injection-contract.md) — design baseline this extends.
- [agentic-memory/docs/architecture/memory-contract.md](../../../../agentic-memory/docs/architecture/memory-contract.md) — sibling design doc.
- [hindsight bank derivation modes probe](../../../../agentic-memory/experiments/2026-05-12--claude-code--hindsight--bank-derivation-modes/results.md) — empirical evidence that `HINDSIGHT_BANK_ID` env override requires `dynamicBankId=false`.
- [lossless-claw doctor-contract-api](../../../../agentic-memory/lib/lossless-claw/doctor-contract-api.js) — reference for `--fix` semantics.
- [hindsight-cli health command](../../../../agentic-memory/lib/hindsight/hindsight-cli/src/commands/health.rs) — reference for JSON/pretty dual output.
