# ADR-006: Middleware-Based Hook System

```yaml
---
status: accepted
created: 2025-11-13
updated: 2025-11-13
deciders: System Architect
consulted: Development Team, Security Team
informed: All Stakeholders
---
```

## Context

Hooks are lifecycle event handlers that run during agent execution (PreToolUse, PostToolUse, SessionStart, etc.). They serve critical purposes:

- 🛡️ **Safety**: Block dangerous operations (rm -rf, editing secrets)
- 📊 **Observability**: Log operations, emit metrics, track usage
- 🎯 **Control**: Auto-approve safe operations, inject context

We need an architecture that supports:
- Multiple safety checks in sequence
- Multiple observability functions in parallel
- Composability (mix and match functions)
- Fail-fast behavior (stop on first block)
- Extensibility (easy to add new functions)

### Alternative Approaches

1. **Monolithic Hook Scripts**
   - Single script per hook event with all logic
   - Pros: Simple, self-contained
   - Cons: Not composable, hard to maintain, duplication

2. **Plugin System**
   - Each function is a separate plugin, hooks configure which to load
   - Pros: Very flexible
   - Cons: Complex plugin management, versioning challenges

3. **Middleware Pipeline** (CHOSEN)
   - Hook orchestrator runs pipeline of middleware functions
   - Each function gets input, processes, returns result
   - Pipeline stops on first block decision
   - Pros: Composable, testable, fail-fast
   - Cons: Requires orchestrator

## Decision

We will implement a **middleware pipeline architecture** for hooks:

### Architecture

```
Hook Event (from Claude)
        ↓
[Hook Orchestrator]
  - Loads hook.meta.yaml
  - Reads stdin (JSON)
  - Executes middleware pipeline
  - Aggregates results
  - Outputs decision (JSON)
        ↓
Middleware Pipeline:
  1. Safety Middleware (sequential, fail-fast)
     - block-dangerous-commands
     - protect-sensitive-files
     - validate-tool-inputs
     ✗ If any blocks → stop, return block
     ✓ All pass → continue
  
  2. Observability Middleware (parallel, non-blocking)
     - log-operations
     - emit-metrics
     - track-token-usage
     - debug-tracer
     ⚠️ Errors logged but don't block
        ↓
Final Decision (allow/block) + Metrics
```

### Hook Meta Configuration

```yaml
# hooks/lifecycle/pre-tool-use/hook.meta.yaml
id: pre-tool-use
kind: hook
category: lifecycle
event: PreToolUse
summary: "Safety and observability for tool execution"

execution: pipeline  # or "parallel"

middleware:
  # Safety middleware (blocking)
  - id: block-dangerous-commands
    path: middleware/safety/block-dangerous-commands.py
    type: safety
    enabled: true
    config:
      dangerous_patterns:
        - "rm -rf"
        - "sudo rm"
        - "dd if="
  
  - id: protect-sensitive-files
    path: middleware/safety/protect-sensitive-files.py
    type: safety
    enabled: true
    config:
      protected_patterns:
        - ".env*"
        - "*.key"
        - "*.pem"
  
  # Observability middleware (non-blocking)
  - id: log-operations
    path: middleware/observability/log-operations.py
    type: observability
    enabled: true
    config:
      log_file: "~/.claude/logs/operations.jsonl"
  
  - id: emit-metrics
    path: middleware/observability/emit-metrics.py
    type: observability
    enabled: true
    config:
      statsd_host: "localhost"
      statsd_port: 8125

# Provider-specific overrides
providers:
  claude:
    timeout: 60
  openai:
    enabled: false  # OpenAI doesn't support hooks natively

default_decision: "allow"  # If no middleware blocks
```

### Middleware Interface

**Python**:
```python
from typing import Dict, Any, List
from dataclasses import dataclass

@dataclass
class MiddlewareResult:
    decision: str  # "allow", "block", "continue"
    reason: str
    metrics: Dict[str, Any]

def process(
    hook_input: Dict[str, Any],
    config: Dict[str, Any],
    previous_results: List[MiddlewareResult],
) -> MiddlewareResult:
    """
    Standard middleware interface.
    
    Args:
        hook_input: The hook event data (tool_name, tool_input, etc.)
        config: Middleware-specific configuration
        previous_results: Results from previous middleware in pipeline
    
    Returns:
        MiddlewareResult with decision, reason, and metrics
    """
    # Your logic here
    return MiddlewareResult(
        decision="allow",  # or "block"
        reason="All checks passed",
        metrics={"checks_run": 3}
    )
```

### Execution Strategies

**Pipeline (Sequential, Fail-Fast)**:
- Middleware runs in order
- Each sees results from previous
- First "block" stops pipeline
- Use for: Safety checks

**Parallel (Concurrent)**:
- All middleware runs simultaneously
- Results aggregated at end
- Errors don't stop others
- Use for: Observability

## Rationale

### Why Middleware?

✅ **Composable**: Mix and match functions freely

✅ **Testable**: Each function tested in isolation

✅ **Reusable**: Same middleware across different hooks

✅ **Fail-Fast**: Stop immediately on safety block

✅ **Non-Blocking Observability**: Metrics don't affect decisions

✅ **Extensible**: Add new middleware without changing orchestrator

✅ **Configurable**: Enable/disable, configure per middleware

✅ **Debuggable**: See exactly which middleware blocked and why

### Why Not Monolithic?

❌ **Duplication**: Same safety checks copied across hooks

❌ **Hard to Test**: Must test entire script, not components

❌ **Not Composable**: Can't reuse parts

❌ **Maintenance**: Changes require editing multiple scripts

## Consequences

### Positive

✅ **Safety First**: Critical safety checks run first, block immediately

✅ **Rich Observability**: Multiple metrics/logs without affecting safety

✅ **Easy Extension**: Add new middleware without touching orchestrator

✅ **Clear Separation**: Safety vs observability clearly distinguished

✅ **Team Collaboration**: Different teams can own different middleware

✅ **Gradual Rollout**: Enable/disable middleware independently

### Negative

⚠️ **Orchestrator Complexity**: Need robust pipeline executor

⚠️ **Coordination**: Multiple middleware need consistent interfaces

⚠️ **Debugging**: Pipeline failures require checking multiple functions

⚠️ **Configuration**: More config than single-script approach

### Mitigations

1. **Standard Interface**: All middleware use same signature

2. **Base Class**: Provide middleware_base.py with helpers

3. **Testing Framework**: Test middleware in isolation and in pipeline

4. **Logging**: Orchestrator logs each middleware execution

5. **Error Handling**: Graceful handling of middleware failures

6. **Documentation**: Clear examples for writing middleware

## Implementation

### Orchestrator

```python
# hooks/lifecycle/pre-tool-use/impl.python.py
#!/usr/bin/env python3
import json
import sys
from pathlib import Path
import importlib.util

def load_middleware(middleware_config):
    """Dynamically load middleware module"""
    path = Path(__file__).parent / middleware_config["path"]
    spec = importlib.util.spec_from_file_location("middleware", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main():
    # Load hook configuration
    hook_config = yaml.safe_load(
        Path(__file__).parent / "hook.meta.yaml"
    )
    
    # Read input
    hook_input = json.load(sys.stdin)
    
    # Execute middleware pipeline
    results = []
    for mw_config in hook_config["middleware"]:
        if not mw_config["enabled"]:
            continue
        
        # Load and execute middleware
        module = load_middleware(mw_config)
        result = module.process(
            hook_input=hook_input,
            config=mw_config.get("config", {}),
            previous_results=results
        )
        
        results.append({
            "id": mw_config["id"],
            "type": mw_config["type"],
            "decision": result.decision,
            "reason": result.reason,
            "metrics": result.metrics
        })
        
        # Fail-fast for safety middleware
        if mw_config["type"] == "safety" and result.decision == "block":
            break
    
    # Aggregate decisions
    final_decision = "allow"
    block_reasons = []
    
    for result in results:
        if result["decision"] == "block":
            final_decision = "block"
            block_reasons.append(f"{result['id']}: {result['reason']}")
    
    # Collect metrics
    all_metrics = {}
    for result in results:
        all_metrics[result["id"]] = result["metrics"]
    
    # Output Claude-compatible JSON
    output = {
        "decision": final_decision,
        "reason": "; ".join(block_reasons) if block_reasons else "All checks passed",
        "hookSpecificOutput": {
            "hookEventName": hook_config["event"],
            "metrics": all_metrics
        }
    }
    
    print(json.dumps(output))
    sys.exit(2 if final_decision == "block" else 0)

if __name__ == "__main__":
    main()
```

### Example Safety Middleware

```python
# middleware/safety/block-dangerous-commands.py
import re
from middleware_base import MiddlewareResult

DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bsudo\s+rm\b",
    r"\bdd\s+if=",
    r"\b>>\s*/dev/sd[a-z]\b",
    r"\bmkfs\b",
]

def process(hook_input, config, previous_results):
    tool_name = hook_input.get("tool_name")
    tool_input = hook_input.get("tool_input", {})
    
    if tool_name != "Bash":
        return MiddlewareResult(
            decision="allow",
            reason="Not a bash command",
            metrics={"skipped": True}
        )
    
    command = tool_input.get("command", "")
    
    # Check against dangerous patterns
    for pattern in config.get("dangerous_patterns", DANGEROUS_PATTERNS):
        if re.search(pattern, command, re.IGNORECASE):
            return MiddlewareResult(
                decision="block",
                reason=f"Dangerous command pattern detected: {pattern}",
                metrics={
                    "blocked": True,
                    "pattern": pattern,
                    "command": command[:100]
                }
            )
    
    return MiddlewareResult(
        decision="allow",
        reason="No dangerous patterns detected",
        metrics={"checked_patterns": len(DANGEROUS_PATTERNS)}
    )
```

### Example Observability Middleware

```python
# middleware/observability/log-operations.py
import json
from datetime import datetime
from pathlib import Path
from middleware_base import MiddlewareResult

def process(hook_input, config, previous_results):
    log_file = Path(config.get("log_file", "~/.claude/logs/operations.jsonl")).expanduser()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "session_id": hook_input.get("session_id"),
        "tool_name": hook_input.get("tool_name"),
        "tool_input": hook_input.get("tool_input"),
        "blocked": any(r["decision"] == "block" for r in previous_results)
    }
    
    try:
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        return MiddlewareResult(
            decision="continue",  # Doesn't affect outcome
            reason="Logged successfully",
            metrics={"logged": True, "log_file": str(log_file)}
        )
    except Exception as e:
        # Non-blocking: log errors but don't fail
        return MiddlewareResult(
            decision="continue",
            reason=f"Logging failed: {e}",
            metrics={"logged": False, "error": str(e)}
        )
```

## Success Criteria

Middleware-based hooks are successful when:

1. ✅ Safety middleware reliably blocks dangerous operations
2. ✅ Observability middleware runs without blocking decisions
3. ✅ Pipeline stops immediately on first block
4. ✅ New middleware can be added without changing orchestrator
5. ✅ Each middleware is testable in isolation
6. ✅ Configuration enables/disables middleware dynamically
7. ✅ Metrics provide insight into agent behavior

## Related Decisions

- **ADR-005: Polyglot Implementations** - Middleware in Python/TypeScript
- **ADR-007: Generated Provider Outputs** - Hooks transformed for Claude
- **ADR-008: Test-Driven Development** - Testing middleware

## References

- [Express.js Middleware](https://expressjs.com/en/guide/using-middleware.html)
- [Django Middleware](https://docs.djangoproject.com/en/stable/topics/http/middleware/)
- [Claude Hooks Reference](https://docs.claude.com/en/docs/claude-code/hooks)

## Notes

**Why Two Types?**

Safety and observability have fundamentally different requirements:
- **Safety**: Must block, fail-fast, sequential
- **Observability**: Can't block, best-effort, parallel

By distinguishing them, we make these requirements explicit.

**Future: More Types?**

Could add other types:
- **Transformation**: Modify tool inputs before execution
- **Validation**: Check preconditions
- **Authorization**: Check permissions

But for v1, safety + observability covers 90% of use cases.

---

**Status**: Accepted  
**Last Updated**: 2025-11-13

