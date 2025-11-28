"""Instrumented Agent wrapper for Claude Agent SDK.

Provides a wrapper around claude-agent-sdk that captures comprehensive metrics
including token usage, tool calls, and cost estimation.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    ToolUseBlock,
    query,
)

from src.metrics import MetricsCollector, SessionMetrics
from src.models import DEFAULT_MODEL, load_model_config


@dataclass
class AgentResult:
    """Result from an agent run including text response and metrics."""

    text: str
    metrics: SessionMetrics
    raw_result: Optional[ResultMessage] = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


class InstrumentedAgent:
    """Claude Agent SDK wrapper with metrics collection.

    Captures comprehensive metrics including:
    - Token usage (input/output)
    - Tool calls with timing
    - Cost estimation from model configs
    - Integration with security hooks

    Usage:
        agent = InstrumentedAgent()
        result = await agent.run("Create a hello world file")
        print(f"Tokens: {result.metrics.total_tokens}")
        print(f"Cost: ${result.metrics.total_cost_usd:.6f}")

    With custom model:
        agent = InstrumentedAgent(model="claude-3-5-haiku-20241022")
        result = await agent.run("Quick task")
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        output_path: str | Path = ".agentic/analytics/events.jsonl",
        cwd: str | Path | None = None,
        allowed_tools: Optional[list[str]] = None,
        permission_mode: str = "bypassPermissions",
        setting_sources: Optional[list[str]] = None,
    ):
        """Initialize the instrumented agent.

        Args:
            model: Model API name (e.g., "claude-sonnet-4-5-20250929")
            output_path: Path to write metrics JSONL
            cwd: Working directory for the agent
            allowed_tools: List of allowed tools (default: all built-in tools)
            permission_mode: Permission mode (default: bypassPermissions for automation)
            setting_sources: Where to load settings from (default: ["project"])
        """
        self.model_name = model
        self.model_config = load_model_config(model)
        self.collector = MetricsCollector(output_path=output_path)
        self.cwd = Path(cwd) if cwd else Path.cwd() / ".workspace"
        self.allowed_tools = allowed_tools or [
            "Read",
            "Write",
            "Edit",
            "MultiEdit",
            "Bash",
            "Glob",
            "Grep",
            "LS",
            "TodoRead",
            "TodoWrite",
        ]
        self.permission_mode = permission_mode
        self.setting_sources = setting_sources or ["project"]

        # Ensure workspace exists
        self.cwd.mkdir(parents=True, exist_ok=True)

    async def run(
        self,
        prompt: str,
        max_turns: int = 10,
        max_budget_usd: Optional[float] = None,
    ) -> AgentResult:
        """Run the agent with a prompt and capture metrics.

        Args:
            prompt: The prompt to send to the agent
            max_turns: Maximum conversation turns (default: 10)
            max_budget_usd: Optional budget cap in USD

        Returns:
            AgentResult with response text and metrics
        """
        session = self.collector.start_session(model=self.model_config)
        start_time = time.time()
        tool_calls: list[dict[str, Any]] = []

        # Configure agent options
        options = ClaudeAgentOptions(
            model=self.model_name,
            cwd=str(self.cwd),
            allowed_tools=self.allowed_tools,
            permission_mode=self.permission_mode,
            setting_sources=self.setting_sources,
            max_turns=max_turns,
            max_budget_usd=max_budget_usd,
        )

        try:
            result_text = ""
            result_message: Optional[ResultMessage] = None

            # Stream the query
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    # Extract tool uses from content blocks
                    if hasattr(message, "content") and message.content:
                        for block in message.content:
                            if isinstance(block, ToolUseBlock):
                                tool_call = {
                                    "tool_name": block.name,
                                    "tool_input": block.input if hasattr(block, "input") else {},
                                    "id": block.id if hasattr(block, "id") else None,
                                }
                                tool_calls.append(tool_call)

                                # Record tool call in metrics
                                session.record_tool_call(
                                    tool_name=block.name,
                                    tool_input=tool_call["tool_input"],
                                )

                elif isinstance(message, ResultMessage):
                    result_message = message
                    result_text = message.result or ""

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Extract token usage from result
            input_tokens = 0
            output_tokens = 0
            if result_message and result_message.usage:
                usage = result_message.usage
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)

            # Record the interaction
            session.record_interaction(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                prompt_preview=prompt[:100],
                response_preview=result_text[:100] if result_text else None,
            )

            # End session and get metrics
            metrics = session.end()

            return AgentResult(
                text=result_text,
                metrics=metrics,
                raw_result=result_message,
                tool_calls=tool_calls,
                success=True,
            )

        except Exception as e:
            # Record error and still return metrics
            duration_ms = (time.time() - start_time) * 1000
            session.record_interaction(
                input_tokens=0,
                output_tokens=0,
                duration_ms=duration_ms,
                prompt_preview=prompt[:100],
                response_preview=f"ERROR: {str(e)[:80]}",
            )
            metrics = session.end()

            return AgentResult(
                text="",
                metrics=metrics,
                raw_result=None,
                tool_calls=tool_calls,
                success=False,
                error=str(e),
            )

    def run_sync(
        self,
        prompt: str,
        max_turns: int = 10,
        max_budget_usd: Optional[float] = None,
    ) -> AgentResult:
        """Synchronous wrapper for run().

        For simpler usage without async/await.

        Args:
            prompt: The prompt to send to the agent
            max_turns: Maximum conversation turns
            max_budget_usd: Optional budget cap

        Returns:
            AgentResult with response text and metrics
        """
        return asyncio.run(self.run(prompt, max_turns, max_budget_usd))


# Convenience function for quick one-off queries
async def quick_query(
    prompt: str,
    model: str = DEFAULT_MODEL,
    output_path: str = ".agentic/analytics/events.jsonl",
) -> AgentResult:
    """Run a quick query with default settings.

    Args:
        prompt: The prompt to send
        model: Model to use
        output_path: Where to write metrics

    Returns:
        AgentResult with response and metrics
    """
    agent = InstrumentedAgent(model=model, output_path=output_path)
    return await agent.run(prompt)
