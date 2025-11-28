---
provider: Anthropic
last_updated: 2025-11-24
audience: AI Agents
purpose: Model Maintenance Guide
---

# Anthropic Models Update Guide

**For AI Agents Maintaining This Repository**

This guide helps you systematically review and update Anthropic model configurations to match the latest official documentation.

## Update Frequency

Check for updates:
- **Monthly**: Routine check for new models or changes
- **On Announcement**: When Anthropic announces new models
- **On Issue Report**: When users report outdated information

## Step 1: Review Official Documentation

Visit: https://platform.claude.com/docs/en/about-claude/models/overview

### Key Information to Extract

From the **Latest Models Comparison** table:
- Model name and description
- Claude API ID (snapshot name)
- Claude API alias
- Pricing (input/output per 1M tokens)
- Extended thinking support (Yes/No)
- Comparative latency (Fastest/Fast/Moderate/Slow)
- Context window (tokens)
- Max output (tokens)
- Reliable knowledge cutoff (date)
- Training data cutoff (date)

From the **Legacy Models** section:
- Identify models moved to legacy status
- Note recommended replacements

## Step 2: Compare with Local Configurations

### Check Current Models

```bash
# List current Anthropic model files
ls -la providers/models/anthropic/

# Validate existing configs
agentic-p validate providers/models/anthropic/*.yaml
```

### Comparison Checklist

For each model in the official docs:

- [ ] Model exists locally with correct ID?
- [ ] `api_name` matches official API ID?
- [ ] `alias` matches official API alias?
- [ ] Pricing matches (input_per_1m_tokens, output_per_1m_tokens)?
- [ ] Context window correct (context_window)?
- [ ] Max output tokens correct (max_tokens)?
- [ ] Knowledge cutoff updated (knowledge_cutoff)?
- [ ] Training cutoff updated (training_cutoff)?
- [ ] Capabilities accurate (vision, function_calling, etc.)?
- [ ] Performance characteristics match (speed, quality)?
- [ ] Status correct (current vs legacy)?

## Step 3: Update Model Files

### For New Models

1. Create new YAML file with version-family naming:
   ```
   providers/models/anthropic/claude-{model}-{major}-{minor}.yaml
   ```

2. Use this template:
   ```yaml
   id: claude-{model}-{major}-{minor}
   full_name: "Claude {Model} {version}"
   api_name: "{full-api-id-with-date}"
   alias: "{api-alias}"
   prefer_alias: false
   version: "{major}.{minor}"
   provider: anthropic
   status: "current"
   
   capabilities:
     max_tokens: {from-docs}
     context_window: {from-docs}
     supports_vision: {true/false}
     supports_function_calling: {true/false}
     supports_streaming: true
     supports_json_mode: true
     supports_system_messages: true
   
   performance:
     speed: "{very-fast|fast|moderate|slow}"
     quality: "{very-high|high|medium}"
     reliability: "very-high"
   
   pricing:
     input_per_1m_tokens: {price}
     output_per_1m_tokens: {price}
     currency: "USD"
   
   strengths:
     - "{from-description}"
   
   recommended_for:
     - "{use-cases}"
   
   knowledge_cutoff: "{YYYY-MM-DD}"
   training_cutoff: "{YYYY-MM-DD}"
   last_updated: "{today-YYYY-MM-DD}"
   
   notes: "{from-official-description}"
   ```

3. Validate new file:
   ```bash
   agentic-p validate providers/models/anthropic/claude-{new-model}.yaml
   ```

### For Updated Models

1. Update changed fields (pricing, cutoffs, capabilities)
2. Update `last_updated` date
3. Add notes about what changed

### For Deprecated Models

1. Change `status: "current"` → `status: "legacy"`
2. Update notes to indicate legacy status  
3. Keep file for backward compatibility
4. **DO NOT** add `replacement` field - this is managed centrally in `config.yaml`

**Important**: Replacement mappings are defined in `config.yaml` under `current_models`. This prevents duplicate maintenance and ensures consistency.

## Step 4: Update Config and README

### Update config.yaml

1. Add new model families to `model_families` list
2. Update `current_models` section with latest recommendations:
   ```yaml
   current_models:
     sonnet: claude-{version}-sonnet
     haiku: claude-{version}-haiku
     opus: claude-{version}-opus
   ```
3. Add deprecated families to `legacy_status` list

### Update README.md

1. Update "Available Models" table
2. Update "Legacy Models" section
3. Update pricing information
4. Update capability descriptions
5. Update last updated date

**Note**: You don't need to update `replacement` fields in individual model files - they're managed centrally in `config.yaml`.

## Step 5: Validate Changes

```bash
# Validate schema compliance
agentic-p validate providers/models/anthropic/

# Test model resolution
agentic-p list --provider anthropic

# Run provider tests
cd cli
cargo test --test test_providers -- --nocapture

# Run full validation suite
cargo test
```

## Step 6: Update Documentation

Check if any docs reference specific models:

```bash
# Search for model references
grep -r "claude-3-" docs/
grep -r "anthropic/" docs/
```

Update examples if needed.

## Common Issues

### Issue: New model not appearing in list

**Cause**: ProviderRegistry not finding the file

**Fix**: Check that:
- File is in `providers/models/anthropic/`
- Filename matches pattern `{id}.yaml`
- File is valid YAML
- `id` field matches filename (without .yaml)

### Issue: Schema validation fails

**Cause**: Missing or incorrect required fields

**Fix**: Compare against schema:
```bash
# View schema
cat specs/v1/model-config.schema.json | jq '.required'
```

### Issue: Model resolution fails

**Cause**: Mismatch between file location and ModelRef expectations

**Fix**: Ensure file is at:
```
providers/models/anthropic/{model-id}.yaml
```

Not at:
```
providers/anthropic/models/{model-id}.yaml  ❌
```

## Example Update Commit

**Title**: `feat(models): Update Anthropic models to Claude 4.5 (Nov 2025)`

**Description**:
```
Updates Anthropic model configurations to latest as of November 24, 2025.

Changes:
- ✅ Added Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)
- ✅ Added Claude Haiku 4.5 (claude-haiku-4-5-20251001)
- ✅ Added Claude Opus 4.1 (claude-opus-4-1-20250805)
- ✅ Updated pricing for all models
- ✅ Added knowledge/training cutoff dates
- ✅ Added alias support
- ⚠️  Moved Claude 3 models to legacy status

Testing:
- [x] Schema validation passes
- [x] Model resolution works
- [x] ProviderRegistry loads successfully
- [x] All tests pass

References:
- https://platform.claude.com/docs/en/about-claude/models/overview
```

## Resources

- [Claude Models Overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Anthropic Pricing](https://www.anthropic.com/pricing)
- [Anthropic API Reference](https://docs.anthropic.com/en/api)
- [Anthropic Transparency Hub](https://www.anthropic.com/transparency)
- [Anthropic Discord](https://discord.gg/anthropic) - For announcements

