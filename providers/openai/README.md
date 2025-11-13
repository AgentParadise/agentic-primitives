# OpenAI Provider

Model configurations for OpenAI's GPT family of models.

## Overview

OpenAI models offer strong code generation, multi-modal capabilities, and structured output support. The GPT-4 family excels at function calling and JSON mode for reliable agentic workflows.

## Available Models

### GPT-4 Turbo with Vision (`openai/gpt-codex`)
**API Name**: `gpt-4-turbo-2024-11-20`

OpenAI's flagship coding model with vision capabilities. Best choice for most OpenAI-based agentic tasks.

- **Context Window**: 128k tokens
- **Speed**: Fast
- **Quality**: High
- **Pricing**: $10/1M input, $30/1M output
- **Best For**: Agents, commands, code-heavy tasks

**Strengths**:
- Excellent code generation and debugging
- Multi-modal understanding (vision + text)
- Structured output generation (JSON mode)
- Strong function calling
- Large context window

**Recommended For**:
- Production agents requiring code generation
- Commands with multi-modal inputs
- Tasks requiring structured outputs
- Tool-heavy workflows
- OpenAI-native deployments

---

### GPT-4.5 Preview (`openai/gpt-large`)
**API Name**: `gpt-4.5-preview`

Latest preview model with extended context and enhanced capabilities. Pricing and features subject to change.

- **Context Window**: 256k tokens (extended)
- **Speed**: Medium
- **Quality**: Highest
- **Pricing**: $20/1M input, $60/1M output (placeholder)
- **Best For**: Cutting-edge tasks, long-context reasoning

**Strengths**:
- Latest OpenAI capabilities
- Extended 256k context window
- Enhanced reasoning abilities
- Improved code generation
- Better instruction following

**Recommended For**:
- Cutting-edge experimental tasks
- Long-context reasoning (large codebases)
- High-quality code generation
- Research and exploration
- Preview of future capabilities

**Note**: Preview model - features and pricing may change. Use for experimentation.

---

### OpenAI o1 Preview (`openai/o1`)
**API Name**: `o1-preview`

Reasoning-focused model with built-in chain-of-thought. Best for complex planning and analysis.

- **Context Window**: 128k tokens
- **Speed**: Slow
- **Quality**: Highest (reasoning)
- **Pricing**: $15/1M input, $60/1M output
- **Best For**: Meta-prompts, planning, complex reasoning

**Strengths**:
- Advanced reasoning and planning
- Chain-of-thought processing (built-in)
- Complex problem-solving
- Mathematical reasoning
- Multi-step analysis
- Strategic planning

**Recommended For**:
- Meta-prompts generating other primitives
- Complex architectural planning
- Algorithm design and optimization
- Research and deep analysis
- Tasks requiring explicit reasoning steps

**Limitations**:
- ❌ No vision support
- ❌ No function calling (reasoning-optimized)
- ⏱️ Slower than GPT-4 models

**Note**: Optimized for reasoning over speed. Not suitable for tool-heavy agents.

---

## Model Selection Guide

### By Primitive Type

| Primitive Type | Primary Model | Alternative | Reasoning |
|---------------|--------------|-------------|-----------|
| **Agents** | gpt-codex | gpt-large | Agents need code gen + tools |
| **Commands** | gpt-codex | gpt-large | Commands need reliable execution |
| **Skills** | gpt-codex | - | Skills are simple, use default |
| **Meta-Prompts** | o1 | gpt-large | Meta-prompts need reasoning |

### By Task Complexity

| Complexity | Model | Cost | Notes |
|-----------|-------|------|-------|
| **Simple** | gpt-codex | $$ | Standard coding tasks |
| **Medium** | gpt-codex | $$ | Most production work |
| **Complex** | o1 | $$$ | Deep reasoning required |
| **Cutting-edge** | gpt-large | $$$$ | Latest capabilities |

### By Capability Requirements

| Requirement | Model | Notes |
|------------|-------|-------|
| **Vision** | gpt-codex, gpt-large | Image understanding |
| **Function Calling** | gpt-codex, gpt-large | Tool integration |
| **Reasoning** | o1 | Built-in CoT |
| **Long Context** | gpt-large | 256k tokens |
| **Structured Output** | gpt-codex | JSON mode |

---

## Pricing Comparison

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Relative Cost |
|-------|----------------------|------------------------|---------------|
| gpt-codex | $10.00 | $30.00 | 1x (baseline) |
| o1 | $15.00 | $60.00 | 1.8x |
| gpt-large | $20.00 | $60.00 | 2.4x |

*Note: gpt-large pricing is placeholder and subject to change.*

---

## Usage Examples

### In Primitive Metadata

Reference models using the `provider/model` format:

```yaml
# In a prompt's meta.yaml
preferred_models:
  - openai/gpt-codex   # Primary model
  - openai/gpt-large   # Fallback for complex cases
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

### GPT-4 Turbo (gpt-codex)
- ✅ **Vision**: Image understanding and analysis
- ✅ **Function Calling**: Structured tool use
- ✅ **JSON Mode**: Guaranteed structured output
- ✅ **Streaming**: Real-time response generation
- ✅ **128k Context**: Large codebases
- ✅ **System Prompts**: Behavior configuration

### GPT-4.5 Preview (gpt-large)
- ✅ **Vision**: Enhanced image understanding
- ✅ **Function Calling**: Advanced tool use
- ✅ **JSON Mode**: Structured output
- ✅ **Streaming**: Real-time responses
- ✅ **256k Context**: Extended context window
- ✅ **Enhanced Reasoning**: Improved capabilities

### o1 Preview (o1)
- ❌ **Vision**: Not supported
- ❌ **Function Calling**: Not supported (reasoning-focused)
- ✅ **Chain-of-Thought**: Built-in reasoning
- ✅ **Streaming**: Real-time responses
- ✅ **128k Context**: Large context
- ✅ **Advanced Reasoning**: Core strength

---

## Best Practices

### 1. Use gpt-codex as Default
For most OpenAI-based primitives, start with gpt-codex (GPT-4 Turbo).

### 2. Use o1 for Reasoning Tasks
Use o1 for:
- Meta-prompt generation
- Complex planning
- Architectural analysis
- Algorithm design
- Tasks requiring explicit reasoning

### 3. Leverage JSON Mode
For structured outputs:

```yaml
# In tool or hook implementations
output_format: json
schema: <json-schema>
```

### 4. Function Calling for Tools
Use function calling for reliable tool integration:

```yaml
# In tool metadata
supports_function_calling: true
```

### 5. Monitor Costs
Track token usage:
- gpt-codex for standard work
- o1 for critical reasoning only
- gpt-large for experiments

---

## OpenAI-Specific Features

### JSON Mode
Guarantee valid JSON responses:

```yaml
# In provider configuration
response_format:
  type: json_object
```

### Function Calling
Native tool integration:

```yaml
# Tools are automatically converted to OpenAI function format
tools:
  - id: file-write
    name: write_file
    description: "Write content to a file"
    parameters:
      # JSON Schema for parameters
```

### Seed Parameter
Deterministic outputs for testing:

```yaml
# For reproducible results
seed: 12345
```

---

## Limitations

### Compared to Claude

| Feature | OpenAI | Claude |
|---------|--------|--------|
| Context Window | 128k-256k | 200k |
| Vision | ✅ gpt-codex, gpt-large | ✅ All Claude 3+ |
| Function Calling | ✅ gpt-codex, gpt-large | ✅ All Claude 3+ |
| Cost (baseline) | $10/$30 | $3/$15 |
| Hooks Support | Limited (external) | Native |

### Hook System Notes

OpenAI does not have native hook support like Claude. For hook integration:
1. Use external wrapper scripts
2. Implement middleware as pre/post-processing
3. Consider Claude for hook-heavy workflows

---

## Version Updates

OpenAI models are versioned by date (e.g., `2024-11-20`). Always use the latest stable version.

When new versions are released:
1. Update the `api_name` and `version` fields
2. Test with representative primitives
3. Update pricing if changed
4. Document any capability changes
5. Check for deprecated features

---

## Migration from Claude

If migrating primitives from Claude to OpenAI:

1. **Context Window**: Most fit within 128k, but check for long prompts
2. **Function Calling**: Similar to Claude's tool use
3. **JSON Mode**: Use for structured outputs
4. **Hooks**: Implement as external scripts
5. **Vision**: Supported in gpt-codex and gpt-large

### Example Migration

```yaml
# Before (Claude)
preferred_models:
  - claude/sonnet

# After (OpenAI)
preferred_models:
  - openai/gpt-codex
```

---

## Related Documentation

- [Provider Architecture](../../docs/adrs/004-provider-scoped-models.md)
- [Model Selection Guide](../../docs/architecture.md#model-selection)
- [OpenAI Pricing](https://openai.com/pricing)
- [OpenAI API Docs](https://platform.openai.com/docs)

---

## Support

For issues with model configurations:
1. Check the [ADR on provider-scoped models](../../docs/adrs/004-provider-scoped-models.md)
2. Validate configs against `schemas/model-config.schema.json`
3. File an issue if configurations need updates
4. Check OpenAI docs for latest model capabilities

