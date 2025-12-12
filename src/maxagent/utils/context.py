"""Context management utilities for token counting and compression"""

from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue
from typing import Any, Callable, Optional, TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from maxagent.llm.models import Message


# Model context limits (max input tokens)
MODEL_CONTEXT_LIMITS = {
    # GLM models
    "glm-4.6": 128000,
    "glm-4.6": 128000,
    # OpenAI models
    "gpt-4": 8192,
    "gpt-4-turbo": 128000,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-3.5-turbo": 16385,
    # DeepSeek models
    "deepseek-chat": 64000,
    "deepseek-reasoner": 64000,
    # GitHub Copilot models (via API)
    "claude-3.5-sonnet": 200000,
    "claude-3.7-sonnet": 200000,
    "o1": 128000,
    "o1-mini": 128000,
    "o3-mini": 128000,
    # Default fallback
    "default": 32000,
}


def get_model_context_limit(model: str) -> int:
    """Get the context limit for a model

    Args:
        model: Model name

    Returns:
        Context limit in tokens
    """
    # Direct match
    if model in MODEL_CONTEXT_LIMITS:
        return MODEL_CONTEXT_LIMITS[model]

    # Partial match
    for key, limit in MODEL_CONTEXT_LIMITS.items():
        if key in model.lower() or model.lower() in key:
            return limit

    return MODEL_CONTEXT_LIMITS["default"]


def estimate_tokens(text: str) -> int:
    """Estimate token count for text using character-based heuristic

    This is a fast approximation. For Chinese text, ~1.5 chars per token.
    For English text, ~4 chars per token. We use a weighted average.

    Args:
        text: Text to estimate tokens for

    Returns:
        Estimated token count
    """
    if not text:
        return 0

    # Count Chinese characters (CJK range)
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_chars = len(text) - chinese_chars

    # Chinese: ~1.5 chars/token, Other: ~4 chars/token
    chinese_tokens = chinese_chars / 1.5
    other_tokens = other_chars / 4

    # Add some overhead for special tokens
    return int(chinese_tokens + other_tokens) + 4


def count_message_tokens(message: "Message") -> int:
    """Count tokens in a single message

    Args:
        message: Message object

    Returns:
        Estimated token count
    """
    tokens = 0

    # Role overhead (~3 tokens)
    tokens += 3

    # Content
    if message.content:
        tokens += estimate_tokens(message.content)

    # Tool calls
    if message.tool_calls:
        for tc in message.tool_calls:
            # Function name
            tokens += estimate_tokens(tc.function.name)
            # Arguments (JSON)
            tokens += estimate_tokens(tc.function.arguments)
            # Overhead for tool call structure
            tokens += 10

    # Tool response
    if message.name:
        tokens += estimate_tokens(message.name)

    return tokens


def _truncate_text(text: str, max_tokens: int) -> tuple[str, bool]:
    """Truncate text to roughly fit within a token budget.

    Uses a character-based heuristic to avoid an expensive tokenizer.

    Args:
        text: Original text content
        max_tokens: Approximate token budget to keep

    Returns:
        Tuple of (possibly truncated text, whether truncation occurred)
    """
    if not text or max_tokens <= 0:
        return text, False

    estimated = estimate_tokens(text)
    if estimated <= max_tokens:
        return text, False

    # Roughly map tokens to characters; keep some tail for debugging
    target_chars = max(max_tokens * 4, 80)
    if len(text) <= target_chars:
        return text, False

    head_len = target_chars // 2
    tail_len = target_chars - head_len
    omitted = len(text) - target_chars

    truncated = (
        f"{text[:head_len]}\n...[truncated {omitted} chars]...\n{text[-tail_len:]}"
    )
    return truncated, True


def count_messages_tokens(messages: list["Message"]) -> int:
    """Count total tokens in a list of messages

    Args:
        messages: List of Message objects

    Returns:
        Total estimated token count
    """
    total = 0
    for msg in messages:
        total += count_message_tokens(msg)

    # Add overhead for message boundaries
    total += len(messages) * 2

    return total


@dataclass
class ContextStats:
    """Statistics about current context"""

    current_tokens: int = 0
    max_tokens: int = 128000
    messages_count: int = 0
    system_tokens: int = 0
    user_tokens: int = 0
    assistant_tokens: int = 0
    tool_tokens: int = 0

    @property
    def usage_percent(self) -> float:
        """Get context usage as percentage"""
        if self.max_tokens == 0:
            return 0.0
        return (self.current_tokens / self.max_tokens) * 100

    @property
    def remaining_tokens(self) -> int:
        """Get remaining available tokens"""
        return max(0, self.max_tokens - self.current_tokens)

    @property
    def is_near_limit(self) -> bool:
        """Check if context is near limit (>80%)"""
        return self.usage_percent > 80

    @property
    def is_critical(self) -> bool:
        """Check if context is at critical level (>95%)"""
        return self.usage_percent > 95


@dataclass
class ContextManager:
    """Manage context window for LLM conversations

    Features:
    - Token counting for messages
    - Context usage tracking
    - Automatic compression when approaching limits
    - Debug output for context status
    """

    # Configuration
    model: str = "glm-4.6"
    compression_threshold: float = 0.8  # Start compression at 80% usage
    retained_ratio: float = 0.6  # Keep 60% of tokens after compression
    min_messages_to_keep: int = 4  # Always keep at least N recent messages
    preserve_system_prompt: bool = True  # Never compress system prompt
    response_reserve_ratio: float = 0.1  # Reserve 10% tokens for next turn
    min_reserve_tokens: int = 2000  # Always leave some headroom
    tool_message_trim_tokens: int = 1200  # Trim verbose tool outputs to this budget
    tool_trim_keep_last: int = 1  # Do not trim the most recent tool messages

    # LLM summarization settings
    enable_llm_summary: bool = True  # Use LLM to summarize dropped messages
    summary_max_tokens: int = 1200  # Target budget for summary message
    summary_input_max_tokens: int = 60000  # Max input tokens for summary call

    # Memory persistence
    project_root: Optional[Path] = None  # Used for memory storage

    # Automatic memory injection settings
    enable_memory_injection: bool = True  # Auto inject relevant memories into prompt
    memory_top_k: int = 5  # How many memories to retrieve per turn
    memory_max_tokens: int = 800  # Token budget for injected memory block

    # State
    console: Optional[Console] = None
    debug: bool = False
    _stats: ContextStats = field(default_factory=ContextStats)

    def __post_init__(self) -> None:
        """Initialize after dataclass creation"""
        self._stats.max_tokens = get_model_context_limit(self.model)

    def set_model(self, model: str) -> None:
        """Update model and adjust limits

        Args:
            model: New model name
        """
        self.model = model
        self._stats.max_tokens = get_model_context_limit(model)

    def set_project_root(self, project_root: Path) -> None:
        """Set project root for memory persistence."""
        self.project_root = project_root

    def _reserve_tokens(self, max_tokens: int) -> int:
        """Compute how many tokens to keep free for the next turn."""
        if max_tokens <= 0:
            return 0
        reserve = int(max_tokens * self.response_reserve_ratio)
        return max(reserve, self.min_reserve_tokens)

    def _trim_verbose_tool_messages(self, messages: list["Message"]) -> list["Message"]:
        """Trim older verbose tool outputs to slow prompt growth.

        Only trims tool messages that are not among the most recent
        `tool_trim_keep_last` tool messages to avoid losing fresh context.
        """
        if self.tool_message_trim_tokens <= 0:
            return messages

        trimmed: list["Message"] = []
        # Track which tool messages are protected from trimming (from the end)
        tool_seen = 0
        protected_from_end = self.tool_trim_keep_last

        msg_type = None

        for msg in reversed(messages):
            if msg.role == "tool":
                if tool_seen < protected_from_end:
                    tool_seen += 1
                else:
                    if msg.content:
                        new_content, did_trim = _truncate_text(
                            msg.content, self.tool_message_trim_tokens
                        )
                        if did_trim:
                            if msg_type is None:
                                from maxagent.llm.models import Message as Msg

                                msg_type = Msg

                            msg = msg_type(
                                role=msg.role,
                                content=new_content,
                                tool_call_id=msg.tool_call_id,
                                name=msg.name,
                            )
                            if self.debug and self.console:
                                self.console.print(
                                    "[yellow]Trimmed verbose tool output to reduce context[/yellow]"
                                )
                    tool_seen += 1
            trimmed.insert(0, msg)

        return trimmed

    def analyze_messages(self, messages: list["Message"]) -> ContextStats:
        """Analyze messages and return context statistics

        Args:
            messages: List of messages

        Returns:
            ContextStats with detailed breakdown
        """
        stats = ContextStats(
            max_tokens=get_model_context_limit(self.model),
            messages_count=len(messages),
        )

        for msg in messages:
            tokens = count_message_tokens(msg)
            stats.current_tokens += tokens

            if msg.role == "system":
                stats.system_tokens += tokens
            elif msg.role == "user":
                stats.user_tokens += tokens
            elif msg.role == "assistant":
                stats.assistant_tokens += tokens
            elif msg.role == "tool":
                stats.tool_tokens += tokens

        self._stats = stats
        return stats

    def get_stats(self) -> ContextStats:
        """Get current context statistics"""
        return self._stats

    def needs_compression(self, messages: list["Message"]) -> bool:
        """Check if messages need compression

        Args:
            messages: List of messages

        Returns:
            True if compression is needed
        """
        # First trim overly verbose tool outputs to slow growth
        messages = self._trim_verbose_tool_messages(messages)

        stats = self.analyze_messages(messages)
        reserve_tokens = self._reserve_tokens(stats.max_tokens)
        threshold_tokens = int(stats.max_tokens * self.compression_threshold)
        effective_limit = max(0, stats.max_tokens - reserve_tokens)
        # Trigger when either percentage threshold is reached or headroom vanishes
        return stats.current_tokens >= min(threshold_tokens, effective_limit)

    def compress_messages(
        self,
        messages: list["Message"],
        llm_client: Optional[object] = None,
    ) -> list["Message"]:
        """Compress messages to fit within context limits

        Strategy:
        1. Always preserve system prompt
        2. Always keep recent messages
        3. Summarize or remove older messages

        Args:
            messages: List of messages to compress
            llm_client: Optional LLM client for summarization (not used yet)

        Returns:
            Compressed list of messages
        """
        if not messages:
            return messages

        # First trim overly verbose tool outputs to slow growth and avoid
        # keeping huge tool messages during compression.
        messages = self._trim_verbose_tool_messages(messages)

        stats = self.analyze_messages(messages)

        # If under threshold, no compression needed
        if not stats.is_near_limit:
            return messages

        if self.debug and self.console:
            self.console.print(
                f"[yellow]Context compression triggered: {stats.usage_percent:.1f}% "
                f"({stats.current_tokens:,}/{stats.max_tokens:,} tokens)[/yellow]"
            )

        # Calculate target token count
        reserve_tokens = self._reserve_tokens(stats.max_tokens)
        target_tokens = int(max(stats.max_tokens - reserve_tokens, 0) * self.retained_ratio)

        # Separate system message and other messages
        system_messages: list["Message"] = []
        other_messages: list["Message"] = []

        for msg in messages:
            if msg.role == "system" and self.preserve_system_prompt:
                system_messages.append(msg)
            else:
                other_messages.append(msg)

        # Calculate tokens used by system prompt
        system_tokens = sum(count_message_tokens(m) for m in system_messages)
        available_tokens = target_tokens - system_tokens

        if available_tokens <= 0:
            # System prompt alone exceeds target, keep minimal
            if self.debug and self.console:
                self.console.print("[red]Warning: System prompt exceeds target tokens[/red]")
            return system_messages + other_messages[-self.min_messages_to_keep :]

        # Keep messages from the end until we hit the limit
        kept_messages: list["Message"] = []
        current_tokens = 0

        # Always try to keep minimum number of recent messages
        for msg in reversed(other_messages):
            msg_tokens = count_message_tokens(msg)

            if len(kept_messages) < self.min_messages_to_keep:
                # Must keep this message
                kept_messages.insert(0, msg)
                current_tokens += msg_tokens
            elif current_tokens + msg_tokens <= available_tokens:
                # Can keep this message
                kept_messages.insert(0, msg)
                current_tokens += msg_tokens
            else:
                # Stop adding messages
                break

        result = system_messages + kept_messages

        if self.debug and self.console:
            new_stats = self.analyze_messages(result)
            self.console.print(
                f"[green]Compressed: {stats.messages_count} -> {new_stats.messages_count} messages, "
                f"{stats.current_tokens:,} -> {new_stats.current_tokens:,} tokens "
                f"({new_stats.usage_percent:.1f}%)[/green]"
            )

        return result

    async def compress_messages_with_summary(
        self,
        messages: list["Message"],
        llm_client: Any,
        project_root: Optional[Path] = None,
    ) -> list["Message"]:
        """Compress messages and summarize removed history using an LLM.

        This implements a rolling summary:
        - Older messages are summarized into a single assistant message
        - Previous summaries are merged into the new summary
        - Memory cards are persisted for later retrieval

        Args:
            messages: Current conversation messages.
            llm_client: LLM client used to generate summaries.
            project_root: Optional root to store memory under `.maxagent/memory.json`.

        Returns:
            Compressed message list containing a summary + recent context.
        """
        if not messages or not self.enable_llm_summary:
            return self.compress_messages(messages)

        # Trim verbose tool outputs first
        messages = self._trim_verbose_tool_messages(messages)
        stats = self.analyze_messages(messages)
        if not stats.is_near_limit:
            return messages

        reserve_tokens = self._reserve_tokens(stats.max_tokens)
        target_tokens = int(max(stats.max_tokens - reserve_tokens, 0) * self.retained_ratio)

        # Separate system prompt, existing summary, and other messages
        from maxagent.utils.context_summary import (
            SUMMARY_MESSAGE_NAME,
            SUMMARY_HEADER,
            ContextSummarizer,
            MemoryStore,
            get_project_memory_path,
        )

        system_messages: list["Message"] = []
        other_messages: list["Message"] = []
        previous_summary: Optional[str] = None

        for msg in messages:
            if msg.role == "assistant" and msg.name == SUMMARY_MESSAGE_NAME:
                previous_summary = msg.content or ""
                continue
            if msg.role == "system" and self.preserve_system_prompt:
                system_messages.append(msg)
            else:
                other_messages.append(msg)

        system_tokens = sum(count_message_tokens(m) for m in system_messages)
        available_tokens = target_tokens - system_tokens
        if available_tokens <= 0:
            return system_messages + other_messages[-self.min_messages_to_keep :]

        # Leave room for summary message
        keep_budget = max(0, available_tokens - self.summary_max_tokens)

        kept_messages: list["Message"] = []
        current_tokens = 0
        for msg in reversed(other_messages):
            msg_tokens = count_message_tokens(msg)
            if len(kept_messages) < self.min_messages_to_keep:
                kept_messages.insert(0, msg)
                current_tokens += msg_tokens
            elif current_tokens + msg_tokens <= keep_budget:
                kept_messages.insert(0, msg)
                current_tokens += msg_tokens
            else:
                break

        # Messages to summarize are those not kept (preserve order)
        kept_set = set(id(m) for m in kept_messages)
        to_summarize = [m for m in other_messages if id(m) not in kept_set]

        if not to_summarize and not previous_summary:
            return system_messages + kept_messages

        summarizer = ContextSummarizer(
            llm_client,
            model=None,
            max_output_tokens=self.summary_max_tokens,
            max_input_tokens=self.summary_input_max_tokens,
        )
        summary_res = await summarizer.summarize(to_summarize, previous_summary=previous_summary)

        from maxagent.llm.models import Message as Msg

        summary_msg = Msg(
            role="assistant",
            name=SUMMARY_MESSAGE_NAME,
            content=f"{SUMMARY_HEADER}\n{summary_res.summary_text}".strip(),
        )

        result = system_messages + [summary_msg] + kept_messages

        # Ensure we fit target by dropping oldest kept messages if needed
        while count_messages_tokens(result) > target_tokens and kept_messages:
            kept_messages.pop(0)
            result = system_messages + [summary_msg] + kept_messages

        # Persist memories
        root = project_root or self.project_root or Path.cwd()
        store = MemoryStore(get_project_memory_path(root))
        store.append(summary_res.memories)

        if self.debug and self.console:
            new_stats = self.analyze_messages(result)
            self.console.print(
                f"[green]Summarized {len(to_summarize)} msgs -> summary + {len(kept_messages)} recent msgs "
                f"({new_stats.current_tokens:,}/{new_stats.max_tokens:,} tokens)[/green]"
            )

        return result

    def format_status(self, messages: list["Message"]) -> str:
        """Format context status for display

        Args:
            messages: List of messages

        Returns:
            Formatted status string
        """
        stats = self.analyze_messages(messages)

        # Color based on usage
        if stats.is_critical:
            color = "red"
        elif stats.is_near_limit:
            color = "yellow"
        else:
            color = "dim"

        return (
            f"[{color}]Context: {stats.current_tokens:,}/{stats.max_tokens:,} "
            f"({stats.usage_percent:.1f}%) | "
            f"{stats.messages_count} msgs[/{color}]"
        )

    def format_debug(self, messages: list["Message"]) -> str:
        """Format detailed debug info

        Args:
            messages: List of messages

        Returns:
            Detailed debug string
        """
        stats = self.analyze_messages(messages)

        lines = [
            f"Context Debug [{self.model}]",
            f"├─ Total: {stats.current_tokens:,}/{stats.max_tokens:,} tokens ({stats.usage_percent:.1f}%)",
            f"├─ Messages: {stats.messages_count}",
            f"├─ System: {stats.system_tokens:,} tokens",
            f"├─ User: {stats.user_tokens:,} tokens",
            f"├─ Assistant: {stats.assistant_tokens:,} tokens",
            f"├─ Tool: {stats.tool_tokens:,} tokens",
            f"└─ Remaining: {stats.remaining_tokens:,} tokens",
        ]

        return "\n".join(lines)

    def display_status(
        self,
        messages: list["Message"],
        console: Optional[Console] = None,
        detailed: bool = False,
    ) -> None:
        """Display context status to console

        Args:
            messages: List of messages
            console: Rich console (uses self.console if not provided)
            detailed: Show detailed breakdown
        """
        con = console or self.console
        if con is None:
            con = Console()

        if detailed:
            con.print(self.format_debug(messages))
        else:
            con.print(self.format_status(messages))


# Global context manager instance
_global_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """Get global context manager instance

    Returns:
        Global ContextManager instance
    """
    global _global_context_manager
    if _global_context_manager is None:
        _global_context_manager = ContextManager()
    return _global_context_manager


def reset_context_manager() -> None:
    """Reset global context manager"""
    global _global_context_manager
    _global_context_manager = ContextManager()


class AsyncContextManager:
    """Asynchronous context manager that performs compression in background

    This manager runs context analysis and compression in a background thread
    to avoid blocking the main event loop during LLM interactions.

    Features:
    - Non-blocking token counting
    - Background compression
    - Cached statistics
    - Thread-safe operations
    """

    def __init__(
        self,
        model: str = "glm-4.6",
        compression_threshold: float = 0.8,
        retained_ratio: float = 0.6,
        min_messages_to_keep: int = 4,
        response_reserve_ratio: float = 0.1,
        min_reserve_tokens: int = 2000,
        tool_message_trim_tokens: int = 1200,
        tool_trim_keep_last: int = 1,
        max_workers: int = 2,
    ) -> None:
        """Initialize async context manager

        Args:
            model: Model name for context limits
            compression_threshold: Trigger compression at this usage %
            retained_ratio: Keep this % of tokens after compression
            min_messages_to_keep: Always keep at least N recent messages
            max_workers: Number of background workers
        """
        self.model = model
        self.compression_threshold = compression_threshold
        self.retained_ratio = retained_ratio
        self.min_messages_to_keep = min_messages_to_keep
        self.response_reserve_ratio = response_reserve_ratio
        self.min_reserve_tokens = min_reserve_tokens
        self.tool_message_trim_tokens = tool_message_trim_tokens
        self.tool_trim_keep_last = tool_trim_keep_last

        # Background processing
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()

        # Cached stats
        self._cached_stats: Optional[ContextStats] = None
        self._stats_valid = False

        # Compression callback
        self._on_compress: Optional[Callable[[list["Message"], list["Message"]], None]] = None

        # Console for debug output
        self.console: Optional[Console] = None
        self.debug = False

    def set_model(self, model: str) -> None:
        """Update model and invalidate cached stats"""
        with self._lock:
            self.model = model
            self._stats_valid = False

    def _reserve_tokens(self, max_tokens: int) -> int:
        """Compute headroom to keep free for next response."""
        if max_tokens <= 0:
            return 0
        reserve = int(max_tokens * self.response_reserve_ratio)
        return max(reserve, self.min_reserve_tokens)

    def _trim_verbose_tool_messages(self, messages: list["Message"]) -> list["Message"]:
        """Trim older tool outputs to reduce prompt growth (background version)."""
        if self.tool_message_trim_tokens <= 0:
            return messages

        trimmed: list["Message"] = []
        tool_seen = 0
        protected_from_end = self.tool_trim_keep_last

        msg_type = None

        for msg in reversed(messages):
            if msg.role == "tool":
                if tool_seen < protected_from_end:
                    tool_seen += 1
                else:
                    if msg.content:
                        new_content, did_trim = _truncate_text(
                            msg.content, self.tool_message_trim_tokens
                        )
                        if did_trim:
                            if msg_type is None:
                                from maxagent.llm.models import Message as Msg

                                msg_type = Msg

                            msg = msg_type(
                                role=msg.role,
                                content=new_content,
                                tool_call_id=msg.tool_call_id,
                                name=msg.name,
                            )
                    tool_seen += 1
            trimmed.insert(0, msg)

        return trimmed

    def set_on_compress_callback(
        self,
        callback: Callable[[list["Message"], list["Message"]], None],
    ) -> None:
        """Set callback to be called when compression occurs

        Args:
            callback: Function(old_messages, new_messages) called after compression
        """
        self._on_compress = callback

    async def analyze_messages_async(
        self,
        messages: list["Message"],
    ) -> ContextStats:
        """Analyze messages asynchronously in background thread

        Args:
            messages: List of messages to analyze

        Returns:
            ContextStats with token breakdown
        """
        loop = asyncio.get_event_loop()
        stats = await loop.run_in_executor(
            self._executor,
            self._analyze_messages_sync,
            messages,
        )

        with self._lock:
            self._cached_stats = stats
            self._stats_valid = True

        return stats

    def _analyze_messages_sync(self, messages: list["Message"]) -> ContextStats:
        """Synchronous message analysis (runs in thread)"""
        stats = ContextStats(
            max_tokens=get_model_context_limit(self.model),
            messages_count=len(messages),
        )

        for msg in messages:
            tokens = count_message_tokens(msg)
            stats.current_tokens += tokens

            if msg.role == "system":
                stats.system_tokens += tokens
            elif msg.role == "user":
                stats.user_tokens += tokens
            elif msg.role == "assistant":
                stats.assistant_tokens += tokens
            elif msg.role == "tool":
                stats.tool_tokens += tokens

        return stats

    def get_cached_stats(self) -> Optional[ContextStats]:
        """Get cached stats without re-analyzing

        Returns:
            Cached ContextStats or None if not available
        """
        with self._lock:
            if self._stats_valid:
                return self._cached_stats
        return None

    async def needs_compression_async(
        self,
        messages: list["Message"],
    ) -> bool:
        """Check if compression is needed (async)

        Args:
            messages: List of messages

        Returns:
            True if compression is needed
        """
        stats = await self.analyze_messages_async(messages)
        reserve_tokens = self._reserve_tokens(stats.max_tokens)
        threshold_tokens = int(stats.max_tokens * self.compression_threshold)
        effective_limit = max(0, stats.max_tokens - reserve_tokens)
        return stats.current_tokens >= min(threshold_tokens, effective_limit)

    async def compress_messages_async(
        self,
        messages: list["Message"],
        llm_client: Optional[Any] = None,
    ) -> list["Message"]:
        """Compress messages asynchronously in background

        Args:
            messages: List of messages to compress
            llm_client: Optional LLM client for summarization

        Returns:
            Compressed list of messages
        """
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            self._compress_messages_sync,
            messages,
        )

        # Call callback if set
        if self._on_compress and len(result) < len(messages):
            self._on_compress(messages, result)

        return result

    def _compress_messages_sync(
        self,
        messages: list["Message"],
    ) -> list["Message"]:
        """Synchronous message compression (runs in thread)"""
        if not messages:
            return messages

        # Trim verbose tool messages before compression to slow growth
        messages = self._trim_verbose_tool_messages(messages)

        stats = self._analyze_messages_sync(messages)

        # If under threshold, no compression needed
        if stats.usage_percent < (self.compression_threshold * 100):
            return messages

        if self.debug and self.console:
            self.console.print(
                f"[yellow]Background compression: {stats.usage_percent:.1f}% "
                f"({stats.current_tokens:,}/{stats.max_tokens:,} tokens)[/yellow]"
            )

        # Calculate target with reserved headroom
        reserve_tokens = self._reserve_tokens(stats.max_tokens)
        target_tokens = int(max(stats.max_tokens - reserve_tokens, 0) * self.retained_ratio)

        # Separate system and other messages
        system_messages: list["Message"] = []
        other_messages: list["Message"] = []

        for msg in messages:
            if msg.role == "system":
                system_messages.append(msg)
            else:
                other_messages.append(msg)

        # Calculate available tokens
        system_tokens = sum(count_message_tokens(m) for m in system_messages)
        available_tokens = target_tokens - system_tokens

        if available_tokens <= 0:
            return system_messages + other_messages[-self.min_messages_to_keep :]

        # Keep messages from end
        kept_messages: list["Message"] = []
        current_tokens = 0

        for msg in reversed(other_messages):
            msg_tokens = count_message_tokens(msg)

            if len(kept_messages) < self.min_messages_to_keep:
                kept_messages.insert(0, msg)
                current_tokens += msg_tokens
            elif current_tokens + msg_tokens <= available_tokens:
                kept_messages.insert(0, msg)
                current_tokens += msg_tokens
            else:
                break

        result = system_messages + kept_messages

        if self.debug and self.console:
            new_stats = self._analyze_messages_sync(result)
            self.console.print(
                f"[green]Compressed: {stats.messages_count} -> {new_stats.messages_count} msgs, "
                f"{stats.current_tokens:,} -> {new_stats.current_tokens:,} tokens[/green]"
            )

        return result

    def schedule_analysis(
        self,
        messages: list["Message"],
        callback: Optional[Callable[[ContextStats], None]] = None,
    ) -> None:
        """Schedule background analysis without blocking

        Args:
            messages: Messages to analyze
            callback: Optional callback with results
        """

        def _run_analysis():
            stats = self._analyze_messages_sync(messages)
            with self._lock:
                self._cached_stats = stats
                self._stats_valid = True
            if callback:
                callback(stats)

        self._executor.submit(_run_analysis)

    def schedule_compression(
        self,
        messages: list["Message"],
        callback: Callable[[list["Message"]], None],
    ) -> None:
        """Schedule background compression without blocking

        Args:
            messages: Messages to compress
            callback: Callback with compressed messages
        """

        def _run_compression():
            result = self._compress_messages_sync(messages)
            if self._on_compress and len(result) < len(messages):
                self._on_compress(messages, result)
            callback(result)

        self._executor.submit(_run_compression)

    async def auto_compress_if_needed(
        self,
        messages: list["Message"],
    ) -> list["Message"]:
        """Automatically compress if usage exceeds threshold

        This is the main method for automatic context management.

        Args:
            messages: Current message list

        Returns:
            Possibly compressed message list
        """
        if await self.needs_compression_async(messages):
            return await self.compress_messages_async(messages)
        return messages

    def format_status(self, messages: list["Message"]) -> str:
        """Format context status for display

        Args:
            messages: List of messages

        Returns:
            Formatted status string
        """
        # Use cached stats if available
        stats = self.get_cached_stats()
        if stats is None:
            stats = self._analyze_messages_sync(messages)

        if stats.is_critical:
            color = "red"
        elif stats.is_near_limit:
            color = "yellow"
        else:
            color = "dim"

        return (
            f"[{color}]Context: {stats.current_tokens:,}/{stats.max_tokens:,} "
            f"({stats.usage_percent:.1f}%)[/{color}]"
        )

    def shutdown(self) -> None:
        """Shutdown background executor"""
        self._executor.shutdown(wait=False)

    def __del__(self):
        """Cleanup on deletion"""
        try:
            self._executor.shutdown(wait=False)
        except Exception:
            pass


# Global async context manager
_global_async_context_manager: Optional[AsyncContextManager] = None


def get_async_context_manager() -> AsyncContextManager:
    """Get global async context manager

    Returns:
        Global AsyncContextManager instance
    """
    global _global_async_context_manager
    if _global_async_context_manager is None:
        _global_async_context_manager = AsyncContextManager()
    return _global_async_context_manager


def reset_async_context_manager() -> None:
    """Reset global async context manager"""
    global _global_async_context_manager
    if _global_async_context_manager is not None:
        _global_async_context_manager.shutdown()
    _global_async_context_manager = AsyncContextManager()
