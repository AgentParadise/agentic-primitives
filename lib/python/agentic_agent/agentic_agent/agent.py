"""Instrumented Agent wrapper for Claude Agent SDK.

Provides observability and metrics collection for agent executions.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, TYPE_CHECKING

from agentic_agent.models import get_model_pricing, DEFAULT_MODEL, ModelPricing
from agentic_agent.result import AgentResult, SessionMetrics, ToolCall

if TYPE_CHECKING:
    from agentic_hooks import HookClient
    from agentic_security import SecurityPolicy


@dataclass
class AgentConfig:
    """Configuration for InstrumentedAgent."""

    model: str = DEFAULT_MODEL
    cwd: str | Path | None = None
    allowed_tools: list[str] | None = None
    permission_mode: str = "bypassPermissions"
    setting_sources: list[str] | None = None
    max_turns: int = 50
    max_budget_usd: float | None = None

    # Observability
    hook_client: Any | None = None  # HookClient from agentic_hooks
    session_id: str | None = None

    # Security
    security_policy: Any | None = None  # SecurityPolicy from agentic_security


class InstrumentedAgent:
    """Claude Agent SDK wrapper with metrics collection and observability.

    Captures:
    - Token usage (input/output/cache)
    - Tool calls with timing
    - Cost estimation
    - Integration with HookClient for event emission

    Usage:
        agent = InstrumentedAgent(model="claude-sonnet-4-20250514")
        result = await agent.run("Create a hello world file")
        print(f"Tokens: {result.metrics.total_tokens}")
        print(f"Cost: ${result.metrics.total_cost_usd:.6f}")

    With HookClient:
        from agentic_hooks import HookClient

        async with HookClient(backend=backend) as hook_client:
            agent = InstrumentedAgent(hook_client=hook_client)
            result = await agent.run("Create a file")
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        cwd: str | Path | None = None,
        hook_client: Any | None = None,
        security_policy: Any | None = None,
        allowed_tools: list[str] | None = None,
        permission_mode: str = "bypassPermissions",
        setting_sources: list[str] | None = None,
        session_id: str | None = None,
    ):
        """Initialize the instrumented agent.

        Args:
            model: Model API name (e.g., "claude-sonnet-4-20250514")
            cwd: Working directory for the agent
            hook_client: Optional HookClient for event emission
            security_policy: Optional SecurityPolicy for tool validation
            allowed_tools: List of allowed tools (default: all built-in tools)
            permission_mode: Permission mode (default: bypassPermissions)
            setting_sources: Where to load settings from (default: ["project"])
            session_id: Optional session ID (generates UUID if not provided)
        """
        self.model_name = model
        self.model_pricing = get_model_pricing(model)
        self.cwd = Path(cwd) if cwd else Path.cwd()
        self.hook_client = hook_client
        self.security_policy = security_policy
        self.session_id = session_id or str(uuid.uuid4())
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

        # Tracking state
        self._tool_use_map: dict[str, str] = {}  # tool_use_id -> tool_name
        self._tool_calls: list[ToolCall] = []
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._cache_creation_tokens = 0
        self._cache_read_tokens = 0

    async def run(
        self,
        prompt: str,
        max_turns: int | None = None,
        max_budget_usd: float | None = None,
    ) -> AgentResult:
        """Run the agent with a prompt and capture metrics.

        Args:
            prompt: The prompt to send to the agent
            max_turns: Maximum conversation turns (default: 50)
            max_budget_usd: Optional budget cap in USD

        Returns:
            AgentResult with response text and metrics
        """
        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                ResultMessage,
                query,
            )
        except ImportError as e:
            raise ImportError(
                "claude-agent-sdk is required. Install with: pip install claude-agent-sdk"
            ) from e

        start_time = datetime.now(UTC)
        start_ms = time.time() * 1000

        # Reset tracking state
        self._tool_use_map = {}
        self._tool_calls = []
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._cache_creation_tokens = 0
        self._cache_read_tokens = 0

        # Emit session started event
        await self._emit_session_started()

        # Configure agent options
        options = ClaudeAgentOptions(
            model=self.model_name,
            cwd=str(self.cwd),
            allowed_tools=self.allowed_tools,
            permission_mode=self.permission_mode,
            setting_sources=self.setting_sources,
            max_turns=max_turns or 50,
            max_budget_usd=max_budget_usd,
        )

        try:
            result_text = ""
            result_message = None
            interaction_count = 0

            # Stream the query
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    interaction_count += 1
                    await self._handle_assistant_message(message)

                elif isinstance(message, ResultMessage):
                    result_message = message
                    result_text = message.result or ""

            # Calculate final metrics
            end_time = datetime.now(UTC)
            duration_ms = (time.time() * 1000) - start_ms
            total_cost = self.model_pricing.calculate_cost(
                self._total_input_tokens,
                self._total_output_tokens,
            )

            metrics = SessionMetrics(
                session_id=self.session_id,
                model=self.model_name,
                start_time=start_time,
                end_time=end_time,
                input_tokens=self._total_input_tokens,
                output_tokens=self._total_output_tokens,
                cache_creation_tokens=self._cache_creation_tokens,
                cache_read_tokens=self._cache_read_tokens,
                total_cost_usd=total_cost,
                interaction_count=interaction_count,
                tool_call_count=len(self._tool_calls),
                duration_ms=duration_ms,
            )

            # Emit session ended event
            await self._emit_session_ended(metrics)

            return AgentResult(
                text=result_text,
                metrics=metrics,
                tool_calls=self._tool_calls,
                success=True,
                raw_result=result_message,
            )

        except Exception as e:
            end_time = datetime.now(UTC)
            duration_ms = (time.time() * 1000) - start_ms

            metrics = SessionMetrics(
                session_id=self.session_id,
                model=self.model_name,
                start_time=start_time,
                end_time=end_time,
                input_tokens=self._total_input_tokens,
                output_tokens=self._total_output_tokens,
                total_cost_usd=self.model_pricing.calculate_cost(
                    self._total_input_tokens,
                    self._total_output_tokens,
                ),
                interaction_count=0,
                tool_call_count=len(self._tool_calls),
                duration_ms=duration_ms,
            )

            # Emit error event
            await self._emit_error(str(e))

            return AgentResult(
                text="",
                metrics=metrics,
                tool_calls=self._tool_calls,
                success=False,
                error=str(e),
            )

    async def _handle_assistant_message(self, message: Any) -> None:
        """Handle an AssistantMessage from the SDK.

        Extracts token usage and tool calls from the message.
        """
        # Extract token usage
        if hasattr(message, "usage") and message.usage:
            usage = message.usage

            # Handle both dict and object-style usage
            def get_usage_value(key: str, default: int = 0) -> int:
                if isinstance(usage, dict):
                    return usage.get(key, default)
                if hasattr(usage, "get"):
                    return usage.get(key, default)
                return getattr(usage, key, default)

            input_tokens = get_usage_value("input_tokens", 0)
            output_tokens = get_usage_value("output_tokens", 0)
            cache_creation = get_usage_value("cache_creation_input_tokens", 0)
            cache_read = get_usage_value("cache_read_input_tokens", 0)

            self._total_input_tokens += input_tokens
            self._total_output_tokens += output_tokens
            self._cache_creation_tokens += cache_creation
            self._cache_read_tokens += cache_read

            # Emit token usage event
            await self._emit_token_usage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_creation=cache_creation,
                cache_read=cache_read,
            )

        # Parse content blocks for tool usage
        if hasattr(message, "content") and message.content:
            for block in message.content:
                await self._handle_content_block(block)

    async def _handle_content_block(self, block: Any) -> None:
        """Handle a content block (ToolUseBlock, ToolResultBlock, etc.)."""
        # Get block type via duck typing
        block_type = (
            getattr(block, "type", None)
            if not isinstance(block, dict)
            else block.get("type")
        )

        # Handle ToolUseBlock (tool started)
        if block_type == "tool_use":
            tool_name = (
                getattr(block, "name", None)
                if not isinstance(block, dict)
                else block.get("name")
            ) or "unknown"

            tool_use_id = (
                getattr(block, "id", None)
                if not isinstance(block, dict)
                else block.get("id")
            )

            tool_input = (
                getattr(block, "input", None)
                if not isinstance(block, dict)
                else block.get("input")
            ) or {}

            # Check security policy if configured
            blocked = False
            block_reason = None
            if self.security_policy:
                result = self.security_policy.validate(tool_name, tool_input)
                if not result.safe:
                    blocked = True
                    block_reason = result.reason

            # Record tool call
            tool_call = ToolCall(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_use_id=tool_use_id,
                success=not blocked,
                error=block_reason,
            )
            self._tool_calls.append(tool_call)

            # Store mapping for result correlation
            if tool_use_id:
                self._tool_use_map[tool_use_id] = tool_name

            # Emit tool started event
            await self._emit_tool_started(tool_name, tool_input, tool_use_id, blocked, block_reason)

        # Handle ToolResultBlock (tool completed)
        elif block_type == "tool_result":
            tool_use_id = (
                getattr(block, "tool_use_id", None)
                if not isinstance(block, dict)
                else block.get("tool_use_id")
            )

            is_error = (
                getattr(block, "is_error", False)
                if not isinstance(block, dict)
                else block.get("is_error", False)
            )

            tool_name = self._tool_use_map.get(tool_use_id, "unknown") if tool_use_id else "unknown"

            # Emit tool completed event
            await self._emit_tool_completed(tool_name, tool_use_id, not is_error)

    async def _emit_session_started(self) -> None:
        """Emit session started event."""
        if self.hook_client:
            try:
                from agentic_hooks import HookEvent, EventType
                await self.hook_client.emit(HookEvent(
                    event_type=EventType.SESSION_STARTED,
                    session_id=self.session_id,
                    data={"model": self.model_name},
                ))
            except ImportError:
                pass

    async def _emit_session_ended(self, metrics: SessionMetrics) -> None:
        """Emit session ended event."""
        if self.hook_client:
            try:
                from agentic_hooks import HookEvent, EventType
                await self.hook_client.emit(HookEvent(
                    event_type=EventType.SESSION_ENDED,
                    session_id=self.session_id,
                    data=metrics.to_dict(),
                ))
            except ImportError:
                pass

    async def _emit_token_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_creation: int = 0,
        cache_read: int = 0,
    ) -> None:
        """Emit token usage event."""
        if self.hook_client:
            try:
                from agentic_hooks import HookEvent, EventType
                await self.hook_client.emit(HookEvent(
                    event_type=EventType.TOKENS_USED,
                    session_id=self.session_id,
                    data={
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cache_creation_tokens": cache_creation,
                        "cache_read_tokens": cache_read,
                    },
                ))
            except ImportError:
                pass

    async def _emit_tool_started(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str | None,
        blocked: bool = False,
        block_reason: str | None = None,
    ) -> None:
        """Emit tool started event."""
        if self.hook_client:
            try:
                from agentic_hooks import HookEvent, EventType
                await self.hook_client.emit(HookEvent(
                    event_type=EventType.TOOL_EXECUTION_STARTED,
                    session_id=self.session_id,
                    data={
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                        "tool_use_id": tool_use_id,
                        "blocked": blocked,
                        "block_reason": block_reason,
                    },
                ))
            except ImportError:
                pass

    async def _emit_tool_completed(
        self,
        tool_name: str,
        tool_use_id: str | None,
        success: bool,
    ) -> None:
        """Emit tool completed event."""
        if self.hook_client:
            try:
                from agentic_hooks import HookEvent, EventType
                await self.hook_client.emit(HookEvent(
                    event_type=EventType.TOOL_EXECUTION_COMPLETED,
                    session_id=self.session_id,
                    data={
                        "tool_name": tool_name,
                        "tool_use_id": tool_use_id,
                        "success": success,
                    },
                ))
            except ImportError:
                pass

    async def _emit_error(self, error: str) -> None:
        """Emit error event."""
        if self.hook_client:
            try:
                from agentic_hooks import HookEvent, EventType
                await self.hook_client.emit(HookEvent(
                    event_type=EventType.ERROR_OCCURRED,
                    session_id=self.session_id,
                    data={"error": error},
                ))
            except ImportError:
                pass

    def run_sync(
        self,
        prompt: str,
        max_turns: int | None = None,
        max_budget_usd: float | None = None,
    ) -> AgentResult:
        """Synchronous wrapper for run().

        For simpler usage without async/await.
        """
        return asyncio.run(self.run(prompt, max_turns, max_budget_usd))
