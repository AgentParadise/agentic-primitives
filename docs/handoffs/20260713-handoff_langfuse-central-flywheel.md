# Handoff: Central LangFuse and Flywheel VPS Exporters

**Date:** 2026-07-13  
**Primary repo:** `AgentParadise/agentic-primitives`  
**Branch:** `feat/observability-exporter-primitive`  
**Status:** Mac Mini server, MacBook exporters, and Flywheel VPS exporters are
verified. Isolated Docker workspace setup remains to be exercised.

## Goal

Operate one self-hosted LangFuse instance on the Mac Mini. Send usable traces
from MacBook, Flywheel VPS, and isolated Docker workspaces through LangFuse's
official Codex and Claude Code plugins. Do not reintroduce the retired Rust
OTLP writer into the execution path.

## IaC Ownership

The deployment is deliberately split across two repositories.

### Generic LangFuse Package

This repository owns reusable server deployment and client guidance:

- `infra/langfuse/self-hosted/deploy.sh` initializes, starts, upgrades, and
  checks the upstream LangFuse Compose deployment.
- `infra/langfuse/self-hosted/compose.private.yaml` binds the server only to
  `127.0.0.1:19431`.
- `infra/langfuse/self-hosted/tailscale/langfuse-acl-snippet.jsonc` describes
  the required private Tailnet service access.
- `docs/runbooks/langfuse-observability.md` is the setup source of truth. It
  includes the trace identity contract and verification steps.

Keep this IaC generic. It may deploy to a Mac Mini, VPS, or Docker host; do not
add Mac-Mini-specific filesystem paths or credentials here.

Important pushed commits:

- `dbfc669` reserves the private LangFuse service port.
- `263fa7f` aligns Tailscale ingress behavior.
- `d862e73` defines the canonical trace identity contract.

### Mac Mini and Tailnet Policy

`/Users/neural/Code/HomeLab/openclaw-hermes_infra-as-code` owns machine and
Tailnet concerns:

- `features/tailscale/acl.jsonc` is the canonical Tailnet ACL.
- `machines/macmini/tailscale-serve.sh` exposes the local backend through
  Tailscale HTTP Serve on port `19431`.
- `machines/macmini/setup.sh` converges Mac Mini service tags and setup.
- HomeLab commit `75c31f6` adds the Flywheel to LangFuse ACL rule.

The operator must paste the complete ACL file into the Tailscale admin console
and save it. A local HomeLab commit alone does not activate Tailnet policy.

## Central Server

- MagicDNS: `macmini.tail3b2f78.ts.net`
- Endpoint: `http://macmini.tail3b2f78.ts.net:19431`
- Docker bind: `127.0.0.1:19431`
- Health: `GET /api/public/health`
- Transport: Tailnet WireGuard plus Tailscale HTTP Serve; no public listener.

Project keys and LangFuse administrator credentials must remain in the OS
secret store or a host-local protected configuration file. Never put them in
source control, shell history, logs, or this handoff.

## Trace Identity Contract

Every trace must have a stable environment plus harness and host tags.

| Emitter | Environment | Required tags |
| --- | --- | --- |
| MacBook Claude | `local-macbook` | `harness:claude`, `host:macbook` |
| MacBook Codex | `local-macbook` | `harness:codex`, `host:macbook` |
| Flywheel Claude | `flywheel-vps` | `harness:claude`, `host:flywheel-vps` |
| Flywheel Codex | `flywheel-vps` | `harness:codex`, `host:flywheel-vps` |
| Isolated Docker workspace | `docker-workspace` | harness tag and `host:<launcher-host>` |

Use lowercase hyphenated identifiers. Use `neuralempowerment` as the local
non-email user ID when needed. Do not send email addresses or other personal
identifiers as user IDs, tags, environments, names, or metadata.

## MacBook Client State

The MacBook stores the central project keys in macOS Keychain under:

- `langfuse_macmini_public_key`
- `langfuse_macmini_secret_key`

Wrappers are `~/.local/bin/codex-langfuse` and
`~/.local/bin/claude-langfuse`; fresh Zsh sessions route `codex` and `claude`
through them via `~/.zshrc`. Restart existing agent sessions because hooks and
environment are loaded at startup.

Verified traces:

- Codex: `25bef32d5bd3e184494a486e9789170a`
- Claude: `4fcdddf612733f9f3c942eba8c47c979`

The Claude plugin's active cache includes a local compatibility adjustment: an
explicit `LANGFUSE_*` environment takes precedence over stale persisted plugin
options, and `CC_LANGFUSE_TAGS` supplies normalized tags. A plugin update can
overwrite that adjustment; re-run a real Claude tool-call trace after updates
and upstream the behavior when possible.

## Flywheel VPS Client State

- SSH host: `flywheel`, user `ubuntu`
- Tailnet identity: `flywheel.tail3b2f78.ts.net`, tag `tag:flywheel`
- Checkout: `/home/ubuntu/Code/NeuralEmpowerment/agentic-coding-flywheel`
- Protected credentials: `~/.config/langfuse/client.env`, mode `0600`
- Wrappers: `~/.local/bin/codex-langfuse` and
  `~/.local/bin/claude-langfuse`
- Both official LangFuse plugins are installed and enabled.

The wrappers set the Mac Mini endpoint, project credentials, environment,
normalized tags, and `user_id=neuralempowerment`. They are aliased from
`~/.bashrc` for fresh VPS shells.

The policy needed for this route is:

```jsonc
{
  "action": "accept",
  "src": ["tag:flywheel"],
  "dst": ["tag:langfuse:19431"]
}
```

It is active as of this handoff. Confirm independently before debugging clients:

```bash
ssh flywheel \
  'curl -fsS http://macmini.tail3b2f78.ts.net:19431/api/public/health'
```

Verified central traces:

- Codex: `14c8b03ae3578beb8b539af97d457e2a`
  - `environment=flywheel-vps`
  - tags `harness:codex`, `host:flywheel-vps`
  - generation and `exec_command` observations have input/output.
- Claude: `8303ddd58331fbb14e61ba9ca57deb44`
  - `environment=flywheel-vps`
  - tags `harness:claude`, `host:flywheel-vps`
  - generation, Bash tool, and conversational-turn observations have
    input/output.

## Standard Verification for a New Host

1. Configure the generic `LANGFUSE_*` server/key variables from a protected
   secret source; do not bake them into an image.
2. Assign a new environment and `host:` tag according to the runbook.
3. Install the official Codex and Claude plugins and create wrappers that add
   their respective harness tags.
4. Verify `GET $LANGFUSE_BASE_URL/api/public/health` from the client host.
5. Run one real, read-only Codex tool call and one Claude Bash tool call.
6. In LangFuse, filter by the new environment and confirm both harness tags,
   the host tag, populated tool inputs/outputs, and non-personal user ID.
7. Comment the exact trace IDs and evidence on `okrs-51p.11`.

## Remaining Work

1. Apply the same runtime secret and identity setup to isolated Docker
   workspaces, without embedding secrets in images.
2. Move the Claude wrapper compatibility behavior into a supported upstream
   configuration or contribute it to the official plugin.
3. Re-test after every official plugin update, especially Claude Code.
