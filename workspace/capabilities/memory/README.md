# memory capability

Opts a workspace image into an agentic-memory backend, so an agent's
retain/recall tools reach a real, correctly-scoped memory bank.

This module predates the capability system: it was ADR-036's memory
primitive, and it moved under `/opt/agentic/capabilities/memory/` when
[ADR-040](../../../docs/adrs/040-workspace-capability-modules.md)
generalized that design. ADR-036's reasoning still governs this module's
posture; only its plumbing changed.

See `doctor` in this directory for the entry point, and
`lib/python/agentic_memory/agentic_memory/contract.py` for the env-var
contract (`Env` in that module is the single source of truth for every
`AGENTIC_MEMORY_*` variable this capability reads).

## Contract

| Contract var | Required | Meaning |
|---|---|---|
| `AGENTIC_MEMORY_PROVIDER` | yes | Selects the adapter directory. Unset or `none` makes the whole capability a no-op. |
| `AGENTIC_MEMORY_NAMESPACE` | yes | The isolation unit. Everything the agent retains is scoped to it. |
| `AGENTIC_MEMORY_URL` | yes | Backend base URL. |
| `AGENTIC_MEMORY_NAMESPACE_KIND` | no | Semantic hint only: `task` (default), `domain`, `workflow`, `user`, `session`, `project`, `custom`. Adapters MAY use it for prefixing or log labels. Adapters MUST NOT change isolation semantics based on it: isolation is always per namespace, regardless of kind. |
| `AGENTIC_MEMORY_AUTH` | no | Bearer token for the backend. |
| `AGENTIC_MEMORY_CONFIG_JSON` | no | Escape hatch for adapter-specific config the core contract does not model. |

`AGENTIC_MEMORY_READY=1` is exported by the lifecycle when `init.sh`
returns successfully. This predates ADR-040 and downstream tooling reads
it, so the generic capability loop preserves it explicitly.

`AGENTIC_MEMORY_NAMESPACE` is constrained to `[a-zA-Z0-9._:-]+`: no spaces,
no slashes, no shell metacharacters. `AGENTIC_MEMORY_PROVIDER` is
constrained to `[a-zA-Z0-9._-]+` because provider names map to a directory
under `/opt/agentic/capabilities/memory/`.

## The `hindsight` provider adapter

`hindsight/init.sh` is the adapter for `AGENTIC_MEMORY_PROVIDER=hindsight`.
It is sourced by `/opt/agentic/entrypoint.sh` section 5.6 and translates
the contract into the `HINDSIGHT_*` env vars the hindsight Claude Code
plugin reads:

| Contract var | Adapter behavior |
|---|---|
| `AGENTIC_MEMORY_URL` | exported as `HINDSIGHT_API_URL` |
| `AGENTIC_MEMORY_AUTH` | exported as `HINDSIGHT_API_TOKEN`, only if set |
| `AGENTIC_MEMORY_NAMESPACE` | exported as `HINDSIGHT_BANK_ID` |
| (none) | `HINDSIGHT_DYNAMIC_BANK_ID=false`, always |
| `AGENTIC_MEMORY_CONFIG_JSON` | written verbatim to `~/.hindsight/claude-code.json` |

### Why `HINDSIGHT_DYNAMIC_BANK_ID=false` is forced

The `HINDSIGHT_BANK_ID` env override is honored **only** when
`dynamicBankId` is false. This was established empirically in
agentic-memory's bank-derivation-modes probe. If the adapter did not force
static bank-id mode, the contract's namespace would be silently ignored and
the agent would retain into whatever bank hindsight derived on its own,
which is the exact silent misconfiguration ADR-036 exists to prevent.

`hindsight/doctor.sh` re-checks this at startup and **auto-fixes** it: if
`~/.hindsight/claude-code.json` exists with `dynamicBankId` not false, the
file is rewritten with `dynamicBankId: false`. That is a stale-state issue
rather than an operator decision, so correcting it silently is appropriate.
A config file that cannot be parsed is a hard fail instead.

## Doctor

```bash
/opt/agentic/capabilities/memory/doctor [--json] [--verbose] [--fix]
```

Run automatically by entrypoint section 5.7 with `--json`, appending one
JSON line per run to `${AGENTIC_CAPABILITY_AUDIT_DIR:-/var/agentic/memory-doctor}/YYYY-MM-DD.jsonl`.
**Any failure hard-stops the container**, per ADR-036: opting into a
provider is opting into loud failure, and failing before the agent starts
is free.

Eight checks, in order:

| Check | What it establishes |
|---|---|
| `env_contract` | `PROVIDER`, `NAMESPACE`, and `URL` are all present and non-empty. |
| `namespace_well_formed` | The namespace matches the allowed charset. |
| `provider_known` | The provider name is one this image knows. |
| `adapter_exists` | `/opt/agentic/capabilities/memory/<provider>/` is really there. |
| `config_json_valid` | `AGENTIC_MEMORY_CONFIG_JSON` parses, when set. |
| `backend_dns` | The backend host resolves. |
| `backend_health` | The backend answers. |
| `provider_specific` | Delegates to `<provider>/doctor.sh`, which for hindsight checks bank reachability and the `dynamicBankId` consistency described above. |

`--fix` currently reports what it would change; `--apply` is not yet
implemented.

Running it by hand:

```bash
AGENTIC_MEMORY_PROVIDER=hindsight \
AGENTIC_MEMORY_NAMESPACE=my-bank \
AGENTIC_MEMORY_URL=http://host.docker.internal:8080 \
/opt/agentic/capabilities/memory/doctor --json
```

The provider-specific half can be exercised on its own, with the adapter's
exports already in the shell:

```bash
. /opt/agentic/capabilities/memory/hindsight/init.sh
/opt/agentic/capabilities/memory/hindsight/doctor.sh
```

## What this module deliberately does not do

- **It has no `finalize.sh`.** Memory is fully configured before the agent
  runs and has nothing to flush afterward. The post-agent hook is optional
  precisely so capabilities like this one can skip it.
- **It never mutates the backend.** The doctor reports on bank state; it
  does not create, delete, or reshape banks. Operators keep authority over
  bank lifecycle and policy. The one exception is the client-side
  `dynamicBankId` auto-fix above, which touches only a local config file.

## Migration note (image 1.x to 2.0.0)

Three things moved when this capability was generalized:

1. `/opt/agentic/memory/` is now `/opt/agentic/capabilities/memory/`, for
   both the `doctor` entry and the per-provider adapters.
2. `AGENTIC_MEMORY_AUDIT_DIR` is now `AGENTIC_CAPABILITY_AUDIT_DIR`, and it
   applies to every capability rather than just this one. The per-capability
   default path is unchanged, so hosts bind-mounting
   `/var/agentic/memory-doctor` need no change.
3. `AGENTIC_MEMORY_PROVIDER` alone no longer activates memory. `memory`
   must also appear in `AGENTIC_CAPABILITIES`, which the image default
   provides. If you override that variable, include `memory` or this
   capability silently stops running (the entrypoint warns on stderr in
   exactly that case).

The contract variables themselves are unchanged.
