# Agentic Primitives extraction

Agentic Primitives is being split into focused repositories. This repository
remains available during the compatibility and rollback window. Do not archive
it until the release gates below pass.

## New source repositories

| Surface | Source of truth | Consumer contract |
|---|---|---|
| Installable skills and named collections | [Agentic Skills](https://github.com/AgentParadise/agentic-skills) | Install an individual skill or collection using a pinned Git tag through Vercel Skills. |
| Workspace manifest, runtime libraries, images, and providers | [Agentic Workspace](https://github.com/AgentParadise/agentic-workspace) | Depend on the repository by immutable commit and consume release images by digest. |
| APSS Workspace experiment | [Agent Paradise Standards System](https://github.com/AgentParadise/agent-paradise-standards-system/tree/main/standards-experimental/EXP-V1-0006-workspace) | Validate manifests against the experimental schema and semantic validator. |
| Legacy Claude Code plugin packaging | This repository during migration | Existing installations continue to work until an announced replacement and compatibility release exist. |

The extraction baseline is Agentic Primitives commit
`dd9e9a8c6b017def819369c0530d004bc7acc32c`. Both destination repositories
preserve relevant history from that baseline.

## Consumer migration

### Skills

Discover or install from an immutable Agentic Skills tag. Skills remain
independently installable under `skills/<module>/<skill>`; collection manifests
expand to named groups without flattening that structure.

```bash
npx -y skills@1.7.0 add \
  https://github.com/AgentParadise/agentic-skills/tree/v0.1.0 \
  --list
```

Private consumers must authenticate Git before invoking the installer. Never
place a repository token in a skill manifest or committed configuration.

### Workspace runtime

Replace source paths under `lib/agentic-primitives` with
`lib/agentic-workspace`. Python package names remain stable during the cutover:

- `agentic-events`
- `agentic-isolation`
- `agentic-logging`
- `agentic-memory`
- `agentic-session-store`

Workspace images must be selected by the multi-architecture index digest from a
signed release. Consumers must update the digest and expected Sigstore workflow
identity together. Never promote `latest` into production configuration.

## Rollback and archive gates

Rollback is the previous Agentic Primitives submodule commit, image digest, and
certificate identity as one atomic consumer change.

Archive this repository only after all of these are true:

1. Agentic Skills has a verified immutable release and cross-harness install proof.
2. Agentic Workspace has two successful signed releases.
3. Syntropic137 has released against Agentic Workspace and passed its rollback proof.
4. An owned-reference audit finds no active consumers of this repository.

Until then, changes here should be limited to compatibility, security, and
migration documentation. New skills belong in Agentic Skills. New workspace
runtime or provider work belongs in Agentic Workspace.
