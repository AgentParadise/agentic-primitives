# Hooks System Architecture Overview

A visual guide to understanding the agentic-primitives hook system.

## High-Level Architecture

```mermaid
graph TB
    subgraph "Development (You)"
        Dev[Write Generic Hook<br/>primitives/v1/hooks/]
    end
    
    subgraph "Configuration"
        AgentConfig[Agent-Specific Config<br/>providers/agents/claude-code/]
    end
    
    subgraph "Build System"
        Build[agentic-p build<br/>--provider claude]
    end
    
    subgraph "Output (Ready to Deploy)"
        Output[build/claude/.claude/<br/>✓ settings.json<br/>✓ hooks/ with wrappers + impls]
    end
    
    subgraph "Runtime (Claude Code)"
        Claude[Claude Code IDE]
        Event[Hook Event]
        Wrapper[Wrapper.py<br/>Config Injection]
        Impl[Impl.py<br/>Business Logic]
        Result[Decision]
    end
    
    Dev --> Build
    AgentConfig --> Build
    Build --> Output
    Output --> Claude
    
    Claude --> Event
    Event --> Wrapper
    Wrapper --> Impl
    Impl --> Result
    Result --> Claude
    
    style Dev fill:#9f9,stroke:#333
    style AgentConfig fill:#99f,stroke:#333
    style Build fill:#f99,stroke:#333
    style Output fill:#ff9,stroke:#333
    style Claude fill:#f9f,stroke:#333
```

## Three-Phase System

### Phase 1: Development

**Location:** `primitives/v1/hooks/{category}/{hook-id}/`

```mermaid
graph LR
    subgraph "Write Generic Hook"
        A[hook-id.hook.yaml<br/>Metadata] --> B[Define events, category]
        C[hook-id.py<br/>Implementation] --> D[Pure Python logic]
        E[README.md] --> F[Documentation]
    end
    
    style A fill:#9f9,stroke:#333
    style C fill:#9f9,stroke:#333
    style E fill:#9f9,stroke:#333
```

**Key Principle:** Hooks are **generic** - they work with any agent provider.

```python
# primitives/v1/hooks/security/bash-validator/bash-validator.py
def validate_bash_command(command):
    """Generic validation logic - no agent-specific code"""
    if "rm -rf /" in command:
        return {"decision": "block"}
    return {"decision": "allow"}
```

### Phase 2: Configuration

**Location:** `providers/agents/{agent-id}/hooks-config/{hook-id}.yaml`

```mermaid
graph LR
    subgraph "Agent Customization"
        A[Select Hook] --> B[Set Timeout]
        B --> C[Configure Middleware]
        C --> D[Set Fail Behavior]
    end
    
    style A fill:#99f,stroke:#333
    style B fill:#99f,stroke:#333
    style C fill:#99f,stroke:#333
    style D fill:#99f,stroke:#333
```

**Key Principle:** Agents **configure** generic hooks for their needs.

```yaml
# providers/agents/claude-code/hooks-config/bash-validator.yaml
agent: claude-code
hook_id: bash-validator

execution:
  timeout_sec: 5          # Claude wants fast response
  fail_on_error: true     # Block on validation failure
```

### Phase 3: Build

**Command:** `agentic-p build --provider claude`

```mermaid
flowchart LR
    A[Generic Hook] --> B[Build System]
    C[Agent Config] --> B
    B --> D[Wrapper.py<br/>+ Embedded Config]
    B --> E[Impl.py<br/>+ Business Logic]
    
    style A fill:#9f9,stroke:#333
    style C fill:#99f,stroke:#333
    style B fill:#f99,stroke:#333
    style D fill:#ff9,stroke:#333
    style E fill:#ff9,stroke:#333
```

**Output:**
```
build/claude/.claude/
├── settings.json                    # Hook registration
└── hooks/
    └── security/
        ├── bash-validator.py        # Wrapper (generated)
        └── bash-validator.impl.py   # Implementation (copied)
```

## Runtime Execution Flow

```mermaid
sequenceDiagram
    participant User
    participant Claude as Claude Code IDE
    participant Wrapper as bash-validator.py<br/>(Wrapper)
    participant Impl as bash-validator.impl.py<br/>(Implementation)
    
    User->>Claude: Types command: "rm -rf /"
    activate Claude
    
    Claude->>Claude: Trigger PreToolUse event
    Claude->>Claude: Check settings.json
    Note over Claude: Find hook for PreToolUse + Bash
    
    Claude->>Wrapper: Execute with stdin:<br/>{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}
    activate Wrapper
    
    Wrapper->>Wrapper: Parse AGENT_CONFIG<br/>(embedded in source)
    Note over Wrapper: No file I/O!<br/>Config already in memory
    
    Wrapper->>Wrapper: Inject config into event<br/>event['__agent_config__'] = config
    
    Wrapper->>Impl: Execute via runpy<br/>(in same process)
    Note over Wrapper,Impl: No subprocess spawn!<br/>15ms execution
    
    activate Impl
    Impl->>Impl: Extract config
    Impl->>Impl: Validate command
    Note over Impl: Found "rm -rf /"<br/>→ DANGEROUS!
    
    Impl-->>Wrapper: {"decision":"block","reason":"Dangerous"}
    deactivate Impl
    
    Wrapper-->>Claude: Output to stdout
    deactivate Wrapper
    
    Claude->>User: ⚠️ Command blocked:<br/>"Dangerous command detected"
    deactivate Claude
```

## Key Design Decisions

### 1. Generic Primitives, Agent Configuration

```mermaid
graph LR
    subgraph "❌ Old Approach"
        A1[claude-bash-validator] --> A2[Hard-coded for Claude]
        B1[openai-bash-validator] --> B2[Hard-coded for OpenAI]
        C1[gemini-bash-validator] --> C2[Hard-coded for Gemini]
    end
    
    subgraph "✅ New Approach"
        D1[bash-validator<br/>Generic Hook] --> D2[Claude Config]
        D1 --> D3[OpenAI Config]
        D1 --> D4[Gemini Config]
    end
    
    style A1 fill:#fbb,stroke:#333
    style B1 fill:#fbb,stroke:#333
    style C1 fill:#fbb,stroke:#333
    style D1 fill:#9f9,stroke:#333
```

**Benefits:**
- ✅ Write once, use everywhere
- ✅ Easy to add new agents
- ✅ Centralized logic updates

### 2. Build-Time Config Embedding

```mermaid
graph TB
    subgraph "❌ Runtime Loading"
        R1[Hook Execution] --> R2[Read YAML file]
        R2 --> R3[Parse config]
        R3 --> R4[Validate]
        R4 --> R5[Execute logic]
        R2 --> R6[❌ Slow I/O]
        R2 --> R7[❌ Runtime errors]
    end
    
    subgraph "✅ Build-Time Embedding"
        B1[Build Time] --> B2[Read YAML]
        B2 --> B3[Validate config]
        B3 --> B4[Embed in source]
        
        E1[Hook Execution] --> E2[Parse embedded JSON]
        E2 --> E3[Execute logic]
        E2 --> E4[✅ Fast - no I/O]
        E2 --> E5[✅ Build-time errors]
    end
    
    style R1 fill:#fbb,stroke:#333
    style B1 fill:#9f9,stroke:#333
    style E1 fill:#9f9,stroke:#333
```

### 3. In-Process Execution

```mermaid
graph TB
    subgraph "❌ Subprocess Cascade"
        S1[Claude] -->|fork| S2[Wrapper]
        S2 -->|fork| S3[UV]
        S3 -->|fork| S4[Python]
        S4 -->|fork| S5[Impl]
        
        S6[100ms latency]
        S7[Resource exhaustion]
        S8[BlockingIOError]
    end
    
    subgraph "✅ In-Process with runpy"
        I1[Claude] -->|fork| I2[Wrapper]
        I2 -->|runpy| I3[Impl<br/>same process]
        
        I4[15ms latency]
        I5[Scales to 100+ agents]
        I6[No resource issues]
    end
    
    style S1 fill:#fbb,stroke:#333
    style I1 fill:#9f9,stroke:#333
```

## Hybrid Architecture

The system supports both **universal** and **specialized** hooks running in parallel:

```mermaid
graph TD
    Event[Hook Event:<br/>PreToolUse + Bash + rm -rf /] --> Parallel{Parallel Execution}
    
    Parallel --> Universal[hooks-collector<br/>Universal Observability]
    Parallel --> Specialized[bash-validator<br/>Specialized Security]
    
    Universal --> U1[Event Normalization]
    U1 --> U2[Analytics Publishing]
    U2 --> U3[Always allows]
    U3 --> UR[Decision: allow<br/>+ metadata]
    
    Specialized --> S1[Pattern Matching]
    S1 --> S2[Command Validation]
    S2 --> S3{Dangerous?}
    S3 -->|Yes| SR1[Decision: block]
    S3 -->|No| SR2[Decision: allow]
    
    UR --> Merge[Merge Results]
    SR1 --> Merge
    SR2 --> Merge
    
    Merge --> Final{Any block?}
    Final -->|Yes| Block[❌ BLOCK OPERATION]
    Final -->|No| Allow[✅ ALLOW OPERATION]
    
    style Universal fill:#9cf,stroke:#333
    style Specialized fill:#f99,stroke:#333
    style Block fill:#fbb,stroke:#333
    style Allow fill:#9f9,stroke:#333
```

## File Organization

```mermaid
graph TB
    subgraph "Source Code"
        P[primitives/v1/hooks/<br/>✓ Generic implementations<br/>✓ Version controlled<br/>✓ Testable]
        
        C[providers/agents/<br/>✓ Agent-specific configs<br/>✓ Timeouts, middleware<br/>✓ Execution preferences]
    end
    
    subgraph "Build System"
        B[agentic-p build]
    end
    
    subgraph "Build Output"
        W[{hook}.py Wrappers<br/>✓ Generated from template<br/>✓ Embedded config<br/>✓ Injection logic]
        
        I[{hook}.impl.py Impls<br/>✓ Copied from primitives<br/>✓ Pure business logic<br/>✓ No agent-specific code]
    end
    
    P --> B
    C --> B
    B --> W
    B --> I
    
    style P fill:#9f9,stroke:#333
    style C fill:#99f,stroke:#333
    style B fill:#f99,stroke:#333
    style W fill:#ff9,stroke:#333
    style I fill:#ff9,stroke:#333
```

## Performance Characteristics

### Latency Breakdown

```mermaid
graph LR
    subgraph "Total Hook Execution: 15-20ms"
        A[Claude Invoke:<br/>2ms] --> B[Wrapper Init:<br/>3ms]
        B --> C[Config Parse:<br/>1ms]
        C --> D[runpy Execute:<br/>5ms]
        D --> E[Business Logic:<br/>3-8ms]
        E --> F[JSON Output:<br/>1ms]
    end
    
    style A fill:#9f9,stroke:#333
    style F fill:#9f9,stroke:#333
```

### Scalability

| Metric | Old System | New System |
|--------|------------|------------|
| **Subprocess spawns per hook** | 3-5 | 0 (in-process) |
| **Latency (avg)** | 100ms | 15ms |
| **Max concurrent agents** | ~20 | 100+ |
| **Resource exhaustion** | Yes (BlockingIOError) | No |
| **Config load time** | 20ms (YAML I/O) | <1ms (embedded) |

## Development Workflow

```mermaid
flowchart TD
    Start[New Hook Idea] --> Create[Create primitive<br/>in primitives/v1/hooks/]
    
    Create --> WriteYAML[Write {hook}.hook.yaml<br/>Define metadata, events]
    WriteYAML --> WriteImpl[Write {hook}.py<br/>Implement logic]
    WriteImpl --> Test[Write tests<br/>tests/unit/claude/hooks/]
    
    Test --> Config[Create agent config<br/>providers/agents/claude-code/]
    Config --> Build[cargo run -- build --provider claude]
    
    Build --> Verify{Tests pass?}
    Verify -->|No| Debug[Debug]
    Debug --> WriteImpl
    
    Verify -->|Yes| Install[Install to project<br/>cp build/claude/.claude ~/project/]
    Install --> Manual[Manual testing in Claude]
    
    Manual --> Works{Works?}
    Works -->|No| Debug
    Works -->|Yes| Commit[Commit changes]
    
    style Start fill:#9f9,stroke:#333
    style Test fill:#99f,stroke:#333
    style Verify fill:#ff9,stroke:#333
    style Commit fill:#9f9,stroke:#333
```

## Related Documentation

- **Deep Dives:**
  - [ADR-014: Wrapper+Impl Pattern](../adrs/014-wrapper-impl-pattern.md)
  - [ADR-013: Hybrid Hook Architecture](../adrs/013-hybrid-hook-architecture.md)

- **Reference:**
  - [Build Output Structure](../_reference/build-output-structure.md)
  - [Hook Development Guide](../_reference/hook-development.md)

- **Examples:**
  - [USAGE_EXAMPLES.md](../../USAGE_EXAMPLES.md)
  - [INSTALLATION.md](../../INSTALLATION.md)

