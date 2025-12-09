# ADR-023: Pattern Registry Architecture

## Status
Accepted

## Date
2024-12-09

## Context
The hook validators (bash, file, pii) contained hardcoded regex patterns for:
- Dangerous shell commands (rm -rf /, fork bombs, etc.)
- Sensitive file paths and patterns (.env, private keys, etc.)
- PII detection (SSN, credit cards, etc.)

This made patterns difficult to:
1. Review and audit
2. Test systematically
3. Update without code changes
4. Document for users

## Decision
We will implement a YAML-based pattern registry with:

### 1. Pattern Files
```
primitives/v1/hooks/validators/
├── security/
│   └── patterns/
│       ├── bash.patterns.yaml
│       └── file.patterns.yaml
├── prompt/
│   └── patterns/
│       └── pii.patterns.yaml
└── pattern_loader.py
```

### 2. Pattern Format
```yaml
name: Bash Command Security Patterns
description: Patterns for validating shell commands

blocked:
  - id: rm-rf-root
    pattern: '\brm\s+-rf\s+/(?!\w)'
    description: "rm -rf / (root deletion)"
    risk_level: critical
    rationale: "Would delete entire filesystem"
    test_cases:
      - input: "rm -rf /"
        expected: blocked
      - input: "rm -rf /home/user/project"
        expected: allowed

suspicious:
  - id: sudo-usage
    pattern: '\bsudo\s+'
    description: "sudo usage"
    risk_level: medium
    test_cases:
      - input: "sudo apt update"
        expected: suspicious
```

### 3. Pattern Loader (`pattern_loader.py`)
```python
def load_blocked_patterns(file: Path) -> list[tuple[Pattern, str, str, str]]:
    """Returns: (compiled_regex, description, risk_level, id)"""

def load_suspicious_patterns(file: Path) -> list[tuple[Pattern, str, str, str]]:
    """Returns: (compiled_regex, description, risk_level, id)"""
```

### 4. Test Generation
```bash
python scripts/generate_pattern_tests.py
# Generates tests from YAML test_cases
```

### 5. Fallback Behavior
Validators include hardcoded fallback patterns if YAML files are not found,
ensuring standalone usage without dependencies.

## Consequences

### Positive
- Patterns are self-documenting with test cases
- Tests can be auto-generated from YAML
- Patterns can be audited and reviewed separately from code
- Pattern updates don't require code changes
- Risk levels enable graduated response

### Negative
- PyYAML dependency for YAML loading
- Slightly more complex initialization

### Neutral
- Patterns are pre-compiled at load time for performance
- Pattern IDs enable precise error reporting

## Pattern Categories

### Bash Security Patterns
- **blocked**: Destructive commands (rm -rf /, fork bombs, disk overwrite)
- **suspicious**: Elevated privileges, remote execution

### File Security Patterns
- **blocked_paths**: System files (/etc/passwd, /boot)
- **sensitive_file_patterns**: .env, private keys, credentials
- **sensitive_content_patterns**: Private key headers, API keys

### PII Patterns
- **pii_patterns**: SSN, credit cards, phone numbers
- **context_patterns**: "my password", "my SSN"

## Implementation
- `pattern_loader.py`: YAML loading with fallback
- `bash.py`, `file.py`, `pii.py`: Updated to use loader
- `scripts/generate_pattern_tests.py`: Test generator

## Related
- ADR-013: Hybrid Hook Architecture
- ADR-016: Hook Event Correlation
