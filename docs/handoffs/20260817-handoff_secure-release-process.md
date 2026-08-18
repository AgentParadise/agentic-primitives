# Handoff: secure release process for agentic-primitives

**Date:** 2026-08-17
**Status:** Phase 1 complete (pushed, PR pending GitHub availability). Phases 2-5 not started.
**Repos:** `AgentParadise/agentic-primitives` (primary), `syntropic137/syntropic137` (consumer)

Uncommitted working document. Read the whole "Why" section before executing any task: several of these look independent and are not, and the ordering is deliberate.

---

## Why

`build-workspace-images.yml` publishes to GHCR on **every push to main**, tagging `:latest`, `:<version>`, `:<cli_version>` and `:<sha>`.

Syntropic137 pulls `ghcr.io/agentparadise/agentic-workspace-claude-cli:latest`
(`packages/syn-shared/src/syn_shared/settings/workspace_images.py`, `DEFAULT_TAG = "latest"`).

**Every merge to agentic-primitives main silently changes what Syntropic137 runs.**

Not hypothetical. On 2026-08-16 the unconditional post-agent wrapper in `c56b9eb` reached `:latest` on merge: containers with no capability enabled kept bash as PID 1 and SIGKILLed the command 1.5s after SIGTERM regardless of `docker stop -t`. Corrected in `5744b86`. Anything pulling in between got it.

Three compounding defects:

1. **Publishing is not gated.** Any push to main ships an image.
2. **Tags are not content-unique** (issue #304). The version tag is derived by grepping `ARG CLAUDE_CLI_VERSION`, so it names a third-party CLI version, not image contents. Bump `CODEX_CLI_VERSION` alone and the same tag points at different bits.
3. **Signatures are generated but never verified.** cosign keyless signing runs at build. No consumer verifies. Confirmed: no `cosign verify` anywhere in Syntropic137.

### Threat model

| Attack | Control that stops it |
|---|---|
| Attacker gains push access to a publishing branch | Branch protection on `release`, required review |
| Tag silently moves under a consumer | Digest pinning by consumers |
| Registry compromised, image swapped | Signature verification at pull |
| Bad code reaches a release legitimately | Release gate checks, human approval |

**cosign keyless proves "built by this workflow from this repo." It does not prove the code was reviewed.** An attacker who can push to a publishing branch gets a build that signs their image with a valid signature. Signing defends the registry, not the source. This is why gating and review come first, and why signing alone is not a mitigation for the scenario that prompted this work.

### Target model

```
main       development. commit freely. no PR required.
release    protected. PR-only. review required. no direct push.
           images build, publish and sign on push HERE.
tags       cut on release after merge.
```

Main-as-development is deliberate: requiring review on every commit is friction on every change, and the risk being managed is what ships rather than what is committed. No drift risk, because `release` never receives independent development; it only ever receives main.

This matches Syntropic137's existing model. One release model across both repos is worth real money in avoided mistakes.

### Reference implementation

**Do not invent this. Port it.** Syntropic137 already has the whole pattern:

- `.github/workflows/release-gate.yml` triggers on `pull_request: branches: [release]`, jobs: `version-check`, `changelog-check`, `codegen-sync`, `docker-dry-run`, `osv-scan`, `pip-audit`
- `.github/workflows/_check-version.yml` runs `scripts/workflows/bump_version.py --check` (all version files agree) and `--check-release` (version is bumped versus the release branch)
- `.github/workflows/release-create.yml` carries the approval gate
- `release-cli.yaml` and `release-containers.yaml` are `workflow_call` only, with a comment stating `release.published` is deliberately omitted because direct release events bypass the approval gate. **Preserve that reasoning when porting.**
- `docs/release-process.md`

---

## Ordering, and why it is not the intuitive order

The intuitive first move is to gate publishing. That is wrong as a first move: a gated build still overwrites a mutable tag, so it feels safer without being safer.

Digest pinning and verification protect consumers regardless of when or how images are built. Phase 1 first.

---

## Phase 1: stop the bleeding  [COMPLETE]

Branch `fix/pin-workspace-image-digests` in syntropic137, commits `bc0c458c` and `737a6783`, pushed.
**PR not yet opened: GitHub API was returning 503s. Body saved at `docs/handoffs/20260817-pr-body_pin-digests.md`.**

Pinned digests, verified against the live registry:
- `claude-cli` `sha256:0d53e7a1a9476c5c45cbb7b1467adc004347bef4cf9168c013a6bc7caa5c3f07` (from `d31c88a`)
- `interactive-tmux` `sha256:43247b67...`

- [x] **1.1** Syntropic137: replace `DEFAULT_TAG = "latest"` with a pinned digest (`image@sha256:...`) in `packages/syn-shared/src/syn_shared/settings/workspace_images.py`. Immutable by construction; the registry cannot repoint it.
- [x] **1.2** Decide and document how the digest gets bumped: manual PR, or automated with review. It is a dependency update and should read like one.
- [x] **1.3** Syntropic137: run `cosign verify` before use, with the expected workflow identity, failing closed. Without this, signing is evidence nobody reads.
- [x] **1.4** Test the failure path explicitly: an image that fails verification must not run. A verification step that cannot fail is not a control.

### Phase 1 findings worth keeping

- **`--new-bundle-format` is required.** Verification of the real images returned "no signatures found" without it: the publisher writes a Sigstore bundle under the `sha256-<digest>` tag, not the legacy `.sig` tag. Without the flag the check fails 100% of the time, which is a control that can only ever block and would eventually be switched off. A test locks it in.
- **Cosign identity values**, read from `build-workspace-images.yml` and confirmed empirically:
  - SAN `https://github.com/AgentParadise/agentic-primitives/.github/workflows/build-workspace-images.yml@refs/heads/main`
  - Issuer `https://token.actions.githubusercontent.com`
  - Default is a regexp anchored to `main|release`, so the Phase 2 branch move needs no emergency config change.
- **`interactive-tmux` IS published and signed.** An earlier note in this doc said it might not be; that was wrong.
- **Missing cosign is a hard failure for remote images, by design.** A missing verifier and a forged signature are indistinguishable if the check is skipped.

### New task from Phase 1

- [ ] **1.5** `npx @syntropic137/setup` must check for cosign and install it or instruct the user. Cosign is now a prerequisite for provisioning remote images, and a self-hoster without it will hit a hard failure at first provision. cosign v3.1.3 was installed on the operator's machine during Phase 1; other environments have not been handled.

## ORDERING CORRECTION (2026-08-17)

The original Phase 2/3 split was wrong. Creating `release` before the gate exists means the
first release goes through ungated, and the workflows must already be present ON `release`
for them to fire when it receives pushes.

**Correct order: workflows onto main FIRST, then create the branch, then protect it.**
Both workflow changes are inert until `release` exists, so landing them on main is safe.

## Phase 2a: workflows onto main (do FIRST)

- [ ] **2a.1** Port `release-gate.yml` from Syntropic137. Triggers `pull_request: branches: [release]`. Inert until the branch exists.
- [ ] **2a.2** Repoint `build-workspace-images.yml`: `on: push: branches: [main]` becomes `branches: [release]`.
- [ ] **2a.3** Keep the `pull_request` trigger so images build and test on PRs without publishing.
- [ ] **2a.4** `:latest` moves only on a release push.
- [ ] **2a.5** Add `:edge` and/or `:sha` publishing from main for development images. **Do not skip.** Without this someone re-adds the main trigger and the gate is gone.

## Phase 2b: create and protect the branch

- [x] **2b.1** Confirm branch protection on `main`. ANSWERED 2026-08-17: **`main` is NOT protected** (404 "Branch not protected"). The only ruleset is "Copilot review for default branch" with `enforcement: disabled`. So today any push to main publishes and signs images with no review anywhere in the chain.
- [ ] **2b.2** Create `release` from main, AFTER 2a lands, so the branch carries the workflows.
- [ ] **2b.3** Protect `release`: require PR, require status checks, no direct push, no force-push, no deletion.
- [ ] **2b.4** **Required status checks, NOT required approvals.** GitHub does not count self-approval, so on a solo-maintainer repo required approvals locks the maintainer out of their own releases. The automated gate is the enforcement; the human is the merge click. Add required approvals when a second reviewer exists.

## Phase 2c: cut a release through the real flow

The plan originally had no step for actually cutting a release. This is that step, and it is
also the procedure Phase 5 documents.

```
1. bump version on main (agentic_isolation version + CHANGELOG entry)
2. open PR: main -> release
3. gate runs: version bumped vs release, changelog present, scans, docker dry-run
4. merge
5. push to release triggers build -> publish -> sign -> :latest moves
6. tag agentic-isolation/vX.Y.Z on release
```

Step 1 is what makes the gate meaningful: the version check compares against what is on
`release` and fails if the version was not bumped.

- [ ] **2c.1** Cut the next release through this exact flow, as the proof it works end to end.

## Phase 3: the release gate content

- [ ] **2.1** Confirm current branch protection state on `main` (could not be read on 2026-08-17, GitHub was returning 503s). This determines whether current exposure is larger or smaller than described above.
- [ ] **2.2** Create `release` from current main.
- [ ] **2.3** Branch protection on `release`: require PR, require review, require status checks to pass, no force-push, no deletion.
- [ ] **2.4** Repoint `build-workspace-images.yml`: `on: push: branches: [main]` becomes `branches: [release]`.
- [ ] **2.5** Keep the `pull_request` trigger so images are still built and tested on PRs without publishing.
- [ ] **2.6** `:latest` moves only on release. It is the tag consumers reach for by default; if it keeps tracking main the whole exercise leaks.
- [ ] **2.7** Add `:edge` or `:sha` publishing from main for development images. **Do not skip.** Without a way to get a fresh image mid-cycle, someone will quietly re-add the main trigger and the gate is gone.

## Phase 3: the release gate

Port from Syntropic137's `release-gate.yml`. Trigger on `pull_request: branches: [release]`.

- [ ] **3.1** `version-check`: all published package versions agree, and the version is bumped versus the release branch. **This is the control that makes a version number mean something.** Its absence is exactly how `agentic_isolation 0.4.0` came to describe two materially different packages (`requires-python` `>=3.10` vs `>=3.11`, and a new exact `pydantic` pin).
- [ ] **3.2** `changelog-check`: a release PR without release notes fails.
- [ ] **3.3** Vulnerability scanning: osv-scan and pip-audit, as Syn137 does.
- [ ] **3.4** `docker-dry-run`: build without publishing.
- [ ] **3.5** Do not add `release.published` as a trigger on publishing workflows. Direct release events bypass the approval gate. Syn137 documents this; keep the same property and the same comment explaining it.

## Phase 4: fix tag semantics (issue #304)

- [ ] **4.1** Image version tags must identify image contents, not a third-party CLI version. Replace the `ARG CLAUDE_CLI_VERSION` grep in `scripts/build-provider.py` (`extract_cli_version()`, around `:202-211`).
- [ ] **4.2** Applies to `claude-cli` as well as `omni-agent`; both have the defect today.
- [ ] **4.3** Lower urgency **only because** Phase 1 makes consumers pin digests. Still needed, because the next consumer will reach for a tag.

## Phase 5: documentation

Not optional and not a trailing task. The current state is under-documented in ways that already caused a real incident.

- [ ] **5.1** `docs/release-process.md` in agentic-primitives, mirroring Syn137's. Must state: what triggers a build, what triggers a publish, which tags move when, who approves, and how to cut a release start to finish.
- [ ] **5.2** Document the consumer contract explicitly: **pin digests, verify signatures, do not pin `:latest`.** State plainly that tags are mutable in OCI by design and that no release process makes a tag a guarantee.
- [ ] **5.3** Document the tag taxonomy: what `:latest`, `:edge`, `:<sha>`, `:<version>` each mean and which are safe to depend on.
- [ ] **5.4** Record the threat model table above, so the reasoning survives. Specifically that cosign keyless proves provenance, not review.
- [ ] **5.5** Update Syntropic137's docs where it describes how it obtains workspace images.
- [ ] **5.6** Note in the changelog convention that a `requires-python` change or a new dependency is a breaking change for a submodule consumer, since the pin carries it silently.

---

## Facts worth not re-deriving

- Syn137 consumes agentic-primitives two ways: the `lib/agentic-primitives` git submodule (Python libs) and GHCR images (workspace containers). **These version independently.** The submodule is currently pinned at `5744b86`; the credential-repr fix is `d31c88a` and the 0.5.0 release is `7089695`.
- Tag convention in agentic-primitives is `<component>/vX.Y.Z` (`sdlc/v1.4.2`, `observability/v0.3.7`). First library tag cut: `agentic-isolation/v0.5.0`.
- `agentic_isolation` never worked on Python 3.10 despite claiming `>=3.10`; the root imports `datetime.UTC` and `enum.StrEnum`. The `>=3.11` change is a metadata correction, not a withdrawal of support. Verified by building a wheel from `944e4b5` and installing on CPython 3.10.20.
- The credential-repr fix (`d31c88a`) covers `repr`, `str`, f-strings and nested reprs. `dataclasses.asdict` and `astuple` still expose values; the PR documents that boundary in a test rather than claiming full coverage.
- PR #323 (dependabot ruff bump) is failing `Python Logging` and was deliberately not merged. Note `gh pr checks` returned nothing for it while the status rollup showed the failure; trust the rollup.

## Open questions

- Branch protection state on `main` (blocked on GitHub availability, see 2.1).
- Whether `:latest` should continue to exist at all, or whether consumers should be forced onto digests by removing it. Removing it is safer and more disruptive.
- Whether the release gate should require a second human approver, or whether required review on the PR is sufficient for a team of this size.
