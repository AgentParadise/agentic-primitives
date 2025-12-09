# Severity Classification Guide

Quick reference for categorizing review comments.

## 🔴 MUST_FIX (Critical)

**Blocks merge.** Fix immediately.

| Category | Keywords | Examples |
|----------|----------|----------|
| Security | injection, XSS, auth bypass | SQL injection, credential leak |
| Logic | bug, crash, null, race | Off-by-one, deadlock |
| Data | loss, corrupt, invalid | Missing validation |

## 🟡 SHOULD_FIX (Important)

**Recommended before merge.**

| Category | Keywords | Examples |
|----------|----------|----------|
| Performance | slow, N+1, leak | Memory leak, blocking IO |
| Quality | test, error handling | Missing tests |
| Maintainability | complex, unclear | Tight coupling |

## 🟢 OPTIONAL (Nice to Have)

**Discretionary improvements.**

| Category | Keywords | Examples |
|----------|----------|----------|
| Style | nit, naming, format | Variable naming |
| Suggestions | could, consider | Alternative approaches |
