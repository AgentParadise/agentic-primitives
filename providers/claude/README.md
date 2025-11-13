# Claude Models

Provider-scoped model configurations for Anthropic's Claude models.

## Available Models

- [Claude Models Documentation](https://docs.claude.com/en/docs/about-claude/models/overview)

### Current Generation (4.5 / 4.1)

- **Claude Sonnet 4.5** (`sonnet`)
  - Best balance of intelligence, speed, and cost
  - Released: September 29, 2025
  - Exceptional for coding and agentic tasks
  - Context: 200K tokens (1M with beta header)
  - Recommended for: agents, commands, meta-prompts, production

- **Claude Haiku 4.5** (`haiku`)
  - Fastest with near-frontier intelligence
  - Released: October 1, 2025
  - Low latency, high throughput
  - Context: 200K tokens
  - Recommended for: skills, real-time applications, high-volume

- **Claude Opus 4.1** (`opus`)
  - Exceptional model for specialized reasoning
  - Released: August 5, 2025
  - Highest quality analysis
  - Context: 200K tokens
  - Recommended for: agents, meta-prompts, mission-critical tasks

## Model Selection Guide

- **For Agents**: Use `sonnet` (recommended default) or `opus` (specialized reasoning)
- **For Commands**: Use `sonnet` for complex tasks, `haiku` for simpler ones
- **For Skills**: Use `haiku` for cost-effective real-time processing
- **For Meta-prompts**: Use `sonnet` or `opus` for maximum reasoning
- **For High-Volume**: Use `haiku` for best throughput and cost

## Key Capabilities (All Models)

- ✅ **Extended Thinking**: Advanced reasoning capabilities
- ✅ **Vision**: Image understanding and analysis
- ✅ **Function Calling**: Native tool use support
- ✅ **Streaming**: Real-time response streaming
- ✅ **Long Context**: 200K token context window (1M for Sonnet with beta)

## Usage in Primitives

Reference models using the format: `claude/model-id`

```yaml
defaults:
  preferred_models:
    - claude/sonnet  # Recommended default
    - claude/haiku   # For cost efficiency
    - claude/opus    # For maximum quality
```

## Pricing (as of November 2025)

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Use Case |
|-------|----------------------|------------------------|----------|
| Sonnet 4.5 | $3.00 | $15.00 | Best overall value |
| Haiku 4.5 | $1.00 | $5.00 | Speed & efficiency |
| Opus 4.1 | $15.00 | $75.00 | Specialized reasoning |

## Why Choose Claude?

- **Intelligence**: State-of-the-art reasoning and analysis
- **Reliability**: Production-tested and consistent
- **Safety**: Built with Constitutional AI principles
- **Context**: Industry-leading context windows
- **Versatility**: Excellent across coding, analysis, and creative tasks

## Links

- [Claude Documentation](https://docs.anthropic.com/)
- [Model Overview](https://docs.anthropic.com/en/docs/about-claude/models)
- [API Reference](https://docs.anthropic.com/en/api)
- [Anthropic Console](https://console.anthropic.com/)
