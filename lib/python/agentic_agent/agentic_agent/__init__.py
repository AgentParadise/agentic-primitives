"""agentic-agent: Instrumented wrapper for AI agent SDKs.

.. deprecated:: 0.2.0
    This package is deprecated in favor of the CLI-first approach using
    `ClaudeCLIRunner` from `agentic_adapters.claude_cli`.

    Claude Code CLI provides:
    - Native OTel metrics (token usage, cost, etc.)
    - Better isolation in containers
    - Production-ready stability

    Migration:
        # OLD (deprecated)
        from agentic_agent import InstrumentedAgent
        agent = InstrumentedAgent(model="claude-sonnet-4-20250514")
        result = await agent.run("Create a file")

        # NEW (recommended)
        from agentic_otel import OTelConfig
        from agentic_adapters.claude_cli import ClaudeCLIRunner

        config = OTelConfig(endpoint="http://collector:4317")
        runner = ClaudeCLIRunner(otel_config=config)
        result = await runner.run("Create a file")

    See ADR-025: Universal Agent Integration Layer for details.

Provides observability and metrics collection for agent executions,
with integration for agentic_hooks event emission and agentic_security
policy enforcement.

Quick Start:
    from agentic_agent import InstrumentedAgent

    agent = InstrumentedAgent(model="claude-sonnet-4-20250514")
    result = await agent.run("Create a hello world file")
    print(f"Tokens: {result.metrics.total_tokens}")
    print(f"Cost: ${result.metrics.total_cost_usd:.6f}")

With HookClient:
    from agentic_hooks import HookClient
    from agentic_agent import InstrumentedAgent

    async with HookClient(backend=backend) as hook_client:
        agent = InstrumentedAgent(hook_client=hook_client)
        result = await agent.run("Create a file")

With SecurityPolicy:
    from agentic_security import SecurityPolicy
    from agentic_agent import InstrumentedAgent

    policy = SecurityPolicy.with_defaults()
    agent = InstrumentedAgent(security_policy=policy)
    result = await agent.run("Run some commands")

Features:
    - Token usage tracking (input/output/cache)
    - Tool call tracking with timing
    - Cost estimation from built-in model pricing
    - Integration with HookClient for event emission
    - Integration with SecurityPolicy for tool validation
    - Works with Claude Agent SDK
"""

import warnings

warnings.warn(
    "agentic_agent is deprecated. Use ClaudeCLIRunner from agentic_adapters.claude_cli "
    "for CLI-first execution with native OTel support. See ADR-025.",
    DeprecationWarning,
    stacklevel=2,
)

from agentic_agent.agent import InstrumentedAgent, AgentConfig
from agentic_agent.result import AgentResult, SessionMetrics, ToolCall
from agentic_agent.models import (
    ModelPricing,
    get_model_pricing,
    list_models,
    DEFAULT_MODEL,
    ANTHROPIC_MODELS,
)

__all__ = [
    # Main API
    "InstrumentedAgent",
    "AgentConfig",
    "AgentResult",
    "SessionMetrics",
    "ToolCall",
    # Models
    "ModelPricing",
    "get_model_pricing",
    "list_models",
    "DEFAULT_MODEL",
    "ANTHROPIC_MODELS",
]

__version__ = "0.1.0"
