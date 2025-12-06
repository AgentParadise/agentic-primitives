---
description: Prioritize review comments by severity
model: sonnet
allowed-tools: Read
---

# Prioritize Review Comments

Categorize and prioritize review comments for efficient resolution.

## Purpose

*Level 2 (Workflow)*

Analyze review comments and categorize by severity to focus on critical issues first.

## Variables

COMMENTS: $ARGUMENTS    # Review comments (from /review/fetch output or direct input)

## Severity Categories

### 🔴 MUST_FIX (Critical)

Issues that **block merge**. Fix these first.

**Security vulnerabilities:**
- SQL injection, XSS, CSRF
- Authentication/authorization bypass
- Secrets or credentials in code
- Insecure data handling

**Logic errors:**
- Incorrect algorithm implementation
- Race conditions, deadlocks
- Null pointer / undefined access
- Off-by-one errors
- Incorrect business logic

**Data integrity:**
- Data loss risks
- Missing validation
- Incorrect state management

**Keywords to watch for:**
- "security", "vulnerability", "injection", "auth"
- "bug", "error", "incorrect", "wrong"
- "crash", "null", "undefined", "race"
- "must", "required", "blocking"

### 🟡 SHOULD_FIX (Important)

Issues that should be addressed but don't block merge.

**Performance issues:**
- N+1 queries
- Memory leaks
- Blocking operations
- Inefficient algorithms

**Best practices:**
- Missing error handling
- Inadequate logging
- Missing tests for new code
- Unclear error messages

**Maintainability:**
- Complex/hard-to-read code
- Missing documentation for public APIs
- Tight coupling

**Keywords to watch for:**
- "performance", "slow", "inefficient"
- "should", "consider", "recommend"
- "test", "coverage", "logging"

### 🟢 OPTIONAL (Nice to Have)

Suggestions that improve quality but are discretionary.

**Style issues:**
- Naming conventions
- Code formatting
- Comment quality
- File organization

**Info suggestions:**
- Alternative approaches
- Minor optimizations
- Future considerations

**Keywords to watch for:**
- "nitpick", "nit", "minor"
- "suggestion", "optional", "could"
- "style", "formatting", "naming"

## Workflow

### 1. Parse Comments

Extract each comment with context:
- File path and line number
- Author (human vs automated)
- Full comment text
- Any thread/replies

### 2. Classify Each Comment

For each comment, evaluate:

1. **Check for security keywords** → 🔴 MUST_FIX
2. **Check for bug/error indicators** → 🔴 MUST_FIX
3. **Check for performance concerns** → 🟡 SHOULD_FIX
4. **Check for best practice suggestions** → 🟡 SHOULD_FIX
5. **Check for style/nitpick indicators** → 🟢 OPTIONAL

Consider author weight:
- Copilot security warnings → take seriously
- Human reviewer "must fix" → 🔴
- Human reviewer suggestions → evaluate context

### 3. Sort by Priority

Order within each category by:
1. Severity of impact
2. Ease of fix (quick wins first)
3. File location (group related fixes)

## Report

```markdown
## Prioritized Review Comments

### Summary

| Priority | Count | Action |
|----------|-------|--------|
| 🔴 MUST_FIX | X | Required before merge |
| 🟡 SHOULD_FIX | X | Recommended |
| 🟢 OPTIONAL | X | At your discretion |

---

### 🔴 MUST_FIX (Critical) - X items

These must be addressed before merging.

#### 1. [file.py:42] Security: SQL injection risk
**Author:** @copilot
**Comment:**
> User input is passed directly to SQL query without sanitization.

**Suggested fix:** Use parameterized queries.

---

#### 2. [auth.py:15] Logic: Missing null check
**Author:** @reviewer
**Comment:**
> This will crash if user is not authenticated.

**Suggested fix:** Add null check before accessing user properties.

---

### 🟡 SHOULD_FIX (Important) - X items

These should be addressed if time permits.

#### 1. [api.py:88] Performance: Potential N+1 query
**Author:** @copilot
**Comment:**
> This query inside a loop could cause performance issues.

**Suggested fix:** Batch the queries or use eager loading.

---

### 🟢 OPTIONAL (Nice to Have) - X items

Address these at your discretion.

#### 1. [utils.py:23] Style: Consider renaming
**Author:** @reviewer
**Comment:**
> `data` is a bit vague, consider `user_records`.

---

## Action Plan

1. **Immediate:** Fix all 🔴 MUST_FIX items
2. **Before merge:** Address 🟡 SHOULD_FIX items
3. **Optional:** Consider 🟢 OPTIONAL improvements

Estimated effort: X items, ~Y minutes
```

## Examples

### Example 1: Prioritize from fetch output
```
/review/fetch | /review/prioritize
```

### Example 2: Direct input
```
/review/prioritize "Security: SQL injection at line 42"
```

## Integration Points

- Receives input from `/review/fetch`
- Output guides fix prioritization in `/workflow/merge-cycle`
- Helps decide which issues to auto-fix vs manual fix
