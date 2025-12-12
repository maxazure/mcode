"""Token usage tracking utilities"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from rich.console import Console
from rich.table import Table

from maxagent.llm.models import Usage


# Model pricing per 1K tokens (input/output) in USD
# Reference: https://open.bigmodel.cn/pricing (GLM)
# Reference: https://openai.com/pricing (OpenAI)
MODEL_PRICING = {
    # GLM models (CNY, converted to USD roughly)
    "glm-4.6": {"input": 0.0001, "output": 0.0001},  # 0.1元/百万tokens
    # OpenAI models
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    # DeepSeek models
    "deepseek-chat": {"input": 0.00014, "output": 0.00028},
    "deepseek-reasoner": {"input": 0.00055, "output": 0.00219},
    # Default fallback
    "default": {"input": 0.001, "output": 0.002},
}


@dataclass
class TokenStats:
    """Statistics for token usage"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    request_count: int = 0
    estimated_cost: float = 0.0


@dataclass
class TokenTracker:
    """Track token usage across multiple API calls"""

    # Accumulated stats
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    request_count: int = 0

    # Per-model stats
    model_stats: dict[str, TokenStats] = field(default_factory=dict)

    # Session info
    current_model: str = ""

    def add_usage(self, usage: Usage, model: Optional[str] = None) -> None:
        """Add usage from a single API call

        Args:
            usage: Usage object from API response
            model: Model name for cost calculation
        """
        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens
        self.request_count += 1

        if model:
            self.current_model = model

        # Track per-model stats
        model_key = model or self.current_model or "unknown"
        if model_key not in self.model_stats:
            self.model_stats[model_key] = TokenStats()

        stats = self.model_stats[model_key]
        stats.prompt_tokens += usage.prompt_tokens
        stats.completion_tokens += usage.completion_tokens
        stats.total_tokens += usage.total_tokens
        stats.request_count += 1
        stats.estimated_cost += self._calculate_cost(usage, model_key)

    def _calculate_cost(self, usage: Usage, model: str) -> float:
        """Calculate estimated cost for usage

        Args:
            usage: Token usage
            model: Model name

        Returns:
            Estimated cost in USD
        """
        # Find pricing for model
        pricing = MODEL_PRICING.get(model)
        if not pricing:
            # Try to find a partial match
            for key in MODEL_PRICING:
                if key in model.lower() or model.lower() in key:
                    pricing = MODEL_PRICING[key]
                    break

        if not pricing:
            pricing = MODEL_PRICING["default"]

        input_cost = (usage.prompt_tokens / 1000) * pricing["input"]
        output_cost = (usage.completion_tokens / 1000) * pricing["output"]
        return input_cost + output_cost

    def get_total_cost(self) -> float:
        """Get total estimated cost across all models"""
        return sum(stats.estimated_cost for stats in self.model_stats.values())

    def get_summary(self) -> dict:
        """Get summary of token usage

        Returns:
            Dictionary with usage summary
        """
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "request_count": self.request_count,
            "estimated_cost_usd": round(self.get_total_cost(), 6),
            "models_used": list(self.model_stats.keys()),
        }

    def format_short(self) -> str:
        """Format a short one-line summary

        Returns:
            Short summary string
        """
        cost = self.get_total_cost()
        if cost > 0:
            return f"Tokens: {self.total_tokens:,} (↑{self.prompt_tokens:,} ↓{self.completion_tokens:,}) | Cost: ${cost:.4f}"
        return (
            f"Tokens: {self.total_tokens:,} (↑{self.prompt_tokens:,} ↓{self.completion_tokens:,})"
        )

    def format_last(self, usage: Usage, model: Optional[str] = None) -> str:
        """Format the last request's usage

        Args:
            usage: Last usage object
            model: Model name

        Returns:
            Formatted string
        """
        model_key = model or self.current_model or "unknown"
        pricing = MODEL_PRICING.get(model_key, MODEL_PRICING["default"])
        cost = (usage.prompt_tokens / 1000) * pricing["input"] + (
            usage.completion_tokens / 1000
        ) * pricing["output"]

        return f"[dim]Tokens: {usage.total_tokens:,} (↑{usage.prompt_tokens:,} ↓{usage.completion_tokens:,}) | ${cost:.4f}[/dim]"

    def display(self, console: Optional[Console] = None) -> None:
        """Display detailed usage statistics

        Args:
            console: Rich console for output
        """
        if console is None:
            console = Console()

        table = Table(title="Token Usage Statistics")
        table.add_column("Model", style="cyan")
        table.add_column("Requests", justify="right")
        table.add_column("Input", justify="right", style="green")
        table.add_column("Output", justify="right", style="yellow")
        table.add_column("Total", justify="right", style="bold")
        table.add_column("Cost (USD)", justify="right", style="magenta")

        for model, stats in self.model_stats.items():
            table.add_row(
                model,
                str(stats.request_count),
                f"{stats.prompt_tokens:,}",
                f"{stats.completion_tokens:,}",
                f"{stats.total_tokens:,}",
                f"${stats.estimated_cost:.4f}",
            )

        # Add total row
        table.add_section()
        table.add_row(
            "[bold]Total[/bold]",
            str(self.request_count),
            f"{self.prompt_tokens:,}",
            f"{self.completion_tokens:,}",
            f"{self.total_tokens:,}",
            f"${self.get_total_cost():.4f}",
            style="bold",
        )

        console.print(table)

    def reset(self) -> None:
        """Reset all statistics"""
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.request_count = 0
        self.model_stats = {}
        self.current_model = ""


# Global token tracker instance
_global_tracker: Optional[TokenTracker] = None


def get_token_tracker() -> TokenTracker:
    """Get global token tracker instance

    Returns:
        Global TokenTracker instance
    """
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = TokenTracker()
    return _global_tracker


def reset_token_tracker() -> None:
    """Reset global token tracker"""
    global _global_tracker
    _global_tracker = TokenTracker()
