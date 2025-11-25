# ADR-014: Wrapper+Impl Pattern for Hook Execution

**Status:** Accepted  
**Date:** 2025-11-25  
**Decision Makers:** Core Team  
**Related:** [ADR-013: Hybrid Hook Architecture](./013-hybrid-hook-architecture.md)

## Context

Our hook system needed to solve several competing requirements:
1. **Generic primitives** - Hook implementations should work across any agent provider
2. **Agent-specific configuration** - Each agent (Claude, OpenAI, Gemini) needs custom middleware, timeouts, and behaviors
3. **Scalability** - System must handle 100+ concurrent agents without resource exhaustion
4. **Performance** - Minimize subprocess overhead in the hot path

### The Problem

Initial implementations had two major issues:

**Issue 1: Configuration Hell**

```mermaid
graph LR
    A[Primitive YAML] --> B[Agent Config]
    B --> C[Runtime Loading]
    C --> D[Validation]
    C --> E[❌ PyYAML Dependency]
    C --> F[❌ File I/O Overhead]
    C --> G[❌ Runtime Errors]
```

Loading YAML at runtime created:
- Dependency on PyYAML in production
- Runtime errors for config issues
- Slower execution due to file I/O

**Issue 2: Subprocess Cascade**

```mermaid
graph TD
    A[Claude Agent] -->|spawn| B[Wrapper Script]
    B -->|spawn| C[UV Process]
    C -->|spawn| D[Python Impl]
    D -->|spawn| E[Middleware Script]
    E -->|spawn| F[UV Process]
    F -->|spawn| G[Python Middleware]
    
    style A fill:#f9f,stroke:#333
    style B fill:#fbb,stroke:#333
    style C fill:#fbb,stroke:#333
    style D fill:#fbb,stroke:#333
    style E fill:#fbb,stroke:#333
    style F fill:#fbb,stroke:#333
    style G fill:#fbb,stroke:#333
    
    H[❌ 3-5 Subprocesses per Hook]
    I[❌ BlockingIOError under Load]
    J[❌ 100ms+ Latency]
```

Each hook call spawned 3-5 subprocesses, leading to:
- `BlockingIOError: Resource temporarily unavailable` under load
- 100ms+ latency per hook
- System resource exhaustion with multiple agents

## Decision

We implemented a **Wrapper+Impl Pattern** that separates concerns:

### Architecture

```mermaid
graph LR
    subgraph "Build Output"
        W[hooks-collector.py<br/>Wrapper - Generated]
        I[hooks-collector.impl.py<br/>Implementation - Copied]
    end
    
    subgraph "Wrapper Responsibilities"
        W1[Embed Config at Build Time]
        W2[Inject Config into stdin]
        W3[Execute via runpy In-Process]
        W4[Or Spawn UV for External Deps]
    end
    
    subgraph "Impl Responsibilities"
        I1[Pure Python Logic]
        I2[Extract __agent_config__]
        I3[Business Logic]
        I4[Return JSON to stdout]
    end
    
    W --> W1
    W --> W2
    W --> W3
    W --> W4
    
    I --> I1
    I --> I2
    I --> I3
    I --> I4
    
    style W fill:#9cf,stroke:#333
    style I fill:#9f9,stroke:#333
```

**File Structure:**
```
build/claude/.claude/hooks/core/
├── hooks-collector.py         # Wrapper (generated)
└── hooks-collector.impl.py    # Implementation (copied)
```

### Build-Time vs Runtime

```mermaid
sequenceDiagram
    participant Build as Build System (Rust)
    participant Agent as Agent Config YAML
    participant Template as Wrapper Template
    participant Wrapper as Generated Wrapper
    participant Impl as Implementation
    
    rect rgb(200, 220, 255)
        Note over Build,Impl: BUILD TIME
        Build->>Agent: Load config YAML
        Agent-->>Build: middleware, timeouts, etc.
        Build->>Build: Serialize to JSON
        Build->>Template: Render with config
        Template-->>Wrapper: Generate .py with embedded config
        Build->>Impl: Copy from primitives/
    end
    
    rect rgb(220, 255, 220)
        Note over Build,Impl: RUNTIME
        Note over Wrapper: Claude calls hook
        Wrapper->>Wrapper: Parse embedded AGENT_CONFIG
        Wrapper->>Wrapper: Read stdin (hook event)
        Wrapper->>Wrapper: Inject config into event
        Wrapper->>Impl: Execute via runpy (in-process)
        Impl->>Impl: Extract __agent_config__
        Impl->>Impl: Run business logic
        Impl-->>Wrapper: Return JSON result
        Wrapper-->>Build: Output to stdout
    end
```

**Build Time Code:**
```rust
// cli/src/providers/claude.rs
let agent_config = load_agent_hook_config("claude-code", "hooks-collector");
let config_json = serde_json::to_string_pretty(&agent_config)?;

// Generate wrapper with embedded config
template.render({
    "config_json": config_json,
    "impl_filename": "hooks-collector.impl.py"
})
```

**Runtime Code:**
```python
# hooks-collector.py (Wrapper)
AGENT_CONFIG = r'''{"agent": "claude-code", "middleware": [...]}'''

def main():
    config_data = json.loads(AGENT_CONFIG)
    hook_event = json.loads(sys.stdin.read())
    hook_event['__agent_config__'] = config_data
    
    # Execute impl in-process (no subprocess!)
    sys.stdin = io.StringIO(json.dumps(hook_event))
    runpy.run_path("hooks-collector.impl.py")
```

```python
# hooks-collector.impl.py (Implementation)
async def main():
    hook_event = json.loads(sys.stdin.read())
    agent_config = hook_event.pop('__agent_config__', None)
    
    orchestrator = HooksCollectorOrchestrator(agent_config=agent_config)
    result = await orchestrator.execute(hook_event)
    print(json.dumps(result))
```

## Consequences

### Positive

✅ **Zero Runtime I/O** - No YAML loading, config is embedded in Python source  
✅ **Fail Fast** - Config errors caught at build time, not in production  
✅ **Performance** - In-process execution eliminates 2-3 subprocess spawns  
✅ **Scalability** - Tested with 100+ concurrent hooks, no resource exhaustion  
✅ **Generic Primitives** - Same impl file works for any agent provider  
✅ **Agent Flexibility** - Each agent customizes via build-time config injection  

### Negative

⚠️ **Build Complexity** - Two files per hook increases artifact count  
⚠️ **Learning Curve** - Developers must understand wrapper vs impl roles  
⚠️ **Debugging** - Stack traces show wrapper → runpy → impl layers  

### Trade-offs

| Aspect | Alternative Considered | Why Rejected |
|--------|----------------------|--------------|
| **Single file** | Merge wrapper+impl into one | Config would need YAML loading (slow, fragile) |
| **Environment vars** | Pass config via ENV | Limited data types, harder to debug |
| **Subprocess always** | Keep subprocess spawn | BlockingIOError under load, poor performance |
| **Compiled binary** | Rust hooks instead | Loses Python ecosystem, harder to extend |

## Implementation Details

### When to Use In-Process Execution

```mermaid
flowchart TD
    Start[Wrapper Execution] --> Check{Is impl in<br/>same directory?}
    
    Check -->|Yes| InProcess[Execute In-Process]
    Check -->|No| External[External Dependency]
    
    InProcess --> Runpy[Use runpy.run_path]
    Runpy --> Fast[✅ Fast - 15ms]
    Runpy --> NoFork[✅ No subprocess]
    Runpy --> Scalable[✅ Scales to 100+ agents]
    
    External --> HasPyProject{Has pyproject.toml?}
    HasPyProject -->|Yes| UV[Use UV subprocess]
    HasPyProject -->|No| System[Use system Python]
    
    UV --> Deps[Manages dependencies]
    System --> Direct[Direct execution]
    
    style InProcess fill:#9f9,stroke:#333
    style Runpy fill:#9f9,stroke:#333
    style Fast fill:#9f9,stroke:#333
    style NoFork fill:#9f9,stroke:#333
    style Scalable fill:#9f9,stroke:#333
    style External fill:#ff9,stroke:#333
```

**Code:**
```python
impl_in_same_dir = impl_file.parent == hook_dir

if impl_in_same_dir:
    # Same directory = self-contained hook
    # Execute in-process via runpy
    runpy.run_path(str(impl_file))
else:
    # External dependency (e.g., analytics middleware)
    # Spawn subprocess with UV
    subprocess.Popen(["uv", "run", ...])
```

### Performance Comparison

| Execution Method | Latency | Forks | Scalability |
|------------------|---------|-------|-------------|
| Bash script chain | 150ms | 4-5 | ❌ Fails at 20 agents |
| Subprocess Python | 80ms | 2-3 | ⚠️ Fails at 50 agents |
| **In-process runpy** | **15ms** | **0** | ✅ **100+ agents** |

### File Naming Convention

```
{hook-id}.py         # Wrapper (generated from template)
{hook-id}.impl.py    # Implementation (copied from primitive)
```

**Why `.impl.py` suffix?**
- Clearly distinguishes generated vs source files
- Prevents accidental wrapper execution
- Makes debugging easier (stack traces show `.impl.py`)
- Allows tooling to filter by purpose

## Examples

### Simple Hook (bash-validator)

```python
# bash-validator.py (Wrapper - 65 lines)
AGENT_CONFIG = r'''{"timeout": 5, "fail_on_error": true}'''
# ... inject config, execute impl via runpy

# bash-validator.impl.py (Implementation - 45 lines)
def validate_bash_command(command):
    if "rm -rf /" in command:
        return {"decision": "block", "reason": "Dangerous command"}
    return {"decision": "allow"}
```

### Complex Hook (hooks-collector)

```python
# hooks-collector.py (Wrapper - 150 lines)
AGENT_CONFIG = r'''{
    "middleware": [
        {"id": "normalizer", "path": "../../../../services/analytics/..."},
        {"id": "publisher", "path": "../../../../services/analytics/..."}
    ]
}'''
# ... inject config, execute impl via runpy

# hooks-collector.impl.py (Implementation - 250 lines)
class HooksCollectorOrchestrator:
    def __init__(self, agent_config):
        self.middleware = agent_config['middleware']
    
    async def execute(self, hook_event):
        # Orchestrate middleware pipeline
        for mw in self.middleware:
            result = await self.run_middleware(mw, hook_event)
        return {"action": "allow", "metadata": {...}}
```

## Testing Strategy

**Unit Tests** - Test impl files directly:
```python
# tests/unit/claude/hooks/test_hooks.py
def test_bash_validator():
    result = run_hook("bash-validator", {"command": "rm -rf /"})
    assert result["decision"] == "block"
```

**Integration Tests** - Test full wrapper+impl flow:
```python
def test_wrapper_integration():
    subprocess.run([
        "build/claude/.claude/hooks/security/bash-validator.py"
    ], input=json.dumps(fixture), check=True)
```

## Future Considerations

1. **Compiled Wrappers** - Pre-compile wrapper to bytecode (`.pyc`) for faster startup
2. **Shared Memory** - For high-volume scenarios, use shared memory for config
3. **Hot Reload** - Support reloading impl without restarting wrapper
4. **Metrics** - Add execution time tracking in wrapper layer

## References

- [ADR-013: Hybrid Hook Architecture](./013-hybrid-hook-architecture.md)
- [Python runpy documentation](https://docs.python.org/3/library/runpy.html)
- [Hook Build System](../../cli/src/providers/claude.rs)
- [Wrapper Template](../../cli/src/templates/hook_wrapper_with_config.py.template)

## Revision History

- **2025-11-25**: Initial version documenting wrapper+impl pattern

