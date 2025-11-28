#!/usr/bin/env python3
"""Claude Agent SDK Integration - Main Entry Point.

Run test scenarios with the Claude Agent SDK and capture comprehensive metrics.

Usage:
    uv run python main.py                          # Run all scenarios
    uv run python main.py --scenario create-file   # Run single scenario
    uv run python main.py --model claude-3-5-haiku-20241022  # Use specific model
    uv run python main.py --dry-run                # Show scenarios without running
    uv run python main.py --list                   # List available scenarios
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from src.agent import InstrumentedAgent
from src.metrics import MetricsCollector
from src.models import DEFAULT_MODEL, list_available_models, load_model_config
from src.scenarios import (
    SCENARIOS,
    Scenario,
    ScenarioResult,
    get_scenario_by_name,
    run_scenario,
)

# ============================================================================
# Output Formatting
# ============================================================================


def print_header(title: str) -> None:
    """Print a formatted header."""
    width = 60
    print()
    print("═" * width)
    print(f"  {title}")
    print("═" * width)


def print_scenario_result(result: ScenarioResult, verbose: bool = False) -> None:
    """Print results for a single scenario."""
    s = result.scenario
    m = result.metrics

    # Status indicator
    status = "✅ PASSED" if result.success else "❌ FAILED"
    if s.should_block and result.success:
        status = "🛡️ BLOCKED (expected)"

    print(f"\n  Scenario: {s.name}")
    print(f"    Status: {status}")
    print(
        f"    Tokens: {m.total_tokens:,} (in: {m.total_input_tokens:,}, out: {m.total_output_tokens:,})"
    )
    print(f"    Cost: ${m.total_cost_usd:.6f}")
    print(f"    Duration: {m.total_duration_ms / 1000:.1f}s")

    if result.agent_result.tool_calls:
        tools_summary = {}
        for tc in result.agent_result.tool_calls:
            name = tc["tool_name"]
            tools_summary[name] = tools_summary.get(name, 0) + 1
        tools_str = ", ".join(f"{k} ({v}x)" for k, v in tools_summary.items())
        print(f"    Tools: {tools_str}")
    else:
        print("    Tools: (none)")

    if result.error:
        print(f"    Error: {result.error[:50]}...")

    if verbose and result.validation_notes:
        print("    Validation:")
        for note in result.validation_notes:
            print(f"      {note}")


def print_summary(results: list[ScenarioResult]) -> None:
    """Print aggregate summary of all scenarios."""
    total = len(results)
    passed = sum(1 for r in results if r.success)
    failed = total - passed
    blocked = sum(1 for r in results if r.scenario.should_block and r.success)

    total_tokens = sum(r.metrics.total_tokens for r in results)
    total_cost = sum(r.metrics.total_cost_usd for r in results)
    total_duration = sum(r.metrics.total_duration_ms for r in results)

    # Count events in JSONL
    events_file = Path(".agentic/analytics/events.jsonl")
    event_count = 0
    if events_file.exists():
        with open(events_file) as f:
            event_count = sum(1 for _ in f)

    print_header("Summary")
    print(f"  Total Scenarios: {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    if blocked:
        print(f"  Blocked (expected): {blocked}")
    print()
    print(f"  Total Tokens: {total_tokens:,}")
    print(f"  Total Cost: ${total_cost:.4f}")
    print(f"  Total Duration: {total_duration / 1000:.1f}s")
    print()
    print(f"  Analytics: {events_file} ({event_count} events)")
    print("═" * 60)


# ============================================================================
# Main Functions
# ============================================================================


def list_scenarios_cmd() -> None:
    """List all available scenarios."""
    print_header("Available Scenarios")
    for s in SCENARIOS:
        block_indicator = " 🛡️" if s.should_block else ""
        print(f"  {s.name}{block_indicator}")
        print(f"    {s.description}")
        if s.expected_tools:
            print(f"    Tools: {', '.join(s.expected_tools)}")
        print()


def list_models_cmd() -> None:
    """List all available models with pricing."""
    print_header("Available Models")
    for api_name in list_available_models():
        try:
            config = load_model_config(api_name)
            print(f"  {api_name}")
            print(f"    Display: {config.display_name}")
            print(f"    Input: ${config.input_per_1m_tokens}/MTok")
            print(f"    Output: ${config.output_per_1m_tokens}/MTok")
            print()
        except Exception:
            pass


def dry_run_cmd(scenarios: list[Scenario], model: str) -> None:
    """Show what would be run without executing."""
    config = load_model_config(model)

    print_header(f"Dry Run - {config.display_name}")
    print(f"  Model: {model}")
    print(
        f"  Pricing: ${config.input_per_1m_tokens}/MTok in, ${config.output_per_1m_tokens}/MTok out"
    )
    print()

    for s in scenarios:
        block_indicator = " 🛡️ (should block)" if s.should_block else ""
        print(f"  [{s.name}]{block_indicator}")
        print(f"    {s.description}")
        print(f"    Prompt: {s.prompt[:60]}...")
        if s.expected_tools:
            print(f"    Expected: {', '.join(s.expected_tools)}")
        print()


async def run_scenarios_async(
    scenarios: list[Scenario],
    model: str,
    verbose: bool = False,
) -> list[ScenarioResult]:
    """Run scenarios asynchronously."""
    config = load_model_config(model)

    print_header("Claude Agent SDK Integration - Test Results")
    print(f"  Model: {config.display_name}")
    print(
        f"  Pricing: ${config.input_per_1m_tokens}/MTok in, ${config.output_per_1m_tokens}/MTok out"
    )
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Clear previous analytics
    collector = MetricsCollector()
    collector.clear()

    # Create agent
    agent = InstrumentedAgent(model=model)

    # Run scenarios
    results = []
    for scenario in scenarios:
        print(f"\n  Running: {scenario.name}...", end="", flush=True)
        result = await run_scenario(agent, scenario)
        results.append(result)

        # Quick status
        status = "✓" if result.success else "✗"
        print(f" {status}")

    # Print detailed results
    for result in results:
        print_scenario_result(result, verbose=verbose)

    # Print summary
    print_summary(results)

    return results


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Claude Agent SDK Integration - Run test scenarios and capture metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                        Run all scenarios
  %(prog)s --scenario create-file Run single scenario
  %(prog)s --dry-run              Show what would run
  %(prog)s --list                 List available scenarios
  %(prog)s --list-models          List available models
        """,
    )

    parser.add_argument(
        "--scenario",
        "-s",
        help="Run a specific scenario by name",
    )
    parser.add_argument(
        "--model",
        "-m",
        default=DEFAULT_MODEL,
        help=f"Model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show scenarios without running",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List available scenarios",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available models with pricing",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed validation output",
    )
    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Run all scenarios (default behavior)",
    )

    args = parser.parse_args()

    # Handle list commands
    if args.list:
        list_scenarios_cmd()
        return 0

    if args.list_models:
        list_models_cmd()
        return 0

    # Determine which scenarios to run
    if args.scenario:
        scenario = get_scenario_by_name(args.scenario)
        if not scenario:
            print(f"Error: Unknown scenario '{args.scenario}'")
            print(f"Available: {', '.join(s.name for s in SCENARIOS)}")
            return 1
        scenarios = [scenario]
    else:
        scenarios = SCENARIOS

    # Handle dry run
    if args.dry_run:
        dry_run_cmd(scenarios, args.model)
        return 0

    # Run scenarios
    try:
        results = asyncio.run(
            run_scenarios_async(
                scenarios=scenarios,
                model=args.model,
                verbose=args.verbose,
            )
        )

        # Return non-zero if any failed
        if any(not r.success for r in results):
            return 1
        return 0

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
