# OpenAI Models

Provider-scoped model configurations for OpenAI's GPT models.

## Available Models

- [OpenAI Models Documentation](https://platform.openai.com/docs/models)

### Flagship Models

- **GPT-5.1** (`gpt-5.1`)
  - Best model for coding and agentic tasks
  - Configurable reasoning effort
  - Recommended for: agents, meta-prompts, complex commands

- **GPT-5.1 Codex** (`gpt-codex`)
  - Optimized specifically for agentic coding
  - Superior code generation and debugging
  - Recommended for: development agents, coding commands

### Efficient Models

- **GPT-5 mini** (`gpt-5-mini`)
  - Faster, cost-efficient version of GPT-5
  - Good for well-defined tasks
  - Recommended for: commands, skills

- **GPT-4.1** (`gpt-4.1`)
  - Smartest non-reasoning model
  - Fast and reliable
  - Recommended for: general commands, skills

## Model Selection Guide

- **For Agents**: Use `gpt-5.1` or `gpt-codex` (if coding-focused)
- **For Commands**: Use `gpt-5-mini` for general tasks, `gpt-codex` for coding
- **For Skills**: Use `gpt-4.1` or `gpt-5-mini` for cost efficiency
- **For Meta-prompts**: Use `gpt-5.1` for maximum reasoning capability

## Usage in Primitives

Reference models using the format: `openai/model-id`

```yaml
defaults:
  preferred_models:
    - openai/gpt-5.1
    - openai/gpt-codex
```

## Pricing (as of November 2025)

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| GPT-5.1 | $15.00 | $60.00 |
| GPT-5.1 Codex | $15.00 | $60.00 |
| GPT-5 mini | $3.00 | $12.00 |
| GPT-4.1 | $2.50 | $10.00 |

## Links

- [OpenAI Platform Documentation](https://platform.openai.com/docs/models)
- [Model Comparison](https://platform.openai.com/docs/models/compare)
- [API Reference](https://platform.openai.com/docs/api-reference)
