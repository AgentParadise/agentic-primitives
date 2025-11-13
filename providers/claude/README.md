# Claude Provider

Model configurations for Anthropic's Claude family of models.

## Overview

Claude models are optimized for agentic workflows with excellent instruction following, code generation, and long context support. All Claude 3+ models support vision, function calling, and 200k token context windows.

## Available Models

### Claude 3.5 Sonnet (`claude/sonnet`)
**API Name**: `claude-3-5-sonnet-20241022`

The balanced choice for most agentic tasks. Combines high quality with fast performance and reasonable cost.

- **Context Window**: 200k tokens
- **Speed**: Fast
- **Quality**: High
- **Pricing**: $3/1M input, $15/1M output
- **Best For**: Agents, commands, general-purpose coding tasks

**Strengths**:
- Excellent code generation and refactoring
- Strong instruction following
- Long context reasoning
- Reliable tool/function calling
- Multi-turn conversation handling

**Recommended For**:
- Production agents requiring reliable code generation
- Commands that need balanced speed and quality
- Complex reasoning with large context
- General-purpose agentic work

---

### Claude 3 Opus (`claude/opus`)
**API Name**: `claude-3-opus-20240229`

The highest quality model in the Claude family. Best for tasks requiring maximum reasoning ability.

- **Context Window**: 200k tokens
- **Speed**: Medium
- **Quality**: Highest
- **Pricing**: $15/1M input, $75/1M output
- **Best For**: Meta-prompts, complex planning, high-stakes decisions

**Strengths**:
- Advanced reasoning and analysis
- Creative problem-solving
- Complex multi-step planning
- Nuanced understanding
- High-quality code generation

**Recommended For**:
- Meta-prompts that generate other primitives
- Complex architectural planning
- Research and deep analysis
- High-stakes code generation
- Critical decision-making

---

### Claude 3 Haiku (`claude/haiku`)
**API Name**: `claude-3-haiku-20240307`

The fastest and most cost-effective Claude model. Ideal for simple tasks and high-throughput scenarios.

- **Context Window**: 200k tokens
- **Speed**: Fastest
- **Quality**: Medium
- **Pricing**: $0.25/1M input, $1.25/1M output
- **Best For**: Skills, simple commands, rapid iteration

**Strengths**:
- Speed and efficiency
- Cost-effective processing
- High-throughput workloads
- Simple task execution
- Rapid prototyping

**Recommended For**:
- Skills and simple command execution
- Rapid prototyping and iteration
- High-volume operations
- Cost-sensitive tasks
- Quick context lookups

---

## Model Selection Guide

### By Primitive Type

| Primitive Type | Primary Model | Alternative | Reasoning |
|---------------|--------------|-------------|-----------|
| **Agents** | Sonnet | Opus | Agents need balanced quality and speed |
| **Commands** | Sonnet | Haiku | Commands need reliable execution |
| **Skills** | Haiku | Sonnet | Skills are often simple, cost-effective |
| **Meta-Prompts** | Opus | Sonnet | Meta-prompts require max reasoning |

### By Task Complexity

| Complexity | Model | Cost | Notes |
|-----------|-------|------|-------|
| **Simple** | Haiku | $ | Quick tasks, high volume |
| **Medium** | Sonnet | $$ | Most production work |
| **Complex** | Opus | $$$$ | Critical decisions, deep reasoning |

### By Budget

| Budget Priority | Model Choice | Trade-offs |
|----------------|-------------|------------|
| **Cost-Optimized** | Haiku | Lower quality, but 12x cheaper than Opus |
| **Balanced** | Sonnet | Best quality/cost ratio |
| **Quality-First** | Opus | 5x more expensive, highest quality |

---

## Pricing Comparison

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Relative Cost |
|-------|----------------------|------------------------|---------------|
| Haiku | $0.25 | $1.25 | 1x (baseline) |
| Sonnet | $3.00 | $15.00 | 12x |
| Opus | $15.00 | $75.00 | 60x |

---

## Usage Examples

### In Primitive Metadata

Reference models using the `provider/model` format:

```yaml
# In a prompt's meta.yaml
preferred_models:
  - claude/sonnet      # Primary model
  - claude/opus        # Fallback for complex cases
```

### Model Resolution

The CLI will resolve model references to full configurations:

```bash
# Inspect a primitive and see resolved models
agentic inspect python/python-pro

# Output includes resolved model details:
# - API name
# - Capabilities
# - Pricing
# - Recommendations
```

---

## Capabilities

All Claude 3+ models support:

- ✅ **Vision**: Image understanding and analysis
- ✅ **Function Calling**: Structured tool use
- ✅ **Streaming**: Real-time response generation
- ✅ **200k Context**: Large codebases and conversations
- ✅ **System Prompts**: Agentic behavior configuration

---

## Best Practices

### 1. Start with Sonnet
Unless you have specific needs, start with Sonnet for balanced performance.

### 2. Upgrade to Opus for Complex Tasks
Use Opus for:
- Meta-prompt generation
- Architectural decisions
- Complex refactoring
- Research and analysis

### 3. Downgrade to Haiku for Simple Tasks
Use Haiku for:
- Simple commands
- Skills (context injection)
- High-volume operations
- Cost-sensitive workflows

### 4. Test Across Models
Use the `preferred_models` array to specify fallback options:

```yaml
preferred_models:
  - claude/sonnet    # Try this first
  - claude/haiku     # Fallback for cost optimization
```

### 5. Monitor Costs
Track token usage and costs. Consider:
- Haiku for development/testing
- Sonnet for production
- Opus for critical paths only

---

## Version Updates

Claude models are versioned by date (e.g., `20241022`). Always use the latest stable version specified in these configs.

When new versions are released:
1. Update the `api_name` and `version` fields
2. Test with representative primitives
3. Update pricing if changed
4. Document any capability changes

---

## Related Documentation

- [Provider Architecture](../../docs/adrs/004-provider-scoped-models.md)
- [Model Selection Guide](../../docs/architecture.md#model-selection)
- [Pricing Calculator](https://anthropic.com/pricing)
- [Claude API Docs](https://docs.anthropic.com/)

---

## Support

For issues with model configurations:
1. Check the [ADR on provider-scoped models](../../docs/adrs/004-provider-scoped-models.md)
2. Validate configs against `schemas/model-config.schema.json`
3. File an issue if configurations need updates

