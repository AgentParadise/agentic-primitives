# agentic-agent

Instrumented wrapper for AI agent SDKs with observability and metrics.

## Installation

```bash
# Core only (requires claude-agent-sdk separately)
pip install agentic-agent

# With Claude Agent SDK
pip install agentic-agent[claude]

# With HookClient for event emission
pip install agentic-agent[hooks]

# With SecurityPolicy for tool validation
pip install agentic-agent[security]

# Everything
pip install agentic-agent[all]
```

## Quick Start

```python
from agentic_agent import InstrumentedAgent

agent = InstrumentedAgent(model="claude-sonnet-4-20250514")
result = await agent.run("Create a hello world file")

print(f"Response: {result.text}")
print(f"Tokens: {result.metrics.total_tokens}")
print(f"Cost: ${result.metrics.total_cost_usd:.6f}")
print(f"Tools used: {len(result.tool_calls)}")
```

## Features

### Token Usage Tracking

```python
result = await agent.run("Write some code")
print(f"Input tokens: {result.metrics.input_tokens}")
print(f"Output tokens: {result.metrics.output_tokens}")
print(f"Cache tokens: {result.metrics.cache_read_tokens}")
```

### Tool Call Tracking

```python
for tool_call in result.tool_calls:
    print(f"Tool: {tool_call.tool_name}")
    print(f"Input: {tool_call.tool_input}")
    print(f"Success: {tool_call.success}")
```

### Cost Estimation

Built-in pricing for common models:

```python
from agentic_agent import get_model_pricing, list_models

# See available models
print(list_models())

# Get pricing for a model
pricing = get_model_pricing("claude-sonnet-4-20250514")
cost = pricing.calculate_cost(input_tokens=1000, output_tokens=500)
```

### Integration with HookClient

```python
from agentic_hooks import HookClient
from agentic_hooks.backends import JSONLBackend

backend = JSONLBackend(output_path=".agentic/events.jsonl")

async with HookClient(backend=backend) as hook_client:
    agent = InstrumentedAgent(hook_client=hook_client)
    result = await agent.run("Create a file")
    # Events automatically emitted to the backend
```

### Integration with SecurityPolicy

```python
from agentic_security import SecurityPolicy

policy = SecurityPolicy.with_defaults()
agent = InstrumentedAgent(security_policy=policy)

result = await agent.run("Run rm -rf /")
# Tool call will be blocked and recorded
```

## Synchronous Usage

```python
agent = InstrumentedAgent()
result = agent.run_sync("Create a file")
```

## License

MIT
