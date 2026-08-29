# Release process

How code in this repository becomes a container image somebody else can
depend on, and what a consumer has to do to depend on it safely.

`main` is the development branch. A protected `release` branch is the only
thing that publishes consumer-facing image tags. Everything below follows
from that one split.

The source of truth is `.github/workflows/`. This page describes what those
files do today; when the two disagree, the workflow is right and this page
is a bug.

---

## What triggers a build, and what triggers a publish

`.github/workflows/build-workspace-images.yml` is the only workflow that
pushes an image.

It runs on:

- **push to `main` or `release`**, filtered to the paths
  `providers/workspaces/**`, `workspace/**`, `plugins/**`, `lib/python/**`,
  and `scripts/build-provider.py`;
- **any pull request** touching those same paths, with no branch filter;
- **`workflow_dispatch`**, with an optional `tag` override and a `dry_run`
  boolean.

Building and publishing are separate questions:

| Event | Builds | Pushes | Channel |
|---|---|---|---|
| Pull request (any target) | yes | no | none |
| Push to `main` | yes | yes | `edge` |
| Push to `release` | yes | yes | `release` |
| `workflow_dispatch` with `dry_run: true` | yes | no | none |
| `workflow_dispatch` from `release` | yes | yes | `release` |
| `workflow_dispatch` from any other ref | yes | yes | `edge` |

A publish is additionally gated on the `integration-gate` job, which builds
`claude-cli` single-arch and runs `tests/integration` against the real
image. The `build-push` job declares `needs: [integration-gate]`, so a
failing integration suite blocks the push and the signature for every
provider in the matrix.

`release.published` is deliberately not a trigger. Cutting a GitHub Release
does not build anything.

## Which images are published

Two, both to GHCR under the `agentparadise` owner:

- `ghcr.io/agentparadise/agentic-workspace-claude-cli`
- `ghcr.io/agentparadise/agentic-workspace-interactive-tmux`

Those are the two entries in the workflow's build matrix, and
`.github/workflows/_check-version.yml` names the same pair as
`PUBLISHED_PROVIDERS`.

`providers/workspaces/base/` and `providers/workspaces/omni-agent/` are
buildable locally (`just build-provider omni-agent`) and are **not** pushed
to GHCR by any workflow on `main`. `omni-agent`'s manifest declares the
image tag `omni-agent-workspace`, which is a local build name today, not a
published one.

## Tag taxonomy

Every tag the workflow can apply, and whether a consumer may depend on it:

| Tag | Set when | Moves | Safe to depend on |
|---|---|---|---|
| `:latest` | push to `release` | on every release | **No.** A mutable pointer to whatever shipped last. |
| `:edge` | push to `main` | on every merged push to `main` | **No.** Development builds. Untested against a release gate. |
| `:<sha>` | any publish, on both channels | never in practice | Better, but still a tag. Prefer the digest. |
| `:<version>` | push to `release` only | never in practice | Better, but still a tag. This is the **provider manifest version** from `providers/workspaces/<provider>/manifest.yaml`, not the repo `VERSION` file. |
| `:<cli version>` | push to `release` only | when a release rebuilds the same bundled CLI | **No.** Two releases can bundle the same Claude CLI version, and the second one moves this tag. |
| `@sha256:<digest>` | always | never, by construction | **Yes. This is the only real pin.** |

`:latest` moving only on release makes it *less* wrong than it was. It does
not make it a pin. See the consumer contract below.

The image also carries the label `agentic.image.channel`, which is
`release`, `edge`, or `none`, alongside `agentic.provider.version` and
`agentic.cli.version`. Reading the label off a pulled image is how you find
out what you actually got.

## The release gate

`.github/workflows/release-gate.yml` runs on `pull_request` with
`branches: [release]`, so it grades exactly the PRs that promote `main` to
`release`. Seven jobs run, and a single required check named
`Release Gate` aggregates them:

| Job | Enforces |
|---|---|
| `version-check` | Every `lib/python/*` package whose non-test files changed versus `origin/release` has a strictly greater `project.version`. Every published provider whose own directory or a shared path (`workspace/`, `plugins/`, `lib/python/`, `scripts/build-provider.py`) changed has a greater `manifest.yaml` version. |
| `changelog-check` | The diff versus `origin/release` touches a `CHANGELOG.md`. |
| `docker-dry-run` | `claude-cli` and `interactive-tmux` both stage and build `linux/amd64` with `push: false`. The job holds `contents: read` and nothing else, so it cannot publish. |
| `workflow-changes` | The PR does not also modify `.github/workflows/`. See below. |
| `osv-scan` | OSV Scanner over every `lib/python/*/uv.lock` and the itmux `Cargo.lock`. |
| `pip-audit` | `pip-audit` over each Python package's exported, frozen requirements. |
| `dependency-review` | GitHub's dependency-review action on the PR diff. |

`version-check` and `changelog-check` fail closed: if `origin/release`
cannot be resolved, they error rather than pass.

There is no container-layer CVE scan. The scans above cover dependency
manifests only.

### The gate is currently editable by the PR it judges

Reusable workflows called from a `pull_request` event are evaluated from
the PR's own merge ref. A release PR that also edits `.github/workflows/`
therefore changes the rules being applied to it.

`_check-workflow-changes.yml` exists to catch that. It fails a PR into
`release` whose diff touches `.github/workflows/`, unless the PR carries the
label `ci-workflow-change`, in which case it emits a warning and passes.

**This is a speed bump, not an authorisation control.** Anyone who can
apply a label to the PR can clear it, and in a single-maintainer repository
that is the same person opening the PR. It buys a deliberate second look at
a combination that is easy to create by accident. It does not prevent
anything.

The correct control is `CODEOWNERS` on `.github/workflows/` plus a required
review from someone other than the author. That needs a second reviewer to
exist. Until then, the honest description of the current state is the one in
this section, and the workflow's own header says the same thing.

## Cutting a release

1. **Bump the version on `main`.** Bump the package version
   (`lib/python/<pkg>/pyproject.toml`) and/or the provider manifest version
   (`providers/workspaces/<provider>/manifest.yaml`) for whatever changed,
   and add the `CHANGELOG.md` entry describing what consumers receive.
2. **Open a PR from `main` into `release`.**
3. **Let the gate run:** version bumped versus `release`, changelog present,
   dependency scans, docker dry-run, no workflow changes riding along.
4. **Merge.**
5. **The push to `release` triggers the build**, which runs the integration
   gate, publishes, cosign-signs the digest, and moves `:latest`.
6. **Tag the component on `release`:** `<component>/vX.Y.Z`, matching the
   convention already in use (`agentic-isolation/v0.5.0`, `sdlc/v1.4.2`,
   `observability/v0.3.7`).

Step 1 happening on `main` rather than on the release PR is what lets
`version-check` compare `HEAD` against `origin/release` and see a
difference.

## Consumer contract

**Pin digests.** Resolve the tag once, record the digest, and reference
`ghcr.io/agentparadise/agentic-workspace-claude-cli@sha256:...` from then
on. Tags are mutable in OCI by design; `:latest` and `:edge` are
*intentionally* mutable, and even `:<sha>` and `:<version>` are only
immutable by convention.

```bash
IMAGE=ghcr.io/agentparadise/agentic-workspace-claude-cli
DIGEST=$(docker buildx imagetools inspect "${IMAGE}:latest" \
    --format '{{.Manifest.Digest}}')
echo "${IMAGE}@${DIGEST}"
```

**Verify the signature before you trust the digest.** Images are cosign
keyless signed on every publish, on both channels. The workflow signs with
a bare `cosign sign "${IMAGE}@${DIGEST}"` under `COSIGN_YES=true` and
ambient GitHub OIDC (`id-token: write`); it passes no identity flags of its
own, because the signing side does not choose the identity. Sigstore
derives it from the workflow's OIDC token, so the identity a consumer
verifies against is built from **this repository, this workflow file path,
and the branch ref that ran it**:

- workflow path: `.github/workflows/build-workspace-images.yml`
- repository: `AgentParadise/agentic-primitives`
- refs that publish: `refs/heads/main` (edge) and `refs/heads/release`
- OIDC issuer: GitHub Actions' token issuer

```bash
cosign verify "${IMAGE}@${DIGEST}" \
  --certificate-identity-regexp '^https://github\.com/AgentParadise/agentic-primitives/\.github/workflows/build-workspace-images\.yml@refs/heads/(main|release)$' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com'
```

Restrict the ref alternation to `release` if you only accept release
builds. The exact regexp is the consumer's to pin; this repository does not
publish one, and the values above are read off the workflow rather than
promised by it.

Because the identity includes the workflow's file path, **renaming or
moving `build-workspace-images.yml` breaks every consumer's verification.**
The workflow header carries that warning for the same reason.

**Signature does not mean reviewed.** Keyless signing proves "built by this
workflow from this repository". Edge images are signed exactly like release
images. The channel is carried by the tag and by the
`agentic.image.channel` label, never by the presence of a signature.

Builds also attach BuildKit provenance and SBOM attestations
(`provenance: true`, `sbom: true` on the push action).

## Two gotchas that already cost time

**Creating a branch does not trigger a path-filtered build.** A push that
creates a branch has no prior commit on that branch to diff against, so the
`paths:` filter matches nothing and the workflow does not run. Pushing a
first commit onto an existing branch does trigger it. If you need a build
from a fresh branch, push a commit after creating it, or use
`workflow_dispatch`.

**`release/*` branch names collide with the `release` branch.** Git stores
branches as files under `refs/heads/`, so `refs/heads/release` being a file
means `refs/heads/release/anything` cannot be created, and vice versa. With
a `release` branch in this repository, any `release/foo` branch name fails
with a lock or "cannot lock ref" error. Name release-related work branches
something else (`rel-`, `chore/release-`).

## Related

- [`.github/workflows/build-workspace-images.yml`](../.github/workflows/build-workspace-images.yml) - build, publish, sign
- [`.github/workflows/release-gate.yml`](../.github/workflows/release-gate.yml) - the gate
- [ADR-037: Release Integration Gate](adrs/037-release-integration-gate.md) - why the integration gate blocks publish
- [`CHANGELOG.md`](../CHANGELOG.md)
