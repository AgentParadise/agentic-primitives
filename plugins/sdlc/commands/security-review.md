---
description: Audit codebase security posture with focus on supply chain threats
argument-hint: "[audit|fix|both] - default: audit"
model: opus
allowed-tools: Read, Grep, Glob, Bash, Edit, Write
---

# Security Review

Audit the codebase for security vulnerabilities — especially supply chain threats — and
produce a prioritized list of action items. Uses the `security-hardening` skill as the
threat model and audit framework.

## Variables

MODE: $1 || "audit"

## Instructions

Use the **security-hardening** skill as your knowledge base. It contains the full threat
model (10 attack categories), audit workflow (12 steps), and fix recipes with inline
comments explaining the "why" behind each defense.

1. Run the audit workflow from the skill (Steps 1-11 + 6.5 + 6.6)
2. Collect findings into a structured report
3. Prioritize the top 2-6 action items by impact
4. If MODE is "fix" or "both", walk through fixes with the user (confirm before each change)

## Workflow

### Phase 1: Discovery

Run audit steps 1-3 from the security-hardening skill:
- Step 1: Project structure (workflows, lock files, Dockerfiles)
- Step 2: GitHub Actions SHA pinning (mutable tags = P0)
- Step 3: Workflow permissions (missing least-privilege = P0)

### Phase 2: Supply Chain

Run audit steps 4-6.6 — the highest-impact area:
- Step 4: Install hygiene (postinstall hook blocking)
- Step 5: Lock file discipline (npm ci, uv sync --frozen)
- Step 6: Vulnerability scanning (OSV Scanner, dependency-review)
- Step 6.5: Native ecosystem audits (pip-audit, pnpm audit)
- Step 6.6: Dependency tree review (total counts, heavy chains)

### Phase 3: Code & Secrets

Run audit steps 7-11:
- Step 7: SAST tools (CodeQL, Semgrep, Bandit)
- Step 8: Container scanning (Docker Scout)
- Step 9: Secret scanning (gitleaks, hardcoded secrets)
- Step 10: .gitignore credential patterns
- Step 11: CODEOWNERS protection

### Phase 4: Report

Generate the audit report using the template from the security-hardening skill.
After the full report, add a **Top Action Items** section:

```markdown
## Top Action Items

Prioritized by impact — fix these first:

1. **[P0/P1/P2]** <title> — <one-line description>
   - Location: `path/to/file:line`
   - Fix: <concise fix description or reference to fix recipe>

2. ...
(2-6 items, sorted by priority)
```

### Phase 5: Fix (if MODE is "fix" or "both")

For each action item:
1. Show the user the exact change (diff preview)
2. Wait for confirmation before applying
3. Apply using the fix recipes from the security-hardening skill
4. Mark the item as done in the report

## Examples

### Example 1: Read-only audit (default)
```
/security-review
```
Runs all audit steps, produces report with prioritized action items. No changes made.

### Example 2: Audit and fix
```
/security-review both
```
Runs audit, then walks through fixes one by one with user confirmation.

### Example 3: Fix mode (skip audit output, go straight to fixes)
```
/security-review fix
```
Runs audit silently, then presents fixes for each finding.
