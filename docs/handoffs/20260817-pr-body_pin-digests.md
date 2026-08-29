# PR body: pin workspace images by digest and verify signatures

For `syntropic137` branch `fix/pin-workspace-image-digests` into `main`.
Not opened yet: GitHub API was returning 503s on 2026-08-17.

Title: `fix(workspace): pin workspace images by digest and verify signatures before use`

---

## Summary

Syntropic137 pulled `ghcr.io/agentparadise/agentic-workspace-claude-cli:latest`, and that tag is overwritten on **every push to agentic-primitives main**. So every merge there silently changed what this orchestrator ran.

Not hypothetical. On 2026-08-16 an unconditional post-agent wrapper reached `:latest` on merge: containers with no capability enabled kept bash as PID 1 and were SIGKILLed 1.5s after SIGTERM regardless of `docker stop -t`. Fixed upstream in `5744b86`, but anything pulling in between got it.

**Tags are mutable in OCI by design. A digest is the only real pin.**

Phase 1 of `agentic-primitives/docs/handoffs/20260817-handoff_secure-release-process.md`. Needs no changes to agentic-primitives and removes the exposure on its own.

## Changes

- Both workspace images pinned by digest (`image@sha256:...`), configurable via settings with working defaults.
- `cosign verify` before a container runs, failing closed.
- Local development preserved: bare-name images (`agentic-workspace-claude-cli:dev`) are classified local and skipped with a warning.
- Escape hatch `SYN_IMAGE_VERIFY_ENABLED=false` logs a WARNING on every provision, so disabling it is loud.

Pinned digests, resolved and verified against the live registry:

```
claude-cli       sha256:0d53e7a1a9476c5c45cbb7b1467adc004347bef4cf9168c013a6bc7caa5c3f07  (from d31c88a)
interactive-tmux sha256:43247b67...
```

`d31c88a` carries the capability runtime, the entrypoint `exec` fix, and the credential-repr fix, so this is also a small upgrade over drifting on `:latest`.

## The finding that mattered

Verification of the real pins initially returned **"no signatures found."**

The publisher writes a Sigstore bundle under the `sha256-<digest>` tag rather than the legacy `.sig` tag, so without `--new-bundle-format` the check fails **100% of the time**. That is a control that can only ever block, which someone eventually switches off, leaving neither verification nor the illusion of it. A test locks the flag in.

## Cosign identity

Read from agentic-primitives' `build-workspace-images.yml`, then confirmed empirically against the live signature:

- SAN: `https://github.com/AgentParadise/agentic-primitives/.github/workflows/build-workspace-images.yml@refs/heads/main`
- Issuer: `https://token.actions.githubusercontent.com`

The default identity is a regexp anchored to that workflow on `main|release`, so the planned release-branch move does not need an emergency config change.

## Missing cosign is a hard failure, deliberately

A missing verifier and a forged signature have the same outcome if the check is skipped, and an absent binary is the likeliest way this dies silently. Local images still skip.

**Consequence: cosign is now a prerequisite for provisioning remote images.** It should be added to the setup CLI's checks; tracked as task 1.5 in the handoff.

## Verification

```
ruff check .                    All checks passed!
ruff format --check .           1230 files already formatted
pyright                         0 errors, 13 warnings
pytest syn-shared+syn-adapters  749 passed, 2 xfailed (pre-existing, #444)
scripts/import_check.py         All 9 package imports OK
```

Live, with cosign v3.1.3:

```
verify pinned digest  -> claims validated, transparency log verified, cert chain verified
wrong signer identity -> Error: expected SAN to match ... got https://github.com/AgentParadise/...
unsigned image        -> Error: no signatures found
```

Three adapter-level tests drive the real code path with a provider double. Removing the `verify_image(image)` call makes all three fail with `SpyProvider.create was reached; an unverified image would have run`, so the control is proven load-bearing rather than decorative.

## Not in scope

Phases 2 through 5 of the handoff: the `release` branch, the release gate, image tag semantics (#304), and documentation.
