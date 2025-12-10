"""Tests for token tracking utilities"""

import pytest
from maxagent.utils.tokens import (
    TokenTracker,
    TokenStats,
    get_token_tracker,
    reset_token_tracker,
    MODEL_PRICING,
)
from maxagent.llm.models import Usage


class TestTokenStats:
    """Tests for TokenStats dataclass"""

    def test_default_values(self):
        """Test default values"""
        stats = TokenStats()
        assert stats.prompt_tokens == 0
        assert stats.completion_tokens == 0
        assert stats.total_tokens == 0
        assert stats.request_count == 0
        assert stats.estimated_cost == 0.0

    def test_with_values(self):
        """Test with custom values"""
        stats = TokenStats(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            request_count=3,
            estimated_cost=0.005,
        )
        assert stats.prompt_tokens == 100
        assert stats.completion_tokens == 50
        assert stats.total_tokens == 150
        assert stats.request_count == 3
        assert stats.estimated_cost == 0.005


class TestTokenTracker:
    """Tests for TokenTracker"""

    def test_initial_state(self):
        """Test initial state"""
        tracker = TokenTracker()
        assert tracker.prompt_tokens == 0
        assert tracker.completion_tokens == 0
        assert tracker.total_tokens == 0
        assert tracker.request_count == 0
        assert tracker.model_stats == {}
        assert tracker.current_model == ""

    def test_add_usage(self):
        """Test adding usage"""
        tracker = TokenTracker()
        usage = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        tracker.add_usage(usage, "glm-4-flash")

        assert tracker.prompt_tokens == 100
        assert tracker.completion_tokens == 50
        assert tracker.total_tokens == 150
        assert tracker.request_count == 1
        assert "glm-4-flash" in tracker.model_stats

    def test_add_multiple_usages(self):
        """Test adding multiple usages"""
        tracker = TokenTracker()
        usage1 = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        usage2 = Usage(prompt_tokens=200, completion_tokens=100, total_tokens=300)

        tracker.add_usage(usage1, "glm-4-flash")
        tracker.add_usage(usage2, "glm-4-flash")

        assert tracker.prompt_tokens == 300
        assert tracker.completion_tokens == 150
        assert tracker.total_tokens == 450
        assert tracker.request_count == 2
        assert tracker.model_stats["glm-4-flash"].request_count == 2

    def test_add_usage_multiple_models(self):
        """Test adding usage from multiple models"""
        tracker = TokenTracker()
        usage1 = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        usage2 = Usage(prompt_tokens=200, completion_tokens=100, total_tokens=300)

        tracker.add_usage(usage1, "glm-4-flash")
        tracker.add_usage(usage2, "gpt-4")

        assert tracker.request_count == 2
        assert len(tracker.model_stats) == 2
        assert "glm-4-flash" in tracker.model_stats
        assert "gpt-4" in tracker.model_stats

    def test_calculate_cost(self):
        """Test cost calculation"""
        tracker = TokenTracker()
        usage = Usage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)

        tracker.add_usage(usage, "glm-4-flash")

        # GLM-4-flash pricing: 0.0001 per 1K tokens
        expected_cost = (1000 / 1000) * 0.0001 + (500 / 1000) * 0.0001
        assert abs(tracker.get_total_cost() - expected_cost) < 0.0001

    def test_get_summary(self):
        """Test get_summary method"""
        tracker = TokenTracker()
        usage = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        tracker.add_usage(usage, "glm-4-flash")

        summary = tracker.get_summary()

        assert summary["prompt_tokens"] == 100
        assert summary["completion_tokens"] == 50
        assert summary["total_tokens"] == 150
        assert summary["request_count"] == 1
        assert "estimated_cost_usd" in summary
        assert "glm-4-flash" in summary["models_used"]

    def test_format_short(self):
        """Test format_short method"""
        tracker = TokenTracker()
        usage = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        tracker.add_usage(usage, "glm-4-flash")

        short = tracker.format_short()

        assert "150" in short  # total tokens
        assert "100" in short  # prompt tokens
        assert "50" in short  # completion tokens

    def test_format_last(self):
        """Test format_last method"""
        tracker = TokenTracker()
        usage = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        tracker.add_usage(usage, "glm-4-flash")

        last = tracker.format_last(usage, "glm-4-flash")

        assert "150" in last  # total tokens
        assert "[dim]" in last  # has formatting

    def test_reset(self):
        """Test reset method"""
        tracker = TokenTracker()
        usage = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        tracker.add_usage(usage, "glm-4-flash")

        tracker.reset()

        assert tracker.prompt_tokens == 0
        assert tracker.completion_tokens == 0
        assert tracker.total_tokens == 0
        assert tracker.request_count == 0
        assert tracker.model_stats == {}


class TestGlobalTracker:
    """Tests for global tracker functions"""

    def test_get_token_tracker(self):
        """Test get_token_tracker returns singleton"""
        reset_token_tracker()  # Reset first
        tracker1 = get_token_tracker()
        tracker2 = get_token_tracker()
        assert tracker1 is tracker2

    def test_reset_token_tracker(self):
        """Test reset_token_tracker creates new instance"""
        tracker1 = get_token_tracker()
        usage = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        tracker1.add_usage(usage, "test")

        reset_token_tracker()
        tracker2 = get_token_tracker()

        assert tracker2.total_tokens == 0
        assert tracker2.request_count == 0


class TestModelPricing:
    """Tests for model pricing data"""

    def test_model_pricing_exists(self):
        """Test that model pricing dictionary exists"""
        assert MODEL_PRICING is not None
        assert len(MODEL_PRICING) > 0

    def test_glm_models_have_pricing(self):
        """Test GLM models have pricing"""
        assert "glm-4-flash" in MODEL_PRICING
        assert "glm-4.6" in MODEL_PRICING
        assert "glm-z1-flash" in MODEL_PRICING

    def test_openai_models_have_pricing(self):
        """Test OpenAI models have pricing"""
        assert "gpt-4" in MODEL_PRICING
        assert "gpt-4o" in MODEL_PRICING
        assert "gpt-3.5-turbo" in MODEL_PRICING

    def test_pricing_structure(self):
        """Test pricing structure is correct"""
        for model, pricing in MODEL_PRICING.items():
            assert "input" in pricing
            assert "output" in pricing
            assert isinstance(pricing["input"], (int, float))
            assert isinstance(pricing["output"], (int, float))
            assert pricing["input"] >= 0
            assert pricing["output"] >= 0

    def test_default_pricing_exists(self):
        """Test default pricing exists"""
        assert "default" in MODEL_PRICING
