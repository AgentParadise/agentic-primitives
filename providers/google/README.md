# Google Gemini Models

Provider-scoped model configurations for Google's Gemini models.

## Available Models

### Current Generation (2.5)

- **Gemini 2.5 Pro** (`gemini-pro`)
  - State-of-the-art thinking model
  - 1M token context window
  - Best for: complex reasoning in code, math, STEM
  - Recommended for: agents, meta-prompts, research

- **Gemini 2.5 Flash** (`gemini-flash`)
  - Best price-performance balance
  - 1M token context window
  - Fast and intelligent
  - Recommended for: agents, commands, production systems

- **Gemini 2.5 Flash-Lite** (`gemini-flash-lite`)
  - Fastest and most cost-efficient
  - 1M token context window
  - Ultra-fast responses
  - Recommended for: skills, simple commands, high-volume

## Model Selection Guide

- **For Agents**: Use `gemini-flash` (best value) or `gemini-pro` (max capability)
- **For Commands**: Use `gemini-flash` for general tasks
- **For Skills**: Use `gemini-flash-lite` for cost efficiency
- **For Meta-prompts**: Use `gemini-pro` for complex reasoning
- **For High-Volume**: Use `gemini-flash-lite` for best throughput/cost

## Key Advantages

- **Long Context**: All models support 1M token context window
- **Thinking Capability**: Native thinking/reasoning support across all models
- **Cost-Effective**: Excellent price-performance, especially Flash and Flash-Lite
- **Multimodal**: Built-in vision, audio, and video support
- **Code Execution**: Native code execution capabilities

## Usage in Primitives

Reference models using the format: `google/model-id`

```yaml
defaults:
  preferred_models:
    - google/gemini-flash
    - google/gemini-pro
```

## Pricing (as of November 2025)

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| Gemini 2.5 Pro | $1.25 | $5.00 |
| Gemini 2.5 Flash | $0.15 | $0.60 |
| Gemini 2.5 Flash-Lite | $0.075 | $0.30 |

## Links

- [Gemini API Documentation](https://ai.google.dev/gemini-api/docs)
- [Model Details](https://ai.google.dev/gemini-api/docs/models)
- [Google AI Studio](https://aistudio.google.com/)

