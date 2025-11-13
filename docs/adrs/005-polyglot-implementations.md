# ADR-005: Polyglot Tool & Hook Implementations

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

Tools and hooks need actual executable implementations. We must decide: **single language or polyglot?**

### Tool Implementations

Tools can be implemented:
- **Locally** (run directly by CLI or agent)
- **Remotely** (call external API)
- **Provider-natively** (use Claude's Bash tool, OpenAI's function calling)

### Hook Implementations

Hooks are lifecycle event handlers that need to:
- Parse JSON input
- Execute middleware pipeline
- Return structured output
- Handle errors gracefully

### Language Options

**Rust**:
- ✅ Fast, safe, already used for CLI
- ❌ Slower development, steeper learning curve

**Python**:
- ✅ Rich ecosystem, easy scripting, good for ML/data
- ✅ `uv` for fast dependency management
- ❌ Slower runtime, requires Python install

**TypeScript/Bun**:
- ✅ Fast, modern, great for web/API integrations
- ✅ Bun for native performance
- ❌ Less common for systems tasks

## Decision

We will support **polyglot implementations** with preferences:

### For Tools

Tools can have **multiple implementations**:

```
tools/<category>/<id>/
├── tool.meta.yaml          # Logical specification
├── impl.claude.yaml        # Claude SDK binding
├── impl.openai.json        # OpenAI function binding
├── impl.local.rs           # Rust implementation
├── impl.local.py           # Python implementation
└── impl.local.ts           # TypeScript/Bun implementation
```

**Execution priority**:
1. Provider-native (if building for that provider)
2. Local Rust (fastest)
3. Local Python (if `uv` available)
4. Local TypeScript (if `bun` available)

### For Hooks

Hooks support **dual implementations**:

```
hooks/<category>/<id>/
├── hook.meta.yaml          # Configuration
├── impl.python.py          # Python orchestrator (PRIMARY)
├── impl.bun.ts             # Bun/TS orchestrator (ALTERNATIVE)
└── middleware/
    ├── safety/             # Can mix languages
    │   ├── *.py
    │   └── *.ts
    └── observability/
        ├── *.py
        └── *.ts
```

**Primary**: Python with `uv`
- Best ecosystem for safety/observability
- Easy to write middleware
- Good performance with `uv`

**Alternative**: Bun/TypeScript
- For teams preferring JS ecosystem
- Fast native performance
- Good for web-focused projects

### Language-Specific Tooling

**Python**:
- Use `uv` for dependency management (fast, reliable)
- Standard interface: `def process(hook_input, config, previous_results)`
- Testing: `pytest`

**TypeScript/Bun**:
- Use `bun` for runtime (fast, native)
- Standard interface: `export function process(hookInput, config, previousResults)`
- Testing: `bun test`

**Rust**:
- For performance-critical tools
- Can be called from Python/TS via FFI if needed

## Rationale

### Why Polyglot?

✅ **Right Tool for Job**: Use language that fits the task
- Python: ML, data processing, scientific computing
- TypeScript: Web APIs, JSON manipulation
- Rust: Performance-critical, systems programming

✅ **Leverage Ecosystems**: 
- Python: requests, pandas, scikit-learn
- TypeScript: axios, zod, express
- Rust: tokio, serde, reqwest

✅ **Team Flexibility**: Teams can use their preferred language

✅ **Gradual Migration**: Start with Python, optimize to Rust later

✅ **Best Libraries**: Use best-in-class libraries regardless of language

### Why Not Single Language?

❌ **Missed Opportunities**: Some tasks much easier in specific languages

❌ **Ecosystem Limitations**: No single language has best libraries for everything

❌ **Team Friction**: Forcing unfamiliar language slows development

❌ **Performance Tradeoffs**: Can't optimize critical paths

## Consequences

### Positive

✅ **Flexibility**: Use best language for each component

✅ **Performance Options**: Can optimize critical paths with Rust

✅ **Easy Prototyping**: Quick Python scripts, optimize later

✅ **Rich Ecosystems**: Access to all language libraries

✅ **Team Choice**: Contributors use familiar languages

### Negative

⚠️ **Complexity**: Multiple runtimes to manage

⚠️ **Testing**: Need test infrastructure for each language

⚠️ **Dependencies**: Users need Python + Bun (or just one)

⚠️ **Maintenance**: More languages = more tools to keep updated

### Mitigations

1. **Clear Preferences**: Python primary for hooks, alternatives optional

2. **Minimal Runtimes**: Only Python (`uv`) required, others optional

3. **Standard Interfaces**: Same signature across languages

4. **Shared Tests**: Test behavior, not implementation

5. **Documentation**: Clear examples for each language

## Implementation

### Python Hook Orchestrator

```python
#!/usr/bin/env python3
"""Hook orchestrator using uv-managed dependencies"""
import json
import sys
from pathlib import Path

def main():
    # Load hook configuration
    hook_config = load_hook_meta()
    
    # Read hook input from stdin
    hook_input = json.load(sys.stdin)
    
    # Execute middleware pipeline
    results = []
    for middleware in hook_config["middleware"]:
        if not middleware["enabled"]:
            continue
        
        result = run_middleware(middleware, hook_input, results)
        results.append(result)
        
        # Fail-fast on block decision
        if result["decision"] == "block":
            break
    
    # Aggregate results
    final_decision = aggregate_decisions(results)
    metrics = collect_metrics(results)
    
    # Output Claude-compatible JSON
    output = {
        "decision": final_decision,
        "reason": get_block_reason(results),
        "metrics": metrics
    }
    
    print(json.dumps(output))
    sys.exit(0 if final_decision != "block" else 2)

if __name__ == "__main__":
    main()
```

### Python Middleware Interface

```python
# middleware_base.py
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
    """Standard middleware interface - implement this"""
    raise NotImplementedError
```

### TypeScript/Bun Hook Orchestrator

```typescript
#!/usr/bin/env bun
/**
 * Hook orchestrator using Bun runtime
 */
interface HookInput {
  session_id: string;
  tool_name?: string;
  tool_input?: any;
  // ... other fields
}

interface MiddlewareResult {
  decision: "allow" | "block" | "continue";
  reason: string;
  metrics: Record<string, any>;
}

async function main() {
  const hookConfig = await loadHookMeta();
  const hookInput: HookInput = await Bun.stdin.json();
  
  const results: MiddlewareResult[] = [];
  
  for (const middleware of hookConfig.middleware) {
    if (!middleware.enabled) continue;
    
    const result = await runMiddleware(middleware, hookInput, results);
    results.push(result);
    
    if (result.decision === "block") break;
  }
  
  const output = {
    decision: aggregateDecisions(results),
    reason: getBlockReason(results),
    metrics: collectMetrics(results)
  };
  
  console.log(JSON.stringify(output));
  process.exit(output.decision === "block" ? 2 : 0);
}

main();
```

### Tool Implementation Example

```
tools/shell/run-tests/
├── tool.meta.yaml
│
├── impl.claude.yaml    # Use Claude's Bash tool
│   tool: run-tests
│   type: bash
│   command_template: "{{command}}"
│
├── impl.openai.json    # OpenAI function calling
│   {
│     "name": "run_tests",
│     "parameters": { ... }
│   }
│
├── impl.local.py       # Python subprocess
│   #!/usr/bin/env python3
│   import subprocess
│   def run_tests(command="pytest"):
│       result = subprocess.run(...)
│       return result.stdout
│
└── impl.local.rs       # Rust std::process
    use std::process::Command;
    pub fn run_tests(cmd: &str) -> Result<String> {
        let output = Command::new(cmd).output()?;
        Ok(String::from_utf8(output.stdout)?)
    }
```

## Success Criteria

Polyglot support is successful when:

1. ✅ Hooks run with Python (`uv`) or Bun
2. ✅ Tools can have multiple language implementations
3. ✅ Standard interfaces work across languages
4. ✅ Tests validate behavior regardless of implementation
5. ✅ Documentation covers all supported languages
6. ✅ Contributors can choose their language

## Related Decisions

- **ADR-006: Middleware-Based Hooks** - Defines hook architecture
- **ADR-008: Test-Driven Development** - Tests must cover all languages

## References

- [uv - Fast Python package installer](https://github.com/astral-sh/uv)
- [Bun - Fast JavaScript runtime](https://bun.sh/)
- [Polyglot Programming](https://en.wikipedia.org/wiki/Polyglot_(computing))

## Notes

**Runtime Requirements**:
- **Minimal**: Just Python 3.11+ with `uv`
- **Optional**: Bun for TypeScript hooks/tools
- **Optional**: Rust for performance-critical tools

**Migration Path**:
1. Start: Python prototype
2. Optimize: Rust for hot paths
3. Alternative: TypeScript for web-focused teams

**No Java/Go/Other**:
For now, limiting to Python/TypeScript/Rust:
- Covers 90% of use cases
- Limits maintenance burden
- Can add more languages later if needed

---

**Status**: Accepted  
**Last Updated**: 2025-11-13

