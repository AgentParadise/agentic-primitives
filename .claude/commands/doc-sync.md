# /doc-sync - Documentation Synchronization

Review recent commits and ensure documentation is synchronized with code changes.

## Step 1: Analyze Recent Changes

First, review what has changed recently:

```bash
git log --oneline -15
git diff HEAD~5 --stat
```

Focus on changes to these key areas:

| Code Area | Watch For |
|-----------|-----------|
| `cli/src/commands/` | New CLI commands, changed options |
| `cli/src/providers/` | Provider transformer changes |
| `primitives/v1/prompts/` | New prompts, structure changes |
| `primitives/v1/hooks/` | Hook changes |
| `specs/v1/` | Schema changes |
| `lib/python/` | Python package updates |

## Step 2: Map Changes to Documentation

Based on what changed, identify which docs need updates:

| Change Type | Documentation to Update |
|-------------|------------------------|
| New CLI command | `README.md` (Quick Start), `cli/README.md`, `docs/getting-started.md` |
| New primitive type | `README.md` (Core Concepts), `docs/architecture.md` |
| New prompt primitive | `docs/getting-started.md`, verify with `agentic-p config list` |
| Schema changes | `docs/versioning-guide.md`, relevant ADR |
| Hook changes | `docs/hooks/`, `docs/architecture/hooks-system-overview.md` |
| Analytics changes | `docs/analytics-*.md` files |
| Provider changes | `providers/*/README.md` |
| Breaking changes | `CHANGELOG.md`, relevant ADR |

## Step 3: Documentation Checklist

### Core Documentation

- [ ] **README.md** - Main entry point
  - Quick Start section current?
  - Core Concepts accurate?
  - CLI commands list complete?
  - Repository structure diagram accurate?

- [ ] **CHANGELOG.md** - Version history
  - New features documented?
  - Breaking changes noted?
  - Version number correct?

- [ ] **cli/README.md** - CLI reference
  - All commands listed?
  - Module descriptions accurate?

### Guide Documentation

- [ ] **docs/getting-started.md**
  - Installation steps work?
  - Examples run correctly?
  - New features covered?

- [ ] **docs/versioning-guide.md**
  - CLI commands accurate?
  - Workflows still valid?
  - Config options documented?

- [ ] **docs/architecture.md**
  - Diagrams current?
  - Component descriptions accurate?

### Specialized Documentation

- [ ] **docs/hooks/** - If hooks changed
- [ ] **docs/analytics-*.md** - If analytics changed
- [ ] **docs/examples/** - If new examples needed

### ADRs (Architecture Decision Records)

Check if any changes warrant a new ADR:

```bash
ls docs/adrs/
```

Current ADRs: 000-016 (template through hook-event-correlation)

Consider new ADR if:
- Significant architectural decision made
- New pattern established
- Breaking change introduced

## Step 4: Verify Synchronization

### Quick Verification

```bash
# Build succeeds
cargo build --manifest-path cli/Cargo.toml

# All primitives valid
agentic-p validate primitives/v1/

# Config list shows all primitives
agentic-p config list
```

### Documentation Consistency

- [ ] Version numbers match across: `Cargo.toml`, `CHANGELOG.md`, `README.md`
- [ ] CLI command examples actually work
- [ ] File paths in docs exist
- [ ] Links are not broken

### Code Examples

Test any code examples in documentation:

```bash
# Test CLI commands from README
agentic-p --help
agentic-p config init --help
agentic-p build --help
```

## Step 5: Update Procedure

For each doc that needs updating:

1. **Read** the current content
2. **Identify** specific sections to update
3. **Edit** with minimal, focused changes
4. **Verify** the update is accurate

### Commit Convention

```bash
git add <doc-files>
git commit -m "docs: <what was updated>

- Updated X section in Y.md
- Added documentation for Z feature"
```

---

## Documentation Structure Reference

```
docs/
├── getting-started.md      # Tutorial, installation
├── architecture.md         # System design
├── versioning-guide.md     # Version management
├── installation.md         # Detailed install
├── logging.md              # Logging system
├── security.md             # Security considerations
├── ci-cd.md                # CI/CD setup
├── release-process.md      # Release workflow
├── stack-presets.md        # Stack configurations
├── analytics-*.md          # Analytics (3 files)
├── adrs/                   # Architecture Decision Records (17 ADRs)
├── hooks/                  # Hook documentation
├── examples/               # Usage examples
├── architecture/           # Detailed architecture
└── _reference/             # Research & reference materials (not user-facing)

Root:
├── README.md               # Main entry point
├── CHANGELOG.md            # Version history
├── AGENTS.md               # Agent configuration
└── cli/README.md           # CLI reference
```

---

**Run this command after significant changes to keep documentation in sync.**

