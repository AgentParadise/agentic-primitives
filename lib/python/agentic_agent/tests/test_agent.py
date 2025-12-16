"""Tests for InstrumentedAgent.

These tests use mock SDK types to avoid requiring the actual Claude SDK.
"""

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_agent import InstrumentedAgent, AgentResult


# =============================================================================
# Mock SDK Types (for fast testing without claude-agent-sdk)
# =============================================================================


@dataclass
class MockUsage:
    """Mock token usage."""
    input_tokens: int = 100
    output_tokens: int = 50
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass
class MockToolUseBlock:
    """Mock ToolUseBlock from SDK."""
    type: str = "tool_use"
    id: str = "toolu_123"
    name: str = "Write"
    input: dict[str, Any] = field(default_factory=lambda: {"path": "test.py"})


@dataclass
class MockToolResultBlock:
    """Mock ToolResultBlock from SDK."""
    type: str = "tool_result"
    tool_use_id: str = "toolu_123"
    is_error: bool = False


@dataclass
class MockTextBlock:
    """Mock TextBlock from SDK."""
    type: str = "text"
    text: str = "Hello, world!"


@dataclass
class MockAssistantMessage:
    """Mock AssistantMessage from SDK."""
    usage: MockUsage = field(default_factory=MockUsage)
    content: list[Any] = field(default_factory=list)


@dataclass
class MockResultMessage:
    """Mock ResultMessage from SDK."""
    result: str = "Task completed"
    usage: MockUsage | None = None


class TestInstrumentedAgentInit:
    """Tests for agent initialization."""

    def test_default_initialization(self) -> None:
        """Should initialize with defaults."""
        agent = InstrumentedAgent()
        assert agent.model_name == "claude-sonnet-4-20250514"
        assert agent.session_id is not None
        assert len(agent.allowed_tools) > 0

    def test_custom_model(self) -> None:
        """Should accept custom model."""
        agent = InstrumentedAgent(model="claude-opus-4-20250514")
        assert agent.model_name == "claude-opus-4-20250514"
        assert agent.model_pricing.api_name == "claude-opus-4-20250514"

    def test_custom_session_id(self) -> None:
        """Should accept custom session ID."""
        agent = InstrumentedAgent(session_id="my-session-123")
        assert agent.session_id == "my-session-123"

    def test_custom_tools(self) -> None:
        """Should accept custom allowed tools."""
        tools = ["Read", "Write"]
        agent = InstrumentedAgent(allowed_tools=tools)
        assert agent.allowed_tools == tools


class TestContentBlockHandling:
    """Tests for content block parsing."""

    @pytest.fixture
    def agent(self) -> InstrumentedAgent:
        """Create agent for testing."""
        return InstrumentedAgent()

    @pytest.mark.asyncio
    async def test_handles_tool_use_block(self, agent: InstrumentedAgent) -> None:
        """Should parse ToolUseBlock correctly."""
        block = MockToolUseBlock(
            name="Write",
            id="toolu_abc",
            input={"path": "test.py", "content": "print('hi')"},
        )

        await agent._handle_content_block(block)

        assert len(agent._tool_calls) == 1
        assert agent._tool_calls[0].tool_name == "Write"
        assert agent._tool_calls[0].tool_use_id == "toolu_abc"
        assert agent._tool_use_map["toolu_abc"] == "Write"

    @pytest.mark.asyncio
    async def test_handles_tool_use_block_dict(self, agent: InstrumentedAgent) -> None:
        """Should parse dict-format tool use block."""
        block = {
            "type": "tool_use",
            "id": "toolu_xyz",
            "name": "Bash",
            "input": {"command": "ls -la"},
        }

        await agent._handle_content_block(block)

        assert len(agent._tool_calls) == 1
        assert agent._tool_calls[0].tool_name == "Bash"

    @pytest.mark.asyncio
    async def test_handles_tool_result_block(self, agent: InstrumentedAgent) -> None:
        """Should parse ToolResultBlock correctly."""
        # First add tool use to map
        agent._tool_use_map["toolu_123"] = "Write"

        block = MockToolResultBlock(tool_use_id="toolu_123", is_error=False)

        # Should not raise
        await agent._handle_content_block(block)

    @pytest.mark.asyncio
    async def test_handles_text_block(self, agent: InstrumentedAgent) -> None:
        """Should ignore text blocks gracefully."""
        block = MockTextBlock(text="Some response text")

        # Should not raise or add tool calls
        await agent._handle_content_block(block)
        assert len(agent._tool_calls) == 0


class TestAssistantMessageHandling:
    """Tests for assistant message handling."""

    @pytest.fixture
    def agent(self) -> InstrumentedAgent:
        """Create agent for testing."""
        return InstrumentedAgent()

    @pytest.mark.asyncio
    async def test_extracts_token_usage(self, agent: InstrumentedAgent) -> None:
        """Should extract token usage from message."""
        message = MockAssistantMessage(
            usage=MockUsage(input_tokens=500, output_tokens=200),
            content=[],
        )

        await agent._handle_assistant_message(message)

        assert agent._total_input_tokens == 500
        assert agent._total_output_tokens == 200

    @pytest.mark.asyncio
    async def test_extracts_cache_tokens(self, agent: InstrumentedAgent) -> None:
        """Should extract cache tokens from message."""
        message = MockAssistantMessage(
            usage=MockUsage(
                input_tokens=500,
                output_tokens=200,
                cache_creation_input_tokens=100,
                cache_read_input_tokens=50,
            ),
            content=[],
        )

        await agent._handle_assistant_message(message)

        assert agent._cache_creation_tokens == 100
        assert agent._cache_read_tokens == 50

    @pytest.mark.asyncio
    async def test_parses_tool_blocks_in_content(self, agent: InstrumentedAgent) -> None:
        """Should parse tool blocks from message content."""
        message = MockAssistantMessage(
            usage=MockUsage(),
            content=[
                MockToolUseBlock(name="Read", id="toolu_1", input={"path": "a.txt"}),
                MockTextBlock(text="Reading file..."),
                MockToolUseBlock(name="Write", id="toolu_2", input={"path": "b.txt"}),
            ],
        )

        await agent._handle_assistant_message(message)

        assert len(agent._tool_calls) == 2
        assert agent._tool_calls[0].tool_name == "Read"
        assert agent._tool_calls[1].tool_name == "Write"


class TestSecurityPolicyIntegration:
    """Tests for security policy integration."""

    @pytest.fixture
    def agent_with_policy(self) -> InstrumentedAgent:
        """Create agent with mock security policy."""
        mock_policy = MagicMock()
        mock_policy.validate.return_value = MagicMock(safe=False, reason="Blocked!")
        return InstrumentedAgent(security_policy=mock_policy)

    @pytest.mark.asyncio
    async def test_blocks_dangerous_tool_calls(
        self, agent_with_policy: InstrumentedAgent
    ) -> None:
        """Should mark blocked tool calls."""
        block = MockToolUseBlock(
            name="Bash",
            id="toolu_danger",
            input={"command": "rm -rf /"},
        )

        await agent_with_policy._handle_content_block(block)

        assert len(agent_with_policy._tool_calls) == 1
        assert agent_with_policy._tool_calls[0].success is False
        assert "Blocked" in (agent_with_policy._tool_calls[0].error or "")


class TestHookClientIntegration:
    """Tests for HookClient integration."""

    @pytest.mark.asyncio
    async def test_emits_events_when_hook_client_provided(self) -> None:
        """Should emit events to hook client."""
        mock_hook_client = AsyncMock()

        agent = InstrumentedAgent(hook_client=mock_hook_client)

        # Mock the HookEvent import
        with patch.dict("sys.modules", {
            "agentic_hooks": MagicMock(
                HookEvent=MagicMock,
                EventType=MagicMock(
                    SESSION_STARTED="session.started",
                    TOKENS_USED="tokens.used",
                    TOOL_EXECUTION_STARTED="tool.started",
                ),
            ),
        }):
            await agent._emit_session_started()
            await agent._emit_token_usage(100, 50)

        # Hook client should have been called
        assert mock_hook_client.emit.called

    @pytest.mark.asyncio
    async def test_handles_missing_hook_client(self) -> None:
        """Should not fail when hook client is None."""
        agent = InstrumentedAgent(hook_client=None)

        # Should not raise
        await agent._emit_session_started()
        await agent._emit_token_usage(100, 50)
        await agent._emit_tool_started("Write", {}, "toolu_123")
