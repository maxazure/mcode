"""Thinking strategy selector for automatic thinking mode"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class ThinkingStrategy(str, Enum):
    """Thinking mode strategy"""

    DISABLED = "disabled"  # Never use thinking model
    ENABLED = "enabled"  # Always use thinking model
    AUTO = "auto"  # Automatically decide based on question complexity


class ThinkingSelector:
    """Select whether to enable thinking based on user input

    Supports three strategies:
    - disabled: Never use thinking model
    - enabled: Always use thinking model
    - auto: Automatically decide based on question complexity
    """

    # Complex question keywords - prefer thinking
    COMPLEX_KEYWORDS_ZH = [
        "分析",
        "推理",
        "证明",
        "解释为什么",
        "原因",
        "比较",
        "对比",
        "评估",
        "权衡",
        "设计",
        "架构",
        "实现方案",
        "调试",
        "排查",
        "优化",
        "重构",
        "算法",
        "复杂度",
        "性能",
        "安全",
        "漏洞",
        "风险",
        "为什么",
        "如何实现",
        "怎么做",
        "深入",
        "详细",
        "全面",
    ]

    COMPLEX_KEYWORDS_EN = [
        "analyze",
        "analyse",
        "reason",
        "prove",
        "explain why",
        "compare",
        "contrast",
        "evaluate",
        "assess",
        "trade-off",
        "design",
        "architect",
        "implement",
        "debug",
        "troubleshoot",
        "optimize",
        "refactor",
        "algorithm",
        "complexity",
        "performance",
        "security",
        "vulnerability",
        "risk",
        "why",
        "how to implement",
        "in-depth",
        "detailed",
        "comprehensive",
    ]

    # Simple question keywords - no thinking needed
    SIMPLE_KEYWORDS_ZH = [
        "是什么",
        "什么是",
        "定义",
        "列出",
        "显示",
        "查看",
        "打开",
        "读取",
        "格式",
        "语法",
        "示例",
        "例子",
        "版本",
        "安装",
        "配置",
    ]

    SIMPLE_KEYWORDS_EN = [
        "what is",
        "define",
        "definition",
        "list",
        "show",
        "display",
        "open",
        "read",
        "format",
        "syntax",
        "example",
        "version",
        "install",
        "setup",
    ]

    # Code task keywords - prefer thinking
    CODE_TASK_KEYWORDS = [
        "bug",
        "error",
        "exception",
        "crash",
        "问题",
        "写一个",
        "编写",
        "创建",
        "生成",
        "write",
        "create",
        "generate",
        "implement",
        "修复",
        "fix",
        "修改",
        "改进",
        "improve",
        "重写",
        "rewrite",
        "优化",
        "optimize",
    ]

    def __init__(
        self,
        strategy: ThinkingStrategy = ThinkingStrategy.AUTO,
        complexity_threshold: int = 150,
    ):
        """
        Args:
            strategy: Thinking strategy
            complexity_threshold: In AUTO mode, enable thinking if message length exceeds this
        """
        self.strategy = strategy
        self.complexity_threshold = complexity_threshold

    def should_use_thinking(self, message: str) -> bool:
        """Determine whether to enable thinking mode

        Args:
            message: User message

        Returns:
            True if thinking model should be used
        """
        if self.strategy == ThinkingStrategy.DISABLED:
            return False
        if self.strategy == ThinkingStrategy.ENABLED:
            return True

        # AUTO mode: analyze question complexity
        return self._analyze_complexity(message)

    def _analyze_complexity(self, message: str) -> bool:
        """Analyze message complexity to decide if deep thinking is needed

        Uses heuristic rules:
        1. Check for complex question keywords
        2. Check for code task keywords
        3. Check message length
        4. Check for simple question keywords (exclude)
        """
        message_lower = message.lower()

        # If contains simple keywords and no complex keywords, don't use thinking
        has_simple = any(
            keyword in message_lower
            for keyword in self.SIMPLE_KEYWORDS_ZH + self.SIMPLE_KEYWORDS_EN
        )
        has_complex = any(
            k in message_lower for k in self.COMPLEX_KEYWORDS_ZH + self.COMPLEX_KEYWORDS_EN
        )

        if has_simple and not has_complex:
            return False

        # Check for complex question keywords
        if has_complex:
            return True

        # Check for code task keywords
        for keyword in self.CODE_TASK_KEYWORDS:
            if keyword in message_lower:
                return True

        # Check message length
        if len(message) > self.complexity_threshold:
            return True

        # Check for code blocks
        if "```" in message or "def " in message or "class " in message:
            return True

        # Check for multi-step tasks
        step_indicators = [
            "1.",
            "2.",
            "3.",
            "first",
            "then",
            "finally",
            "next",
            "首先",
            "然后",
            "最后",
            "接下来",
            "第一",
            "第二",
            "第三",
        ]
        step_count = sum(1 for indicator in step_indicators if indicator in message_lower)
        if step_count >= 2:
            return True

        # Check for question marks (multiple questions often need thinking)
        question_marks = message.count("?") + message.count("？")
        if question_marks >= 2:
            return True

        return False

    def get_model(self, default_model: str, thinking_model: str) -> str:
        """Get the model to use based on strategy

        Args:
            default_model: Default model
            thinking_model: Thinking model

        Returns:
            Model name to use
        """
        if self.strategy == ThinkingStrategy.ENABLED:
            return thinking_model
        return default_model


def create_thinking_selector(
    strategy: str = "auto",
    complexity_threshold: int = 150,
) -> ThinkingSelector:
    """Factory function to create ThinkingSelector

    Args:
        strategy: Strategy string ("auto", "enabled", "disabled")
        complexity_threshold: Complexity threshold for AUTO mode

    Returns:
        ThinkingSelector instance
    """
    try:
        strat = ThinkingStrategy(strategy.lower())
    except ValueError:
        strat = ThinkingStrategy.AUTO

    return ThinkingSelector(strategy=strat, complexity_threshold=complexity_threshold)


# Provider-specific thinking model defaults
THINKING_MODEL_DEFAULTS = {
    "glm": "glm-z1-flash",
    "deepseek": "deepseek-reasoner",
    "openai": "o1-preview",  # OpenAI's reasoning model
    "anthropic": "claude-3-opus-20240229",  # Claude with extended thinking
}


def get_default_thinking_model(provider: str) -> str:
    """Get the default thinking model for a provider

    Args:
        provider: Provider name (glm, deepseek, openai, anthropic)

    Returns:
        Default thinking model name
    """
    return THINKING_MODEL_DEFAULTS.get(provider.lower(), "glm-z1-flash")
