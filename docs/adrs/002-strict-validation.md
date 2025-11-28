# ADR-002: Strict Validation from Start

```yaml
---
status: accepted
created: 2025-11-13
updated: 2025-11-13
deciders: System Architect
consulted: Development Team
informed: All Stakeholders
---
```

## Context

When building a system designed for automation and agentic workflows, **data quality is paramount**. Invalid primitives can break builds, cause runtime failures, or produce incorrect agent behavior. 

We must decide: should validation be strict by default, or permissive with optional strict mode?

### The Quality vs. Velocity Tradeoff

**Permissive Approach**:
- Fast initial development
- Easy to add "quick and dirty" primitives
- Can defer validation until later
- Risk: Technical debt accumulates, becomes hard to fix

**Strict Approach**:
- Slower initial development  
- Forces quality from day one
- Prevents bad primitives from entering repository
- Benefit: Clean codebase, trustworthy for automation

### Validation Layers

We have three layers of validation:

1. **Structural Validation**: File system organization
   - Correct directory structure (`<type>/<category>/<id>/`)
   - Required files exist (`.meta.yaml`, `.prompt.v1.md`, etc.)
   - Naming conventions (folder name = file name = ID)
   - No orphaned or misplaced files

2. **Schema Validation**: Content correctness
   - YAML/JSON parses successfully
   - Required fields present
   - Field types correct
   - Enum values valid

3. **Semantic Validation**: Cross-references and consistency
   - Tool IDs referenced actually exist
   - Model references resolve to real models
   - No duplicate IDs across repository
   - Version entries are sequential and consistent
   - Hashes match file contents

### Alternative Approaches Considered

1. **Permissive Mode Default**
   - Warnings instead of errors
   - Optional `--strict` flag
   - Pros: Faster development, easier for new contributors
   - Cons: Technical debt, unreliable in automation, unclear when to fix issues

2. **Validation-on-Demand**
   - Only validate when explicitly requested
   - Pros: Maximum flexibility
   - Cons: Easy to forget, primitives may never be validated

3. **Layered Enforcement**
   - Structural: strict
   - Schema: warnings
   - Semantic: optional
   - Pros: Balanced approach
   - Cons: Unclear rules, inconsistent quality

4. **Strict by Default** (CHOSEN)
   - All three layers enforced always
   - No permissive mode in v1
   - Exit with error if any validation fails
   - Pros: Trustworthy system, clear expectations, prevents debt
   - Cons: Slower initial development, stricter for contributors

## Decision

We will enforce **strict validation by default** across all three layers:

1. **All Commands Validate**
   - `agentic-p validate` runs all three layers, fails on any error
   - `agentic-p build` validates before building, fails if invalid
   - `agentic-p install` validates before installing, fails if invalid
   - `agentic-p new` generates valid primitives from templates

2. **No Permissive Mode in v1**
   - No `--lenient` or `--warn-only` flags
   - Errors are always errors, not warnings
   - Clear pass/fail: green ✓ or red ✗

3. **Validation Configuration**
   - Can disable individual layers in `primitives.config.yaml` (not recommended)
   - Can skip hash verification during development (`verify_hashes: false`)
   - But default config has all validation enabled

4. **Developer Experience**
   - Clear, actionable error messages
   - Show exact file path, line number, and field causing issue
   - Suggest fixes where possible
   - `agentic-p validate --json` for programmatic use

## Consequences

### Positive

✅ **Trustworthy Automation**: Can confidently use primitives in automated workflows

✅ **No Technical Debt**: Bad primitives cannot enter the repository

✅ **Clear Standards**: Everyone knows what "valid" means

✅ **Early Error Detection**: Catch issues immediately, not during deployment

✅ **Self-Documenting**: Validation errors teach conventions

✅ **Composability**: Can safely combine primitives, knowing they're all valid

### Negative

⚠️ **Learning Curve**: New contributors must understand all conventions upfront

⚠️ **Development Friction**: Must fix validation errors immediately

⚠️ **Manual Intervention**: Can't commit "WIP" primitives that are intentionally incomplete

⚠️ **Potential Blockers**: Strict validation might block experimental work

### Mitigations

1. **Excellent Documentation**: Clear guides on conventions and validation rules

2. **Helpful Error Messages**: Show exactly what's wrong and how to fix it

3. **Template Generation**: `agentic-p new` generates valid scaffolds automatically

4. **Validation on Save**: Recommend editor integration to validate continuously

5. **Test Fixtures**: Provide example valid primitives for reference

6. **Gradual Rollout**: Core team builds first primitives, establishing patterns for contributors

## Implementation Details

### Validation Flow

```
User runs command
       ↓
Load config (primitives.config.yaml)
       ↓
Layer 1: Structural Validation
  - Check directory structure
  - Verify required files exist
  - Validate naming conventions
  ✗ Fail → Show errors → Exit 1
  ✓ Pass → Continue
       ↓
Layer 2: Schema Validation
  - Parse YAML/JSON
  - Validate against JSON Schema
  - Check required fields
  ✗ Fail → Show errors → Exit 1
  ✓ Pass → Continue
       ↓
Layer 3: Semantic Validation
  - Resolve cross-references
  - Verify hashes
  - Check for duplicates
  ✗ Fail → Show errors → Exit 1
  ✓ Pass → Continue
       ↓
Command proceeds (build, install, etc.)
```

### Error Output Format

```
❌ Validation failed (3 errors)

Structural Errors:
  ✗ prompts/agents/python-pro/
    Folder name 'python-pro' does not match meta.yaml id 'python_pro'
    → Fix: Rename folder to 'python_pro' or update meta.yaml id to 'python-pro'

Schema Errors:
  ✗ prompts/agents/python-pro/python-pro.meta.yaml
    Line 8: Missing required field 'kind'
    → Fix: Add 'kind: agent' to meta.yaml

Semantic Errors:
  ✗ prompts/agents/python-pro/python-pro.meta.yaml
    Tool 'run-tests' referenced but not found in tools/
    → Fix: Create tools/shell/run-tests/ or remove from tools list

Run 'agentic-p validate' to see all validation errors.
```

### Configuration Options

```yaml
# primitives.config.yaml
validation:
  structural: true   # Can disable but NOT RECOMMENDED
  schema: true       # Can disable but NOT RECOMMENDED
  semantic: true     # Can disable but NOT RECOMMENDED
  strict: true       # Must be true in v1
  verify_hashes: true  # Can disable during development
```

## Success Criteria

Strict validation is successful when:

1. ✅ All primitives in repository pass all three validation layers
2. ✅ `agentic-p build` never fails due to invalid primitives
3. ✅ Generated primitives (from meta-prompts) are immediately valid
4. ✅ Contributors understand validation rules from error messages
5. ✅ Technical debt does not accumulate over time
6. ✅ The repository can be trusted as input to automated systems

## Related Decisions

- **ADR-001: Staged Bootstrap** - Generated primitives must pass validation
- **ADR-003: Non-Interactive Scaffolding** - Templates generate valid primitives
- **ADR-009: Versioned Primitives** - Hash validation ensures immutability

## References

- [JSON Schema Validation](https://json-schema.org/)
- [Semantic Versioning](https://semver.org/)
- [The Twelve-Factor App - Config](https://12factor.net/config)
- Rust's `rustc` compiler: strict by default, clear error messages

## Notes

**Why no permissive mode?**

Permissive modes create a "gray area" where primitives might work in development but fail in production. By being strict from the start:

- Contributors learn correct patterns immediately
- The repository maintains consistent quality
- Automation can trust the data
- There's no confusion about "when to fix warnings"

**Future considerations:**

- May add `agentic-p validate --fix` to auto-correct common issues
- May add `--warn` flag for specific rules (but still fail on errors)
- Editor plugins could validate on save and suggest fixes
- GitHub Actions could validate PRs automatically

**Philosophy:**

> "If it's worth having in the repository, it's worth having correctly."

We optimize for long-term maintainability over short-term velocity.

---

**Status**: Accepted  
**Last Updated**: 2025-11-13

