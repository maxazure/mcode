"""Tests for context management utilities"""

import pytest
from maxagent.utils.context import (
    estimate_tokens,
    count_message_tokens,
    count_messages_tokens,
    get_model_context_limit,
    ContextManager,
    ContextStats,
    MODEL_CONTEXT_LIMITS,
)
from maxagent.llm.models import Message, ToolCall, ToolCallFunction


class TestEstimateTokens:
    """Tests for token estimation"""

    def test_empty_string(self) -> None:
        """Empty string returns 0 tokens"""
        assert estimate_tokens("") == 0

    def test_english_text(self) -> None:
        """English text estimation (~4 chars per token)"""
        text = "Hello world"  # 11 chars
        tokens = estimate_tokens(text)
        # Should be around 11/4 + 4 overhead = ~7
        assert 5 <= tokens <= 15

    def test_chinese_text(self) -> None:
        """Chinese text estimation (~1.5 chars per token)"""
        text = "你好世界"  # 4 Chinese chars
        tokens = estimate_tokens(text)
        # Should be around 4/1.5 + 4 overhead = ~7
        assert 5 <= tokens <= 15

    def test_mixed_text(self) -> None:
        """Mixed language text estimation"""
        text = "Hello 你好 world 世界"  # Mix of English and Chinese
        tokens = estimate_tokens(text)
        assert tokens > 0


class TestCountMessageTokens:
    """Tests for message token counting"""

    def test_simple_message(self) -> None:
        """Simple user message"""
        msg = Message(role="user", content="Hello")
        tokens = count_message_tokens(msg)
        assert tokens > 0

    def test_message_with_tool_calls(self) -> None:
        """Message with tool calls"""
        msg = Message(
            role="assistant",
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_1",
                    type="function",
                    function=ToolCallFunction(
                        name="read_file",
                        arguments='{"path": "test.py"}',
                    ),
                )
            ],
        )
        tokens = count_message_tokens(msg)
        assert tokens > 10  # Should account for tool call structure

    def test_tool_response_message(self) -> None:
        """Tool response message"""
        msg = Message(
            role="tool",
            tool_call_id="call_1",
            name="read_file",
            content="File content here...",
        )
        tokens = count_message_tokens(msg)
        assert tokens > 0


class TestCountMessagesTokens:
    """Tests for counting tokens in message list"""

    def test_empty_list(self) -> None:
        """Empty message list"""
        assert count_messages_tokens([]) == 0

    def test_multiple_messages(self) -> None:
        """Multiple messages"""
        messages = [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
        ]
        tokens = count_messages_tokens(messages)
        assert tokens > 0


class TestGetModelContextLimit:
    """Tests for model context limit lookup"""

    def test_known_model(self) -> None:
        """Known model returns correct limit"""
        assert get_model_context_limit("glm-4.6") == 128000
        assert get_model_context_limit("gpt-4") == 8192
        assert get_model_context_limit("gpt-4o") == 128000

    def test_unknown_model(self) -> None:
        """Unknown model returns default limit"""
        limit = get_model_context_limit("unknown-model-xyz")
        assert limit == MODEL_CONTEXT_LIMITS["default"]

    def test_partial_match(self) -> None:
        """Partial model name matching"""
        # Should match via partial matching
        limit = get_model_context_limit("gpt-4-turbo-preview")
        assert limit > 0


class TestContextStats:
    """Tests for ContextStats"""

    def test_usage_percent(self) -> None:
        """Usage percentage calculation"""
        stats = ContextStats(current_tokens=50000, max_tokens=100000)
        assert stats.usage_percent == 50.0

    def test_remaining_tokens(self) -> None:
        """Remaining tokens calculation"""
        stats = ContextStats(current_tokens=30000, max_tokens=100000)
        assert stats.remaining_tokens == 70000

    def test_is_near_limit(self) -> None:
        """Near limit detection (>80%)"""
        stats = ContextStats(current_tokens=85000, max_tokens=100000)
        assert stats.is_near_limit is True

        stats = ContextStats(current_tokens=50000, max_tokens=100000)
        assert stats.is_near_limit is False

    def test_is_critical(self) -> None:
        """Critical level detection (>95%)"""
        stats = ContextStats(current_tokens=96000, max_tokens=100000)
        assert stats.is_critical is True

        stats = ContextStats(current_tokens=90000, max_tokens=100000)
        assert stats.is_critical is False


class TestContextManager:
    """Tests for ContextManager"""

    def test_initialization(self) -> None:
        """Context manager initialization"""
        cm = ContextManager(model="glm-4.6")
        assert cm.model == "glm-4.6"
        assert cm._stats.max_tokens == 128000

    def test_set_model(self) -> None:
        """Model switching updates limits"""
        cm = ContextManager(model="glm-4.6")
        cm.set_model("gpt-4")
        assert cm.model == "gpt-4"
        assert cm._stats.max_tokens == 8192

    def test_analyze_messages(self) -> None:
        """Message analysis"""
        cm = ContextManager(model="glm-4.6")
        messages = [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
        ]
        stats = cm.analyze_messages(messages)
        assert stats.current_tokens > 0
        assert stats.messages_count == 3
        assert stats.system_tokens > 0
        assert stats.user_tokens > 0
        assert stats.assistant_tokens > 0

    def test_needs_compression(self) -> None:
        """Compression need detection"""
        cm = ContextManager(model="gpt-4", compression_threshold=0.8)
        # GPT-4 has 8192 token limit, so 80% = 6553 tokens

        # Small messages - no compression needed
        small_messages = [
            Message(role="user", content="Hello"),
        ]
        assert cm.needs_compression(small_messages) is False

        # Large messages - compression needed
        # Create a very large message
        large_content = "x" * 40000  # Many characters to exceed limit
        large_messages = [
            Message(role="system", content=large_content),
        ]
        assert cm.needs_compression(large_messages) is True

    def test_compress_messages(self) -> None:
        """Message compression"""
        cm = ContextManager(
            model="gpt-4",
            compression_threshold=0.5,  # 50% threshold
            retained_ratio=0.3,  # Keep 30%
            min_messages_to_keep=2,
        )

        # Create messages that exceed threshold
        messages = [
            Message(role="system", content="System prompt"),
            Message(role="user", content="Message 1"),
            Message(role="assistant", content="Response 1"),
            Message(role="user", content="Message 2"),
            Message(role="assistant", content="Response 2"),
            Message(role="user", content="Message 3"),
            Message(role="assistant", content="Response 3"),
        ]

        compressed = cm.compress_messages(messages)

        # Should keep system prompt
        assert compressed[0].role == "system"
        # Should keep at least min_messages_to_keep
        assert len(compressed) >= cm.min_messages_to_keep + 1  # +1 for system

    def test_compress_trims_tool_messages(self) -> None:
        """Verbose tool outputs get truncated before compression"""
        long_output = "x" * 40000  # Force near-limit
        cm = ContextManager(
            model="gpt-4",
            compression_threshold=0.5,
            retained_ratio=0.5,
            min_messages_to_keep=3,
            tool_message_trim_tokens=100,
            tool_trim_keep_last=0,
        )

        messages = [
            Message(role="system", content="System prompt"),
            Message(role="tool", name="run", content=long_output),
            Message(role="user", content="Message"),
            Message(role="assistant", content="Response"),
        ]

        compressed = cm.compress_messages(messages)

        tool_msg = next(m for m in compressed if m.role == "tool")
        assert tool_msg.content is not None
        assert "truncated" in tool_msg.content
        assert len(tool_msg.content) < len(long_output)

    def test_format_status(self) -> None:
        """Status formatting"""
        cm = ContextManager(model="glm-4.6")
        messages = [Message(role="user", content="Hello")]
        status = cm.format_status(messages)
        assert "Context:" in status
        assert "%" in status

    def test_format_debug(self) -> None:
        """Debug info formatting"""
        cm = ContextManager(model="glm-4.6")
        messages = [
            Message(role="system", content="System"),
            Message(role="user", content="User"),
        ]
        debug = cm.format_debug(messages)
        assert "Context Debug" in debug
        assert "System:" in debug
        assert "User:" in debug


class TestGlobalContextManager:
    """Tests for global context manager"""

    def test_get_context_manager(self) -> None:
        """Get global context manager"""
        from maxagent.utils.context import get_context_manager, reset_context_manager

        reset_context_manager()  # Start fresh
        cm1 = get_context_manager()
        cm2 = get_context_manager()
        assert cm1 is cm2  # Same instance

    def test_reset_context_manager(self) -> None:
        """Reset global context manager"""
        from maxagent.utils.context import get_context_manager, reset_context_manager

        cm1 = get_context_manager()
        cm1.model = "test-model"

        reset_context_manager()
        cm2 = get_context_manager()
        assert cm2.model != "test-model"  # Should be reset
