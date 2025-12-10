"""Web fetch tool for retrieving and analyzing web content"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Optional
from urllib.parse import urlparse

from .base import BaseTool, ToolParameter, ToolResult


class WebFetchTool(BaseTool):
    """Fetches content from a specified URL
    
    - Takes a URL and fetches the content
    - Converts HTML to plain text or markdown
    - Returns the content for analysis
    - Includes caching for faster responses
    """

    name = "webfetch"
    description = "Fetches content from a URL and converts HTML to readable text or markdown"
    parameters = [
        ToolParameter(
            name="url",
            type="string",
            description="The URL to fetch content from (must be a valid URL)",
        ),
        ToolParameter(
            name="format",
            type="string",
            description='The format to return the content in (text, markdown, or html)',
            required=False,
            default="text",
            enum=["text", "markdown", "html"],
        ),
        ToolParameter(
            name="timeout",
            type="integer",
            description="Optional timeout in seconds (max 120)",
            required=False,
            default=30,
        ),
        ToolParameter(
            name="max_length",
            type="integer",
            description="Maximum content length to return (default: 50000 characters)",
            required=False,
            default=50000,
        ),
    ]
    risk_level = "low"

    # Simple URL cache (in-memory)
    _cache: dict[str, tuple[str, float]] = {}
    _cache_ttl: float = 900  # 15 minutes

    def __init__(self, timeout: int = 30) -> None:
        self.default_timeout = timeout

    def _validate_url(self, url: str) -> tuple[bool, str]:
        """Validate URL and return (is_valid, normalized_url or error)"""
        try:
            # Auto-upgrade http to https
            if url.startswith("http://"):
                url = "https://" + url[7:]
            elif not url.startswith("https://"):
                url = "https://" + url

            parsed = urlparse(url)

            if not parsed.netloc:
                return False, "Invalid URL: no host specified"

            if parsed.scheme not in ("http", "https"):
                return False, f"Invalid URL scheme: {parsed.scheme}"

            return True, url

        except Exception as e:
            return False, f"Invalid URL: {e}"

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text"""
        # Remove script and style elements
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML comments
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

        # Replace block elements with newlines
        block_tags = ["p", "div", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"]
        for tag in block_tags:
            html = re.sub(rf"<{tag}[^>]*>", "\n", html, flags=re.IGNORECASE)
            html = re.sub(rf"</{tag}>", "\n", html, flags=re.IGNORECASE)

        # Remove all remaining HTML tags
        html = re.sub(r"<[^>]+>", "", html)

        # Decode common HTML entities
        entities = {
            "&nbsp;": " ",
            "&lt;": "<",
            "&gt;": ">",
            "&amp;": "&",
            "&quot;": '"',
            "&#39;": "'",
            "&apos;": "'",
        }
        for entity, char in entities.items():
            html = html.replace(entity, char)

        # Clean up whitespace
        lines = [line.strip() for line in html.split("\n")]
        lines = [line for line in lines if line]

        return "\n".join(lines)

    def _html_to_markdown(self, html: str) -> str:
        """Convert HTML to markdown"""
        # Remove script and style elements
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML comments
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

        # Convert headers
        for i in range(1, 7):
            html = re.sub(
                rf"<h{i}[^>]*>(.*?)</h{i}>",
                rf"\n{'#' * i} \1\n",
                html,
                flags=re.DOTALL | re.IGNORECASE,
            )

        # Convert links
        html = re.sub(
            r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
            r"[\2](\1)",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # Convert bold
        html = re.sub(r"<(b|strong)[^>]*>(.*?)</\1>", r"**\2**", html, flags=re.DOTALL | re.IGNORECASE)

        # Convert italic
        html = re.sub(r"<(i|em)[^>]*>(.*?)</\1>", r"*\2*", html, flags=re.DOTALL | re.IGNORECASE)

        # Convert code
        html = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", html, flags=re.DOTALL | re.IGNORECASE)

        # Convert pre/code blocks
        html = re.sub(
            r"<pre[^>]*><code[^>]*>(.*?)</code></pre>",
            r"\n```\n\1\n```\n",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # Convert list items
        html = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", html, flags=re.DOTALL | re.IGNORECASE)

        # Convert paragraphs
        html = re.sub(r"<p[^>]*>(.*?)</p>", r"\n\1\n", html, flags=re.DOTALL | re.IGNORECASE)

        # Convert line breaks
        html = re.sub(r"<br[^>]*>", "\n", html, flags=re.IGNORECASE)

        # Convert horizontal rules
        html = re.sub(r"<hr[^>]*>", "\n---\n", html, flags=re.IGNORECASE)

        # Remove all remaining HTML tags
        html = re.sub(r"<[^>]+>", "", html)

        # Decode common HTML entities
        entities = {
            "&nbsp;": " ",
            "&lt;": "<",
            "&gt;": ">",
            "&amp;": "&",
            "&quot;": '"',
            "&#39;": "'",
            "&apos;": "'",
        }
        for entity, char in entities.items():
            html = html.replace(entity, char)

        # Clean up whitespace
        html = re.sub(r"\n{3,}", "\n\n", html)
        lines = [line.rstrip() for line in html.split("\n")]

        return "\n".join(lines).strip()

    async def execute(
        self,
        url: str,
        format: str = "text",
        timeout: int = 30,
        max_length: int = 50000,
        **kwargs: Any,
    ) -> ToolResult:
        """Fetch content from URL"""
        # Validate URL
        is_valid, result = self._validate_url(url)
        if not is_valid:
            return ToolResult(
                success=False,
                output="",
                error=result,
            )

        url = result

        # Check cache
        import time

        cache_key = f"{url}:{format}"
        if cache_key in self._cache:
            content, cached_time = self._cache[cache_key]
            if time.time() - cached_time < self._cache_ttl:
                return ToolResult(
                    success=True,
                    output=content[:max_length],
                    metadata={"cached": True, "url": url},
                )

        # Enforce timeout limits
        timeout = min(timeout, 120)

        try:
            # Try using aiohttp if available
            try:
                import aiohttp

                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as session:
                    headers = {
                        "User-Agent": "MaxAgent/1.0 (CLI Code Assistant)",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    }
                    async with session.get(url, headers=headers, allow_redirects=True) as response:
                        if response.status != 200:
                            return ToolResult(
                                success=False,
                                output="",
                                error=f"HTTP {response.status}: {response.reason}",
                            )

                        html = await response.text()

            except ImportError:
                # Fallback to urllib
                import urllib.request

                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "MaxAgent/1.0 (CLI Code Assistant)",
                    },
                )

                loop = asyncio.get_event_loop()
                html = await loop.run_in_executor(
                    None,
                    lambda: urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"),
                )

            # Convert content based on format
            if format == "html":
                content = html
            elif format == "markdown":
                content = self._html_to_markdown(html)
            else:
                content = self._html_to_text(html)

            # Truncate if needed
            if len(content) > max_length:
                content = content[:max_length] + "\n\n... [Content truncated]"

            # Cache the result
            self._cache[cache_key] = (content, time.time())

            return ToolResult(
                success=True,
                output=content,
                metadata={
                    "url": url,
                    "format": format,
                    "length": len(content),
                    "cached": False,
                },
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error=f"Request timed out after {timeout} seconds",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to fetch URL: {e}",
            )
