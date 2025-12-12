"""Tests for thinking strategy selector"""

import pytest

from maxagent.core.thinking_strategy import (
    ThinkingSelector,
    ThinkingStrategy,
    create_thinking_selector,
    get_default_thinking_model,
)


class TestThinkingStrategy:
    """Test ThinkingStrategy enum"""

    def test_strategy_values(self):
        """Test strategy enum has correct values"""
        assert ThinkingStrategy.DISABLED.value == "disabled"
        assert ThinkingStrategy.ENABLED.value == "enabled"
        assert ThinkingStrategy.AUTO.value == "auto"


class TestThinkingSelector:
    """Test ThinkingSelector class"""

    def test_disabled_strategy(self):
        """Test disabled strategy always returns False"""
        selector = ThinkingSelector(strategy=ThinkingStrategy.DISABLED)

        # Should never use thinking
        assert selector.should_use_thinking("complex analysis") is False
        assert selector.should_use_thinking("simple question") is False
        assert selector.should_use_thinking("") is False

    def test_enabled_strategy(self):
        """Test enabled strategy always returns True"""
        selector = ThinkingSelector(strategy=ThinkingStrategy.ENABLED)

        # Should always use thinking
        assert selector.should_use_thinking("complex analysis") is True
        assert selector.should_use_thinking("simple question") is True
        assert selector.should_use_thinking("") is True

    def test_auto_strategy_complex_keywords(self):
        """Test auto strategy detects complex keywords"""
        selector = ThinkingSelector(strategy=ThinkingStrategy.AUTO)

        # Complex English keywords
        assert selector.should_use_thinking("analyze this code") is True
        assert selector.should_use_thinking("debug this issue") is True
        assert selector.should_use_thinking("optimize the algorithm") is True
        assert selector.should_use_thinking("explain why this works") is True

        # Complex Chinese keywords
        assert selector.should_use_thinking("分析这段代码") is True
        assert selector.should_use_thinking("请帮我调试这个问题") is True
        assert selector.should_use_thinking("优化这个算法") is True

    def test_auto_strategy_simple_keywords(self):
        """Test auto strategy ignores simple keywords"""
        selector = ThinkingSelector(strategy=ThinkingStrategy.AUTO)

        # Simple questions without complex keywords
        assert selector.should_use_thinking("what is python") is False
        assert selector.should_use_thinking("show me the version") is False
        assert selector.should_use_thinking("list all files") is False

        # Simple Chinese
        assert selector.should_use_thinking("什么是Python") is False
        assert selector.should_use_thinking("显示版本号") is False

    def test_auto_strategy_code_task_keywords(self):
        """Test auto strategy detects code task keywords"""
        selector = ThinkingSelector(strategy=ThinkingStrategy.AUTO)

        assert selector.should_use_thinking("fix this bug") is True
        assert selector.should_use_thinking("there is an error") is True
        assert selector.should_use_thinking("create a function") is True
        assert selector.should_use_thinking("写一个函数") is True

    def test_auto_strategy_message_length(self):
        """Test auto strategy considers message length"""
        selector = ThinkingSelector(strategy=ThinkingStrategy.AUTO, complexity_threshold=50)

        # Short message without keywords
        assert selector.should_use_thinking("hello") is False

        # Long message exceeds threshold
        long_message = "a" * 100
        assert selector.should_use_thinking(long_message) is True

    def test_auto_strategy_code_blocks(self):
        """Test auto strategy detects code blocks"""
        selector = ThinkingSelector(strategy=ThinkingStrategy.AUTO)

        # With code block
        assert selector.should_use_thinking("```python\ncode\n```") is True
        assert selector.should_use_thinking("def hello():") is True
        assert selector.should_use_thinking("class MyClass:") is True

    def test_auto_strategy_multi_step_tasks(self):
        """Test auto strategy detects multi-step tasks"""
        selector = ThinkingSelector(strategy=ThinkingStrategy.AUTO)

        # Multi-step with numbers
        assert selector.should_use_thinking("1. first step 2. second step") is True

        # Multi-step with words
        assert selector.should_use_thinking("first do this, then do that") is True

        # Chinese multi-step
        assert selector.should_use_thinking("首先做这个，然后做那个") is True

    def test_auto_strategy_multiple_questions(self):
        """Test auto strategy detects multiple questions"""
        selector = ThinkingSelector(strategy=ThinkingStrategy.AUTO)

        # Multiple question marks without simple keywords
        assert selector.should_use_thinking("can you help me? and do this?") is True
        assert selector.should_use_thinking("怎么样？好不好？") is True

        # Note: "what is" is a simple keyword, so it won't trigger thinking
        # even with multiple questions
        assert selector.should_use_thinking("what is this? what is that?") is False

        # Single question without complex keywords
        assert selector.should_use_thinking("hello world") is False

    def test_get_model(self):
        """Test get_model method"""
        # Disabled - always return default
        selector = ThinkingSelector(strategy=ThinkingStrategy.DISABLED)
        assert selector.get_model("default", "thinking") == "default"

        # Enabled - always return thinking
        selector = ThinkingSelector(strategy=ThinkingStrategy.ENABLED)
        assert selector.get_model("default", "thinking") == "thinking"

        # Auto - return default (auto doesn't change model selection)
        selector = ThinkingSelector(strategy=ThinkingStrategy.AUTO)
        assert selector.get_model("default", "thinking") == "default"


class TestFactoryFunction:
    """Test factory function"""

    def test_create_thinking_selector(self):
        """Test create_thinking_selector factory"""
        # Valid strategies
        selector = create_thinking_selector("auto")
        assert selector.strategy == ThinkingStrategy.AUTO

        selector = create_thinking_selector("enabled")
        assert selector.strategy == ThinkingStrategy.ENABLED

        selector = create_thinking_selector("disabled")
        assert selector.strategy == ThinkingStrategy.DISABLED

    def test_create_thinking_selector_case_insensitive(self):
        """Test factory is case insensitive"""
        selector = create_thinking_selector("AUTO")
        assert selector.strategy == ThinkingStrategy.AUTO

        selector = create_thinking_selector("Enabled")
        assert selector.strategy == ThinkingStrategy.ENABLED

    def test_create_thinking_selector_invalid(self):
        """Test factory defaults to AUTO for invalid values"""
        selector = create_thinking_selector("invalid")
        assert selector.strategy == ThinkingStrategy.AUTO

        selector = create_thinking_selector("")
        assert selector.strategy == ThinkingStrategy.AUTO

    def test_create_thinking_selector_threshold(self):
        """Test factory accepts custom threshold"""
        selector = create_thinking_selector("auto", complexity_threshold=200)
        assert selector.complexity_threshold == 200


class TestThinkingModelDefaults:
    """Test thinking model defaults"""

    def test_get_default_thinking_model(self):
        """Test default thinking model lookup"""
        assert get_default_thinking_model("glm") == "glm-4.6"
        assert get_default_thinking_model("deepseek") == "deepseek-reasoner"
        assert get_default_thinking_model("openai") == "o1-preview"
        assert get_default_thinking_model("anthropic") == "claude-3-opus-20240229"

    def test_get_default_thinking_model_case_insensitive(self):
        """Test lookup is case insensitive"""
        assert get_default_thinking_model("GLM") == "glm-4.6"
        assert get_default_thinking_model("DeepSeek") == "deepseek-reasoner"

    def test_get_default_thinking_model_unknown(self):
        """Test unknown provider returns default"""
        assert get_default_thinking_model("unknown") == "glm-4.6"
