"""Utilities for handling deep thinking responses (GLM glm-z1-flash)"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown


@dataclass
class ThinkingResult:
    """Parsed thinking result"""

    thinking: Optional[str]  # Content inside <think> tags
    response: str  # Content outside <think> tags
    has_thinking: bool


def parse_thinking(content: str) -> ThinkingResult:
    """Parse response content to extract thinking and response parts
    
    GLM deep thinking models (glm-z1-flash) return thinking in <think>...</think> tags.
    
    Args:
        content: Raw response content from the model
        
    Returns:
        ThinkingResult with thinking and response parts separated
    """
    # Pattern to match <think>...</think> tags
    think_pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)

    match = think_pattern.search(content)

    if match:
        thinking = match.group(1).strip()
        # Remove the thinking part from the response
        response = think_pattern.sub("", content).strip()
        return ThinkingResult(
            thinking=thinking,
            response=response,
            has_thinking=True,
        )
    else:
        return ThinkingResult(
            thinking=None,
            response=content.strip(),
            has_thinking=False,
        )


def display_thinking(
    thinking_result: ThinkingResult,
    console: Console,
    show_thinking: bool = True,
    collapsed: bool = False,
) -> None:
    """Display thinking and response with Rich formatting
    
    Args:
        thinking_result: Parsed thinking result
        console: Rich console for output
        show_thinking: Whether to show the thinking part
        collapsed: Whether to show thinking in a collapsed/summary form
    """
    if thinking_result.has_thinking and show_thinking:
        thinking_content = thinking_result.thinking or ""

        if collapsed:
            # Show a summary instead of full thinking
            lines = thinking_content.split("\n")
            if len(lines) > 5:
                summary = "\n".join(lines[:3]) + f"\n... ({len(lines) - 3} more lines)"
            else:
                summary = thinking_content

            console.print(
                Panel(
                    summary,
                    title="[dim]Thinking (collapsed)[/dim]",
                    border_style="dim",
                    expand=False,
                )
            )
        else:
            console.print(
                Panel(
                    Markdown(thinking_content),
                    title="[cyan]Thinking[/cyan]",
                    border_style="cyan",
                    expand=False,
                )
            )

        console.print()  # Empty line between thinking and response

    # Display the response
    if thinking_result.response:
        console.print(Markdown(thinking_result.response))


def format_thinking_for_stream(
    content: str,
    in_thinking: bool = False,
) -> tuple[str, bool, Optional[str]]:
    """Process streaming content to handle thinking tags
    
    This is useful for processing streaming responses where <think> tags
    may span multiple chunks.
    
    Args:
        content: Current content chunk
        in_thinking: Whether we're currently inside a thinking block
        
    Returns:
        Tuple of (display_content, still_in_thinking, thinking_content)
    """
    display_content = ""
    thinking_content = None

    if in_thinking:
        # We're inside a thinking block, look for closing tag
        if "</think>" in content:
            parts = content.split("</think>", 1)
            thinking_content = parts[0]
            display_content = parts[1] if len(parts) > 1 else ""
            in_thinking = False
        else:
            thinking_content = content
    else:
        # Not in thinking block, look for opening tag
        if "<think>" in content:
            parts = content.split("<think>", 1)
            display_content = parts[0]
            remaining = parts[1] if len(parts) > 1 else ""

            if "</think>" in remaining:
                # Complete thinking block in this chunk
                think_parts = remaining.split("</think>", 1)
                thinking_content = think_parts[0]
                display_content += think_parts[1] if len(think_parts) > 1 else ""
            else:
                # Thinking continues to next chunk
                thinking_content = remaining
                in_thinking = True
        else:
            display_content = content

    return display_content, in_thinking, thinking_content


class ThinkingStreamProcessor:
    """Process streaming content with thinking tags"""

    def __init__(self, show_thinking: bool = True, console: Optional[Console] = None):
        self.show_thinking = show_thinking
        self.console = console or Console()
        self.in_thinking = False
        self.thinking_buffer: list[str] = []
        self.response_buffer: list[str] = []
        self.thinking_displayed = False

    def process_chunk(self, chunk: str) -> Optional[str]:
        """Process a streaming chunk
        
        Args:
            chunk: Content chunk from stream
            
        Returns:
            Content to display (None if inside thinking block)
        """
        display_content, self.in_thinking, thinking_content = format_thinking_for_stream(
            chunk, self.in_thinking
        )

        if thinking_content:
            self.thinking_buffer.append(thinking_content)

        if display_content:
            self.response_buffer.append(display_content)

            # If we just exited thinking and haven't displayed it yet
            if not self.in_thinking and self.thinking_buffer and not self.thinking_displayed:
                if self.show_thinking:
                    full_thinking = "".join(self.thinking_buffer)
                    self.console.print(
                        Panel(
                            full_thinking,
                            title="[cyan]Thinking[/cyan]",
                            border_style="cyan",
                            expand=False,
                        )
                    )
                    self.console.print()
                self.thinking_displayed = True

            return display_content

        return None

    def get_thinking(self) -> Optional[str]:
        """Get accumulated thinking content"""
        if self.thinking_buffer:
            return "".join(self.thinking_buffer)
        return None

    def get_response(self) -> str:
        """Get accumulated response content"""
        return "".join(self.response_buffer)

    def get_result(self) -> ThinkingResult:
        """Get final parsed result"""
        return ThinkingResult(
            thinking=self.get_thinking(),
            response=self.get_response(),
            has_thinking=bool(self.thinking_buffer),
        )
