---
provider: Anthropic
last_updated: 2025-12-02
model_card: https://platform.claude.com/docs/en/about-claude/models/overview
---

# Anthropic Model Provider

Anthropic provides the Claude family of large language models, designed with a focus on safety, reliability, and interpretability.

## Model Card

**Official Documentation:** [Claude Models Overview](https://platform.claude.com/docs/en/about-claude/models/overview)

Last Updated: December 2, 2025

## Model Registry Architecture

See [ADR-018: Model Registry Architecture](../../docs/adrs/018-model-registry-architecture.md) for the complete design.

**Key Concepts:**
- **Simple Aliases** (`sonnet`, `claude-sonnet`): Version-agnostic, auto-upgrade with new releases
- **Model IDs** (`claude-4-5-sonnet`): Family reference, defined in YAML files
- **API Names** (`claude-sonnet-4-5-20250929`): Immutable, pricing tied here

## Available Models

### Current Generation (Claude 4.5)

| Model | API Name | Simple Aliases | Input | Output | Best For |
|-------|----------|----------------|-------|--------|----------|
| **Claude Sonnet 4.5** | `claude-sonnet-4-5-20250929` | `sonnet`, `claude-sonnet` | $3/M | $15/M | Complex agents & coding |
| **Claude Haiku 4.5** | `claude-haiku-4-5-20251001` | `haiku`, `claude-haiku` | $1/M | $5/M | Speed & efficiency |
| **Claude Opus 4.5** | `claude-opus-4-5-20251101` | `opus`, `claude-opus` | $5/M | $25/M | Maximum intelligence |

### Legacy Models

| Model | Status | Model Type | Notes |
|-------|--------|------------|-------|
| Claude Opus 4.1 | Legacy | Opus | Superseded by 4.5 |
| Claude Sonnet 4 | Legacy | Sonnet | Superseded by 4.5 |
| Claude Sonnet 3.7 | Legacy | Sonnet | Superseded by 4.5 |
| Claude Opus 4 | Legacy | Opus | Superseded by 4.5 |
| Claude Haiku 3.5 | Legacy | Haiku | Superseded by 4.5 |
| Claude 3 Opus | Legacy | Opus | Significantly outdated |
| Claude 3 Sonnet | Legacy | Sonnet | Significantly outdated |
| Claude 3 Haiku | Legacy | Haiku | Significantly outdated |

> **Migration Note**: For any legacy model, use the current model of the same type. See `config.yaml` → `current_models` for the latest recommendations.

## Capabilities

All current Claude models support:
- ✅ **Extended Thinking**: Advanced reasoning capabilities
- ✅ **Vision**: Image understanding and analysis
- ✅ **Function Calling**: Tool use support
- ✅ **Streaming**: Real-time response streaming
- ✅ **JSON Mode**: Structured output generation
- ✅ **Long Context**: 200K token window (1M for Sonnet 4.5 with beta)
- ✅ **Priority Tier**: Priority access to API

## Model Selection Guide

- **For Agents**: Use `sonnet` (recommended) or `opus` (maximum quality)
- **For Commands**: Use `sonnet` for complex, `haiku` for simple
- **For Skills**: Use `haiku` for cost-effective real-time processing
- **For Meta-prompts**: Use `sonnet` or `opus` for maximum reasoning
- **For High-Volume**: Use `haiku` for best throughput and cost

**Note**: Use simple aliases (`sonnet`, `opus`, `haiku`) in your code. When new model versions are released, they auto-upgrade. Current mappings are defined in `config.yaml` → `current_models`.

## API Aliases vs Snapshots

Anthropic provides two ways to reference models:

- **Aliases** (e.g., `claude-sonnet-4-5`): Auto-update to latest snapshot within ~1 week
- **Snapshots** (e.g., `claude-sonnet-4-5-20250929`): Immutable, specific version

**Recommendation**: Use snapshots (specific dates) for production to ensure consistent behavior. Set `prefer_alias: false` in model configs (default).

## Knowledge Cutoffs

- **Reliable Knowledge Cutoff**: Date through which knowledge is most extensive and reliable
- **Training Data Cutoff**: Broader date range of training data used

See [Anthropic's Transparency Hub](https://www.anthropic.com/transparency) for details.

## Usage in Primitives

**Recommended: Use simple aliases** (version-agnostic, auto-upgrade):

```yaml
defaults:
  preferred_models:
    - sonnet        # Recommended default (currently Claude Sonnet 4.5)
    - haiku         # For cost efficiency (currently Claude Haiku 4.5)
    - opus          # For maximum quality (currently Claude Opus 4.5)
```

**Alternative: Use explicit model IDs** (if you need to pin):

```yaml
defaults:
  preferred_models:
    - anthropic/claude-4-5-sonnet   # Pinned to 4.5 family
    - anthropic/claude-4-5-haiku
    - anthropic/claude-4-5-opus
```

## Authentication

Set your API key:

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

## Rate Limits

Default tier limits:
- **Requests:** 50 per minute
- **Tokens:** 100,000 per minute

Contact Anthropic support for higher limits and Priority Tier access.

## Documentation

- [Claude Models Overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Claude Documentation](https://docs.anthropic.com/)
- [API Reference](https://docs.anthropic.com/en/api)
- [Pricing](https://www.anthropic.com/pricing)
- [Anthropic Console](https://console.anthropic.com/)

## Updating Models

For instructions on reviewing and updating model configurations, see [UPDATE_GUIDE.md](./UPDATE_GUIDE.md).

## Support

- **Website:** https://anthropic.com
- **Support:** https://support.anthropic.com
- **Discord:** https://discord.gg/anthropic
- **Email:** support@anthropic.com
