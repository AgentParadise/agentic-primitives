"""Claude Agent SDK Integration with Metrics Collection.

This module provides instrumented wrappers around the Claude Agent SDK
that capture comprehensive metrics including:
- Token usage (input/output)
- Tool call tracking with timing
- Cost estimation based on model configs
- Security hook integration
"""

from src.agent import AgentResult, InstrumentedAgent, quick_query
from src.metrics import (
    InteractionMetrics,
    MetricsCollector,
    SessionContext,
    SessionMetrics,
    ToolCallMetric,
)
from src.models import DEFAULT_MODEL, ModelConfig, list_available_models, load_model_config
from src.scenarios import (
    SCENARIOS,
    Scenario,
    ScenarioResult,
    get_scenario_by_name,
    list_scenarios,
    run_all_scenarios,
    run_scenario,
)

__all__ = [
    # Models
    "ModelConfig",
    "load_model_config",
    "list_available_models",
    "DEFAULT_MODEL",
    # Metrics
    "MetricsCollector",
    "SessionContext",
    "SessionMetrics",
    "InteractionMetrics",
    "ToolCallMetric",
    # Agent
    "InstrumentedAgent",
    "AgentResult",
    "quick_query",
    # Scenarios
    "Scenario",
    "ScenarioResult",
    "SCENARIOS",
    "run_scenario",
    "run_all_scenarios",
    "get_scenario_by_name",
    "list_scenarios",
]
