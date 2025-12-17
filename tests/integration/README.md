# OTel Integration Tests

End-to-end tests validating the OpenTelemetry pipeline for agentic-primitives.

## Claude CLI Telemetry

Claude CLI emits **metrics** and **logs** (not traces) via OpenTelemetry when configured with:

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=otlp
export OTEL_LOGS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4317
```

### Telemetry Output

**Metrics:**
- `claude_code.cost.usage` - Cost per API request in USD (by model)
- `claude_code.token.usage` - Token counts by type (input, output, cacheRead, cacheCreation)

**Logs:**
- `claude_code.api_request` - Events for each API call with model, tokens, duration, cost

## Prerequisites

1. **Docker** must be running
2. **Workspace image** must be built:
   ```bash
   just build-provider claude-cli
   ```
3. **ANTHROPIC_API_KEY** must be set (for live tests):
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```

## Quick Start

```bash
# From agentic-primitives root
cd tests/integration

# Start the OTel collector
docker compose up -d

# Run the tests
uv run pytest -v

# View collector logs (for debugging)
docker compose logs -f otel-collector

# Clean up
docker compose down -v
```

## Test Structure

```
tests/integration/
├── docker-compose.yaml      # OTel collector setup
├── otel-collector-config.yaml  # Collector config (exports to files)
├── output/                  # Collector output (traces, metrics, logs)
├── conftest.py              # Pytest fixtures
├── test_otel_pipeline.py    # Test cases
└── README.md                # This file
```

## Test Categories

### TestOTelCollector
Basic tests to verify the OTel collector is running and accessible.

### TestWorkspaceImage
Tests for the `agentic-workspace-claude-cli` image:
- Claude CLI is installed
- Agentic packages are installed
- Hooks are in place

### TestClaudeCLIOTel
Tests for Claude CLI's native OTel emission:
- Metrics and logs are emitted when running tasks
- OTel environment variables are passed correctly

### TestHookOTelEmission
Tests for hook-based OTel emission:
- Hooks can import and use `agentic_otel`
- Pre-tool-use events are logged

### TestEndToEndPipeline
Full end-to-end tests (marked `@pytest.mark.slow`):
- Complete task with tool use
- Traces flow through the entire pipeline

## Viewing OTel Output

After running tests, check the output files:

```bash
# View traces
cat tests/integration/output/traces.jsonl | jq .

# View logs
cat tests/integration/output/logs.jsonl | jq .

# View metrics
cat tests/integration/output/metrics.jsonl | jq .
```

## Troubleshooting

### "Image not found" error
```bash
just build-provider claude-cli
```

### "API key not set" - tests skipped
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### Collector not receiving traces
1. Check collector is healthy:
   ```bash
   docker inspect --format '{{.State.Health.Status}}' test-otel-collector
   ```
2. Check collector logs:
   ```bash
   docker compose logs otel-collector
   ```
3. Verify network connectivity:
   ```bash
   docker run --rm --network integration_test-network \
     curlimages/curl curl -v http://otel-collector:13133
   ```

## CI Integration

For CI, set the environment variable and run:

```bash
export ANTHROPIC_API_KEY=${{ secrets.ANTHROPIC_API_KEY }}
cd lib/agentic-primitives
just build-provider claude-cli
cd tests/integration
docker compose up -d --wait
uv run pytest -v --tb=short
docker compose down -v
```
