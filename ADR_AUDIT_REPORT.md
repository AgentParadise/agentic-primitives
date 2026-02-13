# ADR Audit Report - v3.1.2 Architecture Review

**Date:** 2026-02-12
**Version:** 3.1.2
**Objective:** Identify outdated ADRs from pre-v3.0 architecture rewrites

## Executive Summary

Out of 32 ADRs (excluding template 000):
- **REMOVE**: 18 ADRs (58%) - Describe deleted architecture
- **KEEP**: 12 ADRs (39%) - Still accurate
- **SUPERSEDED**: 1 ADR (3%) - ADR-032 (replaced by v3.x plugins)

**Total files to delete:** 19 ADRs (including 032 which was superseded)

---

## Full Audit Results

### ADRs to REMOVE (18)

| ADR | Title | Reason | Superseded By |
|-----|-------|--------|---------------|
| 001 | Staged Bootstrap Strategy | Rust CLI (`agentic-p`) removed, primitives build system gone | ADR-032 |
| 002 | Strict Validation from Start | Primitives validation system removed, plugins use Claude validation | — |
| 003 | Non-Interactive Scaffolding | `agentic-p new` command removed with Rust CLI | — |
| 006 | Middleware-Based Hook System | Middleware pipeline removed v1.2.0, replaced with self-logging | v1.2.0 self-logging |
| 007 | Generated Provider Outputs | Primitives build system removed | ADR-032, ADR-033 |
| 009 | Versioned Primitives | Per-file versioning removed, git-based now | ADR-032 |
| 010 | System-Level Versioning | `/primitives/v1/` `/primitives/v2/` structure removed | ADR-032 |
| 011 | Analytics Middleware | Already marked rejected in ADR itself | Self-logging (v1.2.0) |
| 012 | Wrapper-Impl Pattern | Two-file pattern replaced by atomic hooks | ADR-014 Rev 2 |
| 013 | Hybrid Hook Architecture | ADR marked superseded, `hooks-collector` removed | Self-logging |
| 017 | Hook Client Library | Never implemented, no `agentic-hooks` package or backend | — |
| 019 | File Naming Convention | Describes primitives naming, `.meta.yaml` files removed | ADR-032 |
| 021 | Primitives Directory Structure | Primitives structure removed | ADR-032 (explicit) |
| 023 | Universal Agent Integration Layer | Never implemented, packages planned for removal per ADR-033 | — |
| 024 | Documentation Philosophy | Fumadocs site removed, no `docs-site/` directory | — |
| 028 | Tool Permissions Config | `WorkspaceToolConfig` class never implemented | — |
| 031 | Auto-Generated Adapters | Never implemented, repo went to v3.x plugins instead | — |
| 032 | V2 Simplified Structure | `primitives/v2/` structure replaced by v3.x plugins | v3.x plugin architecture |

### ADRs to KEEP (12)

| ADR | Title | Reason | Status |
|-----|-------|--------|--------|
| 000 | ADR Template | Template for future ADRs | Template |
| 004 | Provider-Scoped Models | `providers/models/{provider}/` structure active | ✅ |
| 008 | Test-Driven Development | TDD principles still apply, pytest active | ✅ |
| 014 | Centralized Agentic Logging | `agentic_logging` package exists and is active | ✅ (update status to "accepted") |
| 015 | Parallel QA Workflows | `.github/workflows/qa.yml` matches architecture | ✅ |
| 016 | Hook Event Correlation | `tool_use_id` correlation actively implemented | ✅ |
| 018 | Model Registry Architecture | Three-tier registry active in `providers/models/` | ✅ |
| 020 | Agentic Prompt Taxonomy | Conceptual taxonomy still valid | ✅ |
| 022 | Git Hook Observability | Git hooks active in `plugins/sdlc/hooks/git/` | ✅ |
| 025 | Just Task Runner | `justfile` active at root | ✅ |
| 027 | Provider Workspace Images | Provider-based images foundational, extended by ADR-033 | ✅ |
| 029 | Simplified Event System | `agentic_events` package implements JSONL events | ✅ |
| 030 | Session Recording Testing | `SessionRecorder`/`SessionPlayer` fully implemented | ✅ |
| 033 | Plugin-Native Workspace Images | Current architecture, created today, implementation present | ✅ (proposed) |

---

## Breakdown by Architecture Era

### Pre-v3.0 (Primitives Era) - REMOVE ALL
- **001-003**: Bootstrap, validation, scaffolding for primitives
- **006**: Middleware pipeline
- **007**: Build system
- **009-010**: Versioning systems
- **012-013**: Hook architectures (superseded)
- **017**: Client library (never built)
- **019, 021**: Primitives file/directory structure
- **023**: Agent integration layer (never built)
- **024**: Docs site (removed)
- **028**: Tool permissions (never implemented)
- **031-032**: V2 transition architecture (superseded by v3.x)

### v3.x Plugin Era - KEEP
- **004**: Model registry
- **008**: TDD philosophy
- **014-016**: Logging, QA, event correlation
- **018**: Model registry architecture
- **020, 022**: Taxonomy, git hooks
- **025, 027**: Just, workspace images
- **029-030**: Events, session recording
- **033**: Plugin-native images (current)

---

## Implementation Plan

### Phase 1: Mark Superseded ADRs
Update frontmatter for ADRs that reference superseded decisions:

**ADR-005** (Polyglot Implementations):
```yaml
status: superseded
superseded_by: ADR-019 (File Naming), Simplified hook architecture
```

### Phase 2: Update Status for Active ADRs

**ADR-014** (Centralized Logging):
```yaml
status: accepted  # Currently says "superseded" but implementation exists
```

### Phase 3: Delete Obsolete ADRs (19 files)
Remove these files completely:
```
001-staged-bootstrap.md
002-strict-validation.md
003-non-interactive-scaffolding.md
006-middleware-hooks.md
007-generated-outputs.md
009-versioned-primitives.md
010-system-level-versioning.md
011-analytics-middleware.md
012-wrapper-impl-pattern.md
013-hybrid-hook-architecture.md
017-hook-client-library.md
019-file-naming-convention.md
021-primitives-directory-structure.md
023-universal-agent-integration-layer.md
024-documentation-philosophy.md
028-tool-permissions-config.md
031-tool-primitives-auto-generated-adapters.md
032-v2-simplified-structure.md
005-polyglot-implementations.md  # After marking superseded
```

### Phase 4: Update README
Change line 194 from:
```markdown
This project's design decisions are documented in [32 ADRs](docs/adrs/), including:
```

To:
```markdown
This project's design decisions are documented in [13 ADRs](docs/adrs/), including:
```

### Phase 5: Create Transition ADR (Optional)
Consider creating **ADR-034: V3 Plugin Architecture** to document the fundamental shift from primitives to plugins, capturing what ADR-032 attempted but was itself superseded.

---

## Risk Assessment

**Low Risk:**
- ADRs 001-003, 006-007, 009-013: Clear primitives architecture removal
- ADRs 017, 023, 024, 028, 031: Never implemented

**Medium Risk:**
- ADR-032: Recent (2026-01-14) but already obsolete
- ADR-005: Still partially relevant (Python + uv usage)

**Verification Needed:**
- Confirm ADR-005 can be fully removed (some polyglot patterns may still apply)
- Verify ADR-014 status change doesn't conflict with other references

---

## Post-Cleanup ADR Count

**Before:** 33 files (000 template + 32 ADRs, missing 026)
**After:** 14 files (000 template + 13 ADRs)
**Removed:** 19 files (58% reduction)

---

## Agent Reports Referenced

- Agent ace5f91: ADRs 001-006
- Agent a89a5fa: ADRs 007-012
- Agent aebe5b0: ADRs 013-018
- Agent a0e2e8b: ADRs 019-024
- Agent a1b358f: ADRs 025-030
- Agent ae83315: ADRs 031-033
