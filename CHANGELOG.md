# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## Unreleased

### 🔁 omni-agent: exporter pinned to v0.3.0

The pinned `agentic-session-exporter` digest moves from v0.2.1 to v0.3.0.

**v0.2.1 recorded a refused transcript as sent.** Its uploader marked every
item in a successful batch as done, rejections included, so the next sweep
skipped the refused transcript as `skipped_unchanged` and reported success. One
transient rejection became permanent silent absence from the store. The solo
retry path had the same bug, and is the likelier route since it is the fallback
for a batch that already failed.

v0.3.0 marks only what the store confirmed, counts what it did not
(`unconfirmed`), and scopes its state to the store so repointing at a new one
re-sends rather than skipping everything.

**Exit 3 is new and is a behaviour change**: a sweep that ran without capturing
everything it found no longer exits 0. `finalize.sh` was taught about it first
(see the entry above), so a partial capture is reported as INCOMPLETE rather
than as a total upload failure.


### 🔁 omni-agent: exporter pinned to v0.2.1

The pinned `agentic-session-exporter` digest moves from v0.1.1 to v0.2.1.

**The glibc floor recorded under omni-agent 1.1.0's "Known limit" is resolved
upstream.** The exporter's Linux binaries are statically linked against musl
now, so they carry no libc floor rather than one that happened to sit above
Debian 12. That entry is left as-is: it describes what 1.1.0 actually shipped,
and rewriting it would make a released version look like it contained a fix it
did not.

Only `apss-session-exporter` is still copied, but the reason has changed. It
was infeasible to copy `apss-session-reconstitute` before, because it could not
run on this base. Now it simply is not needed: resuming a stored session is
something a developer does on their own machine, not something a short-lived
workspace container ever does.

**Sessions captured with the default origin were out of spec.** v0.1.1
defaulted `origin.environment` to `laptop`, which is not one of the four
classes APS-V1-0004 s4.2.1 defines (`local`, `vps`, `container`, `workflow`).
v0.2.1 detects the class and refuses an out-of-enum value at startup instead of
writing it.

Do not pin v0.2.0: its Linux binaries require glibc 2.39 and cannot run here.

## [Unreleased]

### ✨ The omni workspace image now ships the session-store exporter

`omni-agent` 1.1.0.

Until now the image shipped no exporter binary at all, so the session-store
capability's `exporter_present` check could never pass. Session capture was
impossible rather than merely unconfigured, and enabling it hard-failed the
workspace.

The image previously refused to bake one on purpose: the only client available
was named for a single vendor's store, and embedding it would have coupled a
general-purpose multi-agent workspace image to that company's product. That
client has since been extracted and published as the public reference
implementation of the APS-V1-0004 Exporter profile, so the image now depends on
a public client of a public contract instead.

**What consumers receive**

- `apss-session-exporter` at `/usr/local/bin`, copied `FROM` a signed OCI image
  by digest. CI verifies that digest's cosign signature **before** the build, so
  a build cannot start against an unverified artifact. A digest establishes
  which bytes; the signature establishes who published them.
- `AGENTIC_SESSION_STORE_DEPLOYMENT` in the capability contract, translated to
  `SESSION_STORE_ORIGIN_DEPLOYMENT`. This is what makes APS-V1-0004 2.0.0's
  `origin.deployment` reachable from a workspace. Without it every containerised
  session reports the same runtime class and a multi-tier install is
  unattributable.
- `/spool` and `/var/agentic` are writable under `--read-only`, so a capability
  that writes can actually run in the production security configuration.
- The capability doctor reports its real failure cause. It previously printed
  `doctor: FAIL` for a doctor that never executed, because a swallowed `mkdir`
  under `errexit` killed the entrypoint before the check ran.

**Behaviour change for existing deployments**

An operator bind-mounting `SeshMagicSessionExporter` will find the baked
`apss-session-exporter` now takes precedence, because the capability resolves
the standard-anchored name first. Capture keeps working - it is the same
reference client - but the mounted build is no longer the one that runs. Set
`AGENTIC_SESSION_STORE_EXPORTER_BIN` to keep using a specific binary. This is
why the provider bump is a minor rather than a patch.

**Known limit**

The exporter's release binaries are built against glibc 2.39 while this image is
Debian 12 (2.36). `apss-session-exporter` runs because it happens not to
reference a 2.39 symbol; `apss-session-reconstitute` does, so only the exporter
is copied. The build now executes the copied binary per target platform, which is
what surfaced this, so the failure mode is a failed build rather than a broken
workspace. Upstream fix tracked as agentic-session-exporter#7.

`claude-cli` is unchanged and deliberately still ships no exporter.


### 🔒 Security: pytest and pygments advisories

`agentic-events` 0.1.1, `agentic-isolation` 0.5.1, `agentic-logging` 0.1.2.

Two advisories surfaced by the release gate's dependency audit on its first
run, both in development dependencies rather than in shipped runtime code:

| Package | Was | Advisory | Now |
|---|---|---|---|
| pytest | 9.0.2 | PYSEC-2026-1845 | 9.1.1 |
| pygments | 2.19.2 | PYSEC-2026-2987 | 2.21.0 |

`agentic-memory` and `agentic-session-store` already carried fixed versions
and are unchanged.

### 🐳 omni-agent is published

`omni-agent` enters the image build matrix and is published as
`omni-agent-workspace` for the first time. It has existed as source since the
capability work but was never built by CI, so the image did not exist in the
registry.

This also makes `test_omni_hosts_the_shared_capability_runtime` run. That test
was guarded on the omni image being available and had therefore silently
skipped in CI since it was written, despite being the only test that checks
whether the ADR-040 section 12 image contract holds for a second image.

`omni-agent` is added to the release gate's published-provider list and to the
docker dry-run matrix, without which a release could ship changed omni content
under an unchanged image tag.

### 📚 Documentation

Documentation synced with the capability system and the two-channel release
process, net -697 lines. New `docs/release-process.md`. Two corrections worth
naming: the `.capture-env` parse was documented as a raw line when the file
holds `SESSION_STORE_TAGS_B64=<base64>`, so the documented parse silently
produced no tags, and the session-store doctor has six checks rather than the
five documented.

### 📦 agentic-isolation 0.5.0 (BREAKING)

`agentic-isolation` is bumped `0.4.0` to `0.5.0`. This is the release note for
everything that reached a consumer between commit `944e4b5` and `d31c88a`.

Read this first if you consume this repo as a git submodule pinned to a raw
commit. The package version did **not** change across that range while the
package's Python floor, its dependency list, and the workspace image's PID 1
behaviour all did, so "0.4.0" names two materially different packages depending
on when you pulled. The bump exists to make that distinguishable. The project is
pre-1.0, so a minor bump is the SemVer-sanctioned way to carry breaking changes,
but they are breaking and are listed as such below.

#### Breaking Changes

**1. `requires-python` moved `>=3.10` to `>=3.11`.**

Committed in `bcef534`. The classifier list dropped
`Programming Language :: Python :: 3.10` in the same change, and `[tool.mypy]`
`python_version` moved to `3.11`.

Read the change as a metadata correction rather than a withdrawal of working
support. At `944e4b5` the package advertised `>=3.10` and installed on 3.10, but
the package root already failed to import there: `agentic_isolation.providers.base`
imports `datetime.UTC` (3.11+) and `agentic_isolation.providers.claude_cli.types`
declares `EventType(enum.StrEnum)` (3.11+), both on the unconditional root import
path. Verified: `import agentic_isolation` on CPython 3.10.20 against a wheel
built from `944e4b5` raises
`ImportError: cannot import name 'UTC' from 'datetime'`.

What changes for you: on 3.10 the failure moves from import time to install
time. `0.5.0` refuses to resolve on 3.10 instead of installing and then failing
on first import. If you are on 3.10, upgrade to 3.11 or later. There is no
version of this package on either side of this range that works on 3.10.

**2. A previously dependency-free package now has a hard, exactly pinned
dependency.**

`dependencies` moved from `[]` to exactly one entry, `pydantic==2.13.4`. The pin
is exact, not a range, so it will conflict with any environment holding a
different pydantic 2.x. The `docker` extra (`docker>=7.0.0`) is unchanged and
still optional.

The dependency is not needed by the isolation API this package exports. Nothing
reachable from `import agentic_isolation` imports pydantic; only the run-contract
modules do (`agent_run_spec`, `agent_run_result`, `agent_run_events`,
`run_client`, `workspace_run`, `recipe`, `itmux_client`), and none of those are
re-exported from the package root. Verified: installing the `0.5.0` wheel with
`--no-deps` into a pydantic-free 3.12 environment leaves `import agentic_isolation`
working, while `import agentic_isolation.agent_run_spec` raises
`ModuleNotFoundError: No module named 'pydantic'`.

If the exact pin is a problem for you and you do not use the run contract, you
can install with `--no-deps` today. That is an observation about the current
import graph, not a supported contract.

**3. The workspace entrypoint changed PID 1 semantics, then changed back.**

Affected range: exactly one commit, `c56b9eb`. Introduced there, fixed in
`5744b86`, which is its immediate successor. If your pin is `c56b9eb`, you are
affected. If your pin is `5744b86` or later, or `944e4b5` or earlier, you are
not.

At `c56b9eb` the capability runtime wrapped `CMD` unconditionally so that
`finalize.sh` hooks could run after the agent exits. It wrapped even when no
capability was enabled and no finalizer existed, which cost a consumer who opted
into nothing two things:

- **PID 1.** With `AGENTIC_CAPABILITIES=""` the command ran as a child of the
  entrypoint shell rather than as PID 1.
- **Docker's stop grace.** The wrapper's own bounded wait is
  `__TERM_GRACE_TICKS=15` iterations of `sleep 0.1`, so it escalated to SIGKILL
  1.5 seconds after being signalled regardless of `docker stop -t`. A command
  that trapped SIGTERM to flush for longer than that was killed mid-flush and
  the container exited 137 instead of the command's own status.

`5744b86` restores `exec "$@"` when no finalizer would run, and wraps only when
there is post-agent work. Both answers come from one discovery function so the
two notions of "active capability" cannot drift. The wrapper path itself is
unchanged.

#### Added

- **Workspace capability modules** (`c56b9eb`, ADR-040). A named capability
  registry driven by `AGENTIC_CAPABILITIES` (space separated, image default
  `"memory session-store"`), with a three-hook lifecycle per capability
  adapter: `init.sh` is sourced before the agent starts (entrypoint 5.6),
  `doctor` runs as preflight (5.7), and `finalize.sh` runs after the agent
  exits (section 6). Adding a capability is a directory plus a registry entry,
  with no entrypoint edit. Memory is the migrated first instance and
  session-store is the second. The breaking path and env-var renames that came
  with this are documented in the ADR-040 section below, which is part of the
  same unreleased range.
- **Harness-neutral `workspace/` runtime** (`c56b9eb`). The entrypoint and the
  capability adapters moved out of the Claude-specific provider tree to
  `workspace/entrypoint.sh` and `workspace/capabilities/<capability>/<provider>/`,
  and are staged into every image at `/opt/agentic/`. The ADR-040 section
  below still cites the old
  `providers/workspaces/claude-cli/capabilities/session-store/` path; the
  runtime is now shared rather than per-harness.
- **`omni-agent-workspace` image** (`c56b9eb`,
  `providers/workspaces/omni-agent/`). A single workspace image hosting both
  the Claude CLI and the Codex CLI on the shared capability runtime, manifest
  `omni-agent` 1.0.0, image tag `omni-agent-workspace`. It contributes no
  capability code of its own. Its `otel_native: true` describes the default
  harness (claude) only; Codex's OTel support is not exercised here.
- **`agentic_session_store` Python package** (`c56b9eb`,
  `lib/python/agentic_session_store/`): the `AGENTIC_SESSION_STORE_*` contract,
  a five-check doctor, and env-name conformance tests.

#### Fixed

- **`WorkspaceConfig` no longer prints credentials when rendered** (`d31c88a`).
  `secrets` and `environment` are now `field(..., repr=False)`, so neither
  appears in `repr()`, `str()`, an f-string, or `"{}".format(...)`, and by
  extension not in the repr of anything that embeds a `WorkspaceConfig`. Both
  fields are covered, not just `secrets`: `environment` is the field a
  capability credential such as `AGENTIC_SESSION_STORE_AUTH` actually travels
  in, and before this change moving a secret into `secrets` was a mitigation
  that did nothing because that field had the identical exposure.

  Stated limit, with a test recording it: `repr=False` does not affect
  `dataclasses.asdict`, which still returns the values, and the same is true of
  `astuple`. Anything serialising a config for output must still redact for
  itself. Field access is unchanged, so no caller behaviour changes.

#### Notes

- `agentic_isolation.__version__` is bumped alongside `pyproject.toml`, and both
  `uv.lock` files that pin the package are regenerated so the repo's
  `uv sync --locked` gate stays green. No other file changes.
- No tag is cut by this change. Preparing the release is separate from cutting
  it.

---

### 🧩 Workspace Capability Modules (ADR-040, BREAKING)

Generalizes ADR-036's memory-only adapter mechanism into a named capability
registry, and adds session capture as its second instance. Workspace image
manifest moves **1.3.0 to 2.0.0**.

#### Breaking Changes

| # | Was | Is | What the operator must do |
|---|---|---|---|
| 1 | `/opt/agentic/memory/doctor` | `/opt/agentic/capabilities/memory/doctor` | Update any script, healthcheck, or runbook that invokes the memory doctor by path. Adapter paths move too: `/opt/agentic/memory/<provider>/init.sh` becomes `/opt/agentic/capabilities/memory/<provider>/init.sh`. |
| 2 | `AGENTIC_MEMORY_AUDIT_DIR` | `AGENTIC_CAPABILITY_AUDIT_DIR` | Rename the variable wherever it is set. It is now capability-generic: it overrides the audit directory for every capability, not just memory. The per-capability default is still `/var/agentic/<capability>-doctor`, so hosts relying on the default path need no change. |
| 3 | `AGENTIC_MEMORY_PROVIDER` alone activated memory | Memory must also be listed in `AGENTIC_CAPABILITIES` (default `"memory session-store"`) | No action if the image default is accepted. If `AGENTIC_CAPABILITIES` is set explicitly, it must include `memory` or memory silently stops running. **This failure is silent**: the workspace starts cleanly with memory quietly inactive. The entrypoint warns on stderr at startup when it detects a `*_PROVIDER` var with no matching registry entry, but nothing hard-fails. |

See [ADR-040](docs/adrs/040-workspace-capability-modules.md) for the full
migration table and rationale.

#### Added

- **Capability registry**: `AGENTIC_CAPABILITIES` (space-separated) drives entrypoint sections 5.6/5.7 generically; a new capability is a directory plus a registry entry, no entrypoint edit required.
- **Session capture as a capability**: `providers/workspaces/claude-cli/capabilities/session-store/` uploads agent transcripts to a session store speaking APS-V1-0004, with the SeshMagic exporter as the shipped adapter.
- **`agentic_session_store`** Python package (`lib/python/agentic_session_store/`): contract, doctor, and env-name conformance following the same shape `agentic_memory` established.

---

### 🏗 Workspace Injection Contract (ADR-035)

A small, cross-orchestrator file-injection seam that any consumer of the workspace image (agentic-domain-runner, Syntropic137, future Codex/Gemini wrappers) can target.

#### Added

- **Workspace entrypoint section 5.5** — `providers/workspaces/claude-cli/scripts/entrypoint.sh` now reads a read-only bind-mount at `/etc/agentic/workspace/` plus three optional env vars (`AGENTIC_WORKSPACE_CONTEXT`, `AGENTIC_WORKSPACE_PLUGINS`, `AGENTIC_WORKSPACE_AGENTS`) and copies content into the agent-visible workspace:
  - `CLAUDE.md` → `/workspace/CLAUDE.md` (chmod 600)
  - `plugins/<name>/` → `/workspace/.agentic-plugins/<name>/` + appends `--plugin-dir` flags to `AGENTIC_PLUGIN_FLAGS`
  - `agents/<name>.md` → `~/.claude/agents/<name>.md`
- **`WorkspaceFiles` Python helper** — `lib/python/agentic_isolation/agentic_isolation/workspace_files.py`. Exposes `bind_mount(host, ctr, read_only)` and `inject(container_id, ctr_path, content)` as the two complementary staging primitives. Library import only — no daemon. Exported from `agentic_isolation` package root.
- **Canonical docs**: [`docs/workspace.md`](docs/workspace.md) describes the workspace's three responsibilities (inject / isolate / observe); [ADR-035](docs/adrs/035-workspace-injection-contract.md) captures the decision; `docs/superpowers/specs/` + `docs/superpowers/plans/` hold the design + implementation plan.
- **7 integration tests** in `tests/integration/test_entrypoint_workspace_injection.py` covering CLAUDE.md copy, plugin copy + flag append, loose subagent copy, env filter, no-mount skip, invalid-plugin skip, plugin-flags append-not-replace.
- **5 unit tests** for `WorkspaceFiles` (descriptor shape, relative-path resolution, `put_archive` call shape, ValueError on non-absolute / empty-basename `container_path`).
- **docs/issues/** convention introduced — numbered enhancement / follow-up notes (003 cosmetic items captured).

#### Notes

- Backwards compatible: when `/etc/agentic/workspace/` isn't bind-mounted, section 5.5 is a silent no-op.
- Tool restrictions live inside subagent frontmatter (`tools: [...]`) or plugin permission settings, NOT in a separate workspace-contract env var — see ADR-035 alternative #3.
- Sibling consumer (the [agentic-domain-runner](https://gitea.neuralempowerment.xyz/HomeLab/agentic-domain-runner)) renames its `AGENTIC_DOMAIN_*` env vars to `AGENTIC_WORKSPACE_*` in a coordinated branch.

---

### 🎯 Agentic Prompts & Smart Sync

Major additions for prompt primitives and improved install workflow.

### Added

- **Prompt primitives**: New prompt types with full taxonomy
  - `commands/` - Task execution prompts (e.g., `/review`, `/pre-commit-qa`, `/qa-setup`)
  - `meta-prompts/` - Prompt generators (e.g., `/create-prime`, `/create-doc-sync`, `/prompt-generator`)
  - `agents/` and `skills/` - Directory structure for future expansion

- **Manifest-based smart sync**: `build` and `install` commands now track managed files
  - `.agentic-manifest.yaml` generated during build with primitive metadata
  - Install shows sync preview (new/updated/unchanged primitives)
  - **Local files preserved** - files not in manifest (e.g., generated `/doc-sync`) are not overwritten

- **Per-project configuration**: `agentic.yaml` for version overrides
  - `agentic-p config init` - Generate config template (tsconfig-style with commented options)
  - `agentic-p config show` - Display current configuration
  - `agentic-p config list` - List available primitives

- **agentic_settings package**: Centralized configuration management
  - Pydantic-settings based API key management
  - Auto-discovery of `.env` files
  - Type-safe settings with validation

### Changed

- Build command now outputs manifest for tracking installed primitives
- Install command uses manifest diff to only update changed files
- Prompt frontmatter uses model aliases (e.g., `sonnet`) instead of explicit versions

### Fixed

- **Claude CLI attribution in commits**: Updated `.claude/settings.json` format per official docs
  - Changed to `attribution: {commit: "", pr: ""}` (empty strings disable attribution)
  - Fixes issue where "Generated with Claude Code" and Co-Authored-By attribution appeared in commits
  - Added regression test (`test_claude_cli_attribution.py`) to validate attribution is disabled
  - See: https://code.claude.com/docs/en/settings#attribution-settings

---

## [1.2.0] - 2025-11-26

### 🔄 Self-Logging Hooks Architecture

Major refactoring of the analytics architecture from centralized hooks-collector to self-logging hooks.

### Added

- **agentic-analytics library**: New Python client library for hook decision logging
  - `AnalyticsClient` for logging to JSONL files and/or API endpoints
  - `HookDecision` dataclass for standardized decision tracking
  - Validation utilities for E2E testing of analytics events
  - DI-friendly configuration via environment variables or constructor

- **Provider configurations**: Added missing `config.yaml` files for Google and OpenAI model providers

### Changed

- **Security hooks now self-log**: `bash-validator`, `file-security`, and `prompt-filter` hooks now log decisions directly via `AnalyticsClient`
- **Rust CLI ModelConfig**: Updated to match actual YAML file format used in model definitions
- **Hook scaffold template**: Fixed YAML indentation in generated hook files
- **Claude transformer tests**: Updated to use new `.claude/settings.json` structure

### Removed

- **hooks-collector**: Removed centralized hooks-collector infrastructure (superseded by self-logging pattern)
- **Middleware pipeline**: Simplified architecture removes complex middleware orchestration

### Architecture

- ADR-013 (Hybrid Hook Architecture) marked as superseded
- Each hook now directly logs its decisions, eliminating middleware complexity
- Enables easier dependency injection of analytics backends

---

## [1.0.0] - 2025-11-15

### 🎉 Initial Release - Production Ready

The first production-ready release of Agentic Primitives, a complete framework for managing atomic AI agent components with industrial-grade validation, versioning, and multi-provider support.

### Added

#### Core CLI Commands (10/10)
- **`init`** - Initialize new primitives repository with scaffolding
- **`new`** - Create new primitives from templates (agents, commands, skills, meta-prompts, tools, hooks)
- **`validate`** - Three-layer validation system (structural, schema, semantic)
- **`list`** - Discover and list all primitives with filtering
- **`inspect`** - Detailed primitive information and metadata
- **`version`** - Version management (bump, list, promote, deprecate)
- **`migrate`** - Cross-version migration support
- **`build`** - Transform primitives to provider-specific formats
- **`install`** - Deploy built outputs to project or global locations
- **`test-hook`** - Local hook testing with mock events

#### Validation System
- **Structural validation**: Directory structure, required files, naming conventions
- **Schema validation**: JSON schema validation against versioned specs
- **Semantic validation**: Cross-references, version integrity, hash verification
- BLAKE3 hashing for content integrity
- Kebab-case naming enforcement
- Comprehensive error messages with actionable suggestions

#### Versioning System
- System-level versioning for architectural shifts (`/v1/`, `/v2/`)
- Prompt-level versioning with hash validation
- Version status management (draft, active, deprecated)
- Immutable version content with BLAKE3 hashes
- Version promotion and deprecation workflows
- Migration support between system versions

#### Provider Support
- **Claude**: Full support for Claude Agent SDK format
  - Transform prompts to `.claude/agents/`, `.claude/commands/`
  - Tool transformations with MCP bindings
  - Hook middleware orchestration
- **OpenAI**: Full support for OpenAI API format
  - Function calling transformations
  - System/user prompt formatting
  - Tool schema conversions

#### Primitive Types

##### Prompt Primitives
- **Agents**: Personas and roles with context usage preferences
- **Commands**: Discrete tasks with input/output specs
- **Skills**: Knowledge overlays and pattern libraries
- **Meta-Prompts**: Prompt generators for bootstrapping new primitives

##### Tool Primitives
- Logical tool specifications (provider-agnostic)
- Provider-specific implementations (Claude MCP, OpenAI functions, local Rust/Python/Bun)
- Safety constraints (runtime limits, working directory, write permissions)
- Argument validation and type checking

##### Hook Primitives
- Lifecycle event handlers (PreToolUse, PostToolUse, etc.)
- Middleware pipeline architecture:
  - **Safety middleware**: Blocking, fail-fast validation
  - **Observability middleware**: Non-blocking, parallel execution
- Python (uv) and Bun runtime support
- Decision-based control flow (allow, deny, modify)

#### Build & Install System
- Streaming transformation pipeline for memory efficiency
- Provider-native output generation
- Project-local installation (`.claude/`, `.openai/`)
- Global installation (`~/.claude/`, `~/.openai/`)
- Automatic backup with timestamping
- Dry-run mode for safety
- Type and kind filtering

#### Templates
- Handlebars-based template system
- Templates for all primitive types
- Consistent YAML structure generation
- Schema-compliant output
- Proper indentation and formatting

#### Testing
- **302 tests passing** (204 unit + 98 integration)
- E2E integration tests for full lifecycle
- Performance benchmarks with criterion.rs
- Cross-version compatibility tests
- Provider transformation validation
- Error handling coverage
- Test fixtures for all primitive types

#### Documentation
- Comprehensive README with quick start
- Architecture documentation with diagrams
- Versioning guide with best practices
- Getting started tutorial
- 10 Architecture Decision Records (ADRs):
  - ADR-001: Staged Bootstrap Strategy
  - ADR-002: Strict Validation
  - ADR-003: Non-Interactive Scaffolding
  - ADR-004: Provider-Scoped Models
  - ADR-005: Polyglot Implementations
  - ADR-006: Middleware-Based Hooks
  - ADR-007: Generated Provider Outputs
  - ADR-008: Test-Driven Development
  - ADR-009: Versioned Primitives
  - ADR-010: System-Level Versioning

#### Repository Structure
- Organized primitive storage (`primitives/v1/`)
- Versioned JSON schemas (`specs/v1/`)
- Provider configuration and models
- Experimental sandbox for v2+ testing
- Clean separation of concerns

#### Developer Experience
- Makefile for turnkey operations
- Automated formatting (Rust + Python)
- Linting with clippy and ruff
- Type checking with mypy
- QA checkpoint automation
- Git hooks support

### Technical Details

#### Dependencies
- **Rust**: 1.75+ with modern features
- **Key Crates**: clap, serde, anyhow, thiserror, walkdir, blake3, chrono, dirs, criterion
- **Python**: 3.11+ with uv for fast dependency management
- **Node**: Bun for TypeScript/JavaScript hook implementations

#### Performance
- Streaming transformations for large primitive sets
- Efficient directory traversal
- Parallel test execution
- Benchmarked critical paths (validation, build)

#### Quality Metrics
- 302 tests with >90% coverage
- Zero clippy warnings
- Full type safety (Rust + Python)
- Schema validation for all YAML
- Consistent error handling with anyhow/thiserror

### Breaking Changes
None - this is the initial release.

### Migration Guide
None - this is the initial release.

### Known Issues
None - all tests passing, production ready.

### Contributors
- Built with love for the AI agent community 🤖

---

## [1.1.0] - 2025-11-15

### 🚀 Phase 2: CI/CD & Distribution

Complete CI/CD pipeline with automated testing, releases, security audits, and universal installation system.

### Added

#### GitHub Actions Workflows
- **CI Workflow** (`.github/workflows/ci.yml`)
  - Multi-OS testing (Ubuntu, macOS, Windows)
  - Format checking with `cargo fmt`
  - Linting with clippy (zero warnings)
  - Fixture validation
  - Code coverage with codecov
  - Triggers on PRs and pushes to main

- **Release Workflow** (`.github/workflows/release.yml`)
  - Automated releases on version tags
  - Multi-platform binary builds (Linux x64/ARM64, macOS x64/ARM, Windows x64)
  - SHA256 checksum generation
  - GitHub Release creation with binaries
  - Optional crates.io publishing

- **Security Workflow** (`.github/workflows/security.yml`)
  - Weekly cargo audit for vulnerability scanning
  - Dependency review on PRs
  - SBOM (Software Bill of Materials) generation
  - Automated security reporting

- **Benchmarks Workflow** (`.github/workflows/benchmarks.yml`)
  - Weekly performance benchmarking
  - Baseline comparison tracking
  - Regression detection
  - Performance trend reporting

#### Installation System
- **Universal Install Script** (`scripts/install.sh`)
  - One-line installation: `curl -fsSL ... | sh`
  - OS/architecture auto-detection
  - GitHub Release binary download
  - SHA256 checksum verification
  - Automatic PATH integration
  - Version selection support
  - Clean uninstall option

- **Bootstrap Script** (`scripts/bootstrap.sh`)
  - One-command repository setup
  - Automatic CLI installation
  - Stack detection (Python, TypeScript, React, NestJS, TurboRepo, Rust)
  - Stack-specific primitive installation
  - `.gitignore` configuration
  - Optional git hook setup
  - Composable integration for any tech stack

#### Stack Presets
Pre-configured primitive sets for popular stacks:
- **Python** (`scripts/stacks/python.yaml`)
  - UV-based tooling hooks
  - Python testing agents
  - Code quality commands
- **TypeScript** (`scripts/stacks/typescript.yaml`)
  - Bun runtime support
  - TS linting hooks
  - Type checking agents
- **React** (`scripts/stacks/react.yaml`)
  - Component generation agents
  - React hooks validation
  - UI best practices skills
- **NestJS** (`scripts/stacks/nestjs.yaml`)
  - API endpoint agents
  - Dependency injection hooks
  - Service scaffolding commands
- **TurboRepo** (`scripts/stacks/turborepo.yaml`)
  - Monorepo management agents
  - Workspace coordination hooks
  - Build orchestration commands
- **Rust** (`scripts/stacks/rust.yaml`)
  - Cargo integration hooks
  - Rust best practices agents
  - Safety validation commands

#### Documentation
- **CI/CD Guide** (`docs/ci-cd.md`)
  - Workflow architecture
  - Trigger conditions
  - Badge integration
  - Troubleshooting guide
- **Release Process** (`docs/release-process.md`)
  - Version bumping workflow
  - Release checklist
  - Rollback procedures
  - Distribution channels
- **Security Policy** (`docs/security.md`)
  - Vulnerability reporting
  - Security audit schedule
  - Dependency management
  - SBOM usage

#### Validation & Quality
- Stack preset validation script (`scripts/validate-stacks.sh`)
- Bash script syntax validation
- YAML workflow validation with yamllint
- All 302 tests continue to pass

### Improvements
- **Code Quality**: Fixed remaining clippy warnings
  - Replaced `vec![]` with array `[]` for static lists
  - Simplified identical if blocks
  - Improved code clarity

### Breaking Changes
None - fully backward compatible with v1.0.0.

### Migration from v1.0.0
No migration needed - drop-in replacement. Simply:
```bash
curl -fsSL https://raw.githubusercontent.com/AgentParadise/agentic-primitives/main/scripts/install.sh | sh
```

### Contributors
Built with ❤️ for the AI agent community 🤖

---

## [Unreleased]

### Planned Features
- Homebrew formula for macOS installation
- Chocolatey package for Windows
- Docker images for containerized usage
- VSCode extension for primitive development
- Web-based primitive explorer
- Community primitive registry

---

**Legend**:
- 🎉 Major milestone
- ✨ New feature
- 🐛 Bug fix
- 📚 Documentation
- ⚡ Performance
- 🔒 Security
- ♻️ Refactoring
- 🧪 Testing
- 🎨 UI/UX
