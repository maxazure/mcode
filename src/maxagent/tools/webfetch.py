"""Web fetch tool for retrieving and analyzing web content"""

from __future__ import annotations

import asyncio
import os
import re
from html import unescape
from typing import Any, Optional
from urllib.parse import urlparse

from .base import BaseTool, ToolParameter, ToolResult


class WebFetchTool(BaseTool):
    """Fetches content from a specified URL

    - Takes a URL and fetches the content
    - Converts HTML to plain text or markdown
    - Returns the content for analysis
    - Includes caching for faster responses
    - Supports proxy via HTTP_PROXY/HTTPS_PROXY environment variables
    - Uses BeautifulSoup for better HTML parsing when available
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
            description="The format to return the content in (text, markdown, or html)",
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
        ToolParameter(
            name="extract_main",
            type="boolean",
            description="Try to extract main content area only (removes nav, sidebar, footer, etc.)",
            required=False,
            default=False,
        ),
        ToolParameter(
            name="include_links",
            type="boolean",
            description="Include link URLs in text output (default: True for markdown)",
            required=False,
            default=True,
        ),
    ]
    risk_level = "low"

    # Simple URL cache (in-memory)
    _cache: dict[str, tuple[str, float]] = {}
    _cache_ttl: float = 900  # 15 minutes

    # Check if beautifulsoup is available
    _bs4_available: Optional[bool] = None

    def __init__(self, timeout: int = 30) -> None:
        self.default_timeout = timeout

    @classmethod
    def _check_bs4(cls) -> bool:
        """Check if BeautifulSoup is available"""
        if cls._bs4_available is None:
            try:
                from bs4 import BeautifulSoup  # noqa: F401

                cls._bs4_available = True
            except ImportError:
                cls._bs4_available = False
        return cls._bs4_available

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

    def _decode_entities(self, text: str) -> str:
        """Decode HTML entities"""
        # First use html.unescape for standard entities
        text = unescape(text)
        # Handle any remaining numeric entities
        text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
        text = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)
        return text

    def _html_to_text_regex(self, html: str, include_links: bool = False) -> str:
        """Convert HTML to plain text using regex (fallback)"""
        # Remove script and style elements
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<noscript[^>]*>.*?</noscript>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML comments
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

        # Extract links if requested
        if include_links:
            html = re.sub(
                r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                r"\2 (\1)",
                html,
                flags=re.DOTALL | re.IGNORECASE,
            )

        # Replace block elements with newlines
        block_tags = [
            "p",
            "div",
            "br",
            "hr",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "tr",
            "td",
            "th",
            "article",
            "section",
            "header",
            "footer",
            "nav",
            "aside",
        ]
        for tag in block_tags:
            html = re.sub(rf"<{tag}[^>]*>", "\n", html, flags=re.IGNORECASE)
            html = re.sub(rf"</{tag}>", "\n", html, flags=re.IGNORECASE)

        # Remove all remaining HTML tags
        html = re.sub(r"<[^>]+>", "", html)

        # Decode HTML entities
        html = self._decode_entities(html)

        # Clean up whitespace
        lines = [line.strip() for line in html.split("\n")]
        lines = [line for line in lines if line]

        # Remove duplicate consecutive lines
        result = []
        prev_line = ""
        for line in lines:
            if line != prev_line:
                result.append(line)
                prev_line = line

        return "\n".join(result)

    def _html_to_text_bs4(
        self, html: str, include_links: bool = False, extract_main: bool = False
    ) -> str:
        """Convert HTML to plain text using BeautifulSoup"""
        from bs4 import BeautifulSoup, NavigableString

        soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted elements
        for tag in soup.find_all(["script", "style", "noscript", "iframe", "svg", "canvas"]):
            tag.decompose()

        # Remove comments
        for comment in soup.find_all(
            string=lambda text: isinstance(text, NavigableString) and text.parent.name is None
        ):
            pass  # BeautifulSoup handles this

        # Try to extract main content if requested
        if extract_main:
            # Look for common main content containers
            main_selectors = [
                "main",
                "article",
                "[role='main']",
                "#content",
                "#main-content",
                ".main-content",
                ".post-content",
                ".article-content",
                ".entry-content",
            ]
            main_content = None
            for selector in main_selectors:
                main_content = soup.select_one(selector)
                if main_content:
                    soup = BeautifulSoup(str(main_content), "html.parser")
                    break

            # Remove navigation, sidebars, footers from remaining content
            for tag in soup.find_all(["nav", "aside", "footer", "header"]):
                tag.decompose()
            for tag in soup.find_all(
                class_=re.compile(r"(nav|sidebar|footer|header|menu|ad|banner)", re.I)
            ):
                tag.decompose()
            for tag in soup.find_all(
                id=re.compile(r"(nav|sidebar|footer|header|menu|ad|banner)", re.I)
            ):
                tag.decompose()

        # Extract text
        if include_links:
            # Process links to include URLs
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True)
                if text and href and not href.startswith("#"):
                    link.replace_with(f"{text} ({href})")

        text = soup.get_text(separator="\n", strip=True)

        # Clean up whitespace
        lines = [line.strip() for line in text.split("\n")]
        lines = [line for line in lines if line]

        # Remove duplicate consecutive lines
        result = []
        prev_line = ""
        for line in lines:
            if line != prev_line:
                result.append(line)
                prev_line = line

        return "\n".join(result)

    def _html_to_markdown_regex(self, html: str) -> str:
        """Convert HTML to markdown using regex (fallback)"""
        # Remove script and style elements
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<noscript[^>]*>.*?</noscript>", "", html, flags=re.DOTALL | re.IGNORECASE)

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

        # Convert images
        html = re.sub(
            r'<img[^>]*src=["\']([^"\']+)["\'][^>]*alt=["\']([^"\']*)["\'][^>]*>',
            r"![\2](\1)",
            html,
            flags=re.IGNORECASE,
        )
        html = re.sub(
            r'<img[^>]*alt=["\']([^"\']*)["\'][^>]*src=["\']([^"\']+)["\'][^>]*>',
            r"![\1](\2)",
            html,
            flags=re.IGNORECASE,
        )

        # Convert bold
        html = re.sub(
            r"<(b|strong)[^>]*>(.*?)</\1>", r"**\2**", html, flags=re.DOTALL | re.IGNORECASE
        )

        # Convert italic
        html = re.sub(r"<(i|em)[^>]*>(.*?)</\1>", r"*\2*", html, flags=re.DOTALL | re.IGNORECASE)

        # Convert inline code
        html = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", html, flags=re.DOTALL | re.IGNORECASE)

        # Convert pre/code blocks
        html = re.sub(
            r"<pre[^>]*><code[^>]*>(.*?)</code></pre>",
            r"\n```\n\1\n```\n",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        html = re.sub(
            r"<pre[^>]*>(.*?)</pre>",
            r"\n```\n\1\n```\n",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # Convert blockquotes
        html = re.sub(
            r"<blockquote[^>]*>(.*?)</blockquote>",
            lambda m: "\n" + "\n".join("> " + line for line in m.group(1).split("\n")) + "\n",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # Convert unordered list items
        html = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", html, flags=re.DOTALL | re.IGNORECASE)

        # Convert paragraphs
        html = re.sub(r"<p[^>]*>(.*?)</p>", r"\n\1\n", html, flags=re.DOTALL | re.IGNORECASE)

        # Convert line breaks
        html = re.sub(r"<br[^>]*>", "\n", html, flags=re.IGNORECASE)

        # Convert horizontal rules
        html = re.sub(r"<hr[^>]*>", "\n---\n", html, flags=re.IGNORECASE)

        # Remove all remaining HTML tags
        html = re.sub(r"<[^>]+>", "", html)

        # Decode HTML entities
        html = self._decode_entities(html)

        # Clean up whitespace
        html = re.sub(r"\n{3,}", "\n\n", html)
        lines = [line.rstrip() for line in html.split("\n")]

        return "\n".join(lines).strip()

    def _html_to_markdown_bs4(self, html: str, extract_main: bool = False) -> str:
        """Convert HTML to markdown using BeautifulSoup"""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted elements
        for tag in soup.find_all(["script", "style", "noscript", "iframe", "svg", "canvas"]):
            tag.decompose()

        # Try to extract main content if requested
        if extract_main:
            main_selectors = [
                "main",
                "article",
                "[role='main']",
                "#content",
                "#main-content",
                ".main-content",
                ".post-content",
                ".article-content",
                ".entry-content",
            ]
            for selector in main_selectors:
                main_content = soup.select_one(selector)
                if main_content:
                    soup = BeautifulSoup(str(main_content), "html.parser")
                    break

            # Remove navigation, sidebars, footers
            for tag in soup.find_all(["nav", "aside", "footer"]):
                tag.decompose()
            for tag in soup.find_all(
                class_=re.compile(r"(nav|sidebar|footer|menu|ad|banner)", re.I)
            ):
                tag.decompose()

        # Convert to markdown
        result = []

        def process_element(element, depth=0):
            if isinstance(element, str):
                text = element.strip()
                if text:
                    result.append(text)
                return

            tag_name = element.name if hasattr(element, "name") else None

            if tag_name is None:
                for child in element:
                    process_element(child, depth)
                return

            # Headers
            if tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                level = int(tag_name[1])
                text = element.get_text(strip=True)
                if text:
                    result.append(f"\n{'#' * level} {text}\n")
                return

            # Links
            if tag_name == "a":
                href = element.get("href", "")
                text = element.get_text(strip=True)
                if text and href:
                    result.append(f"[{text}]({href})")
                elif text:
                    result.append(text)
                return

            # Images
            if tag_name == "img":
                src = element.get("src", "")
                alt = element.get("alt", "")
                if src:
                    result.append(f"![{alt}]({src})")
                return

            # Bold
            if tag_name in ["strong", "b"]:
                text = element.get_text(strip=True)
                if text:
                    result.append(f"**{text}**")
                return

            # Italic
            if tag_name in ["em", "i"]:
                text = element.get_text(strip=True)
                if text:
                    result.append(f"*{text}*")
                return

            # Code
            if tag_name == "code":
                text = element.get_text(strip=True)
                if text:
                    # Check if inside pre
                    if element.parent and element.parent.name == "pre":
                        result.append(f"\n```\n{text}\n```\n")
                    else:
                        result.append(f"`{text}`")
                return

            # Pre (without code)
            if tag_name == "pre":
                # Check if contains code tag
                code = element.find("code")
                if not code:
                    text = element.get_text(strip=True)
                    if text:
                        result.append(f"\n```\n{text}\n```\n")
                    return
                # Otherwise process children
                for child in element.children:
                    process_element(child, depth)
                return

            # Blockquote
            if tag_name == "blockquote":
                text = element.get_text(strip=True)
                if text:
                    quoted = "\n".join(f"> {line}" for line in text.split("\n"))
                    result.append(f"\n{quoted}\n")
                return

            # List items
            if tag_name == "li":
                text = element.get_text(strip=True)
                if text:
                    result.append(f"- {text}\n")
                return

            # Paragraphs
            if tag_name == "p":
                text = element.get_text(strip=True)
                if text:
                    result.append(f"\n{text}\n")
                return

            # Line breaks
            if tag_name == "br":
                result.append("\n")
                return

            # Horizontal rules
            if tag_name == "hr":
                result.append("\n---\n")
                return

            # Process children for other elements
            for child in element.children:
                process_element(child, depth)

        process_element(soup)

        # Join and clean up
        text = "".join(result)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _html_to_text(
        self, html: str, include_links: bool = False, extract_main: bool = False
    ) -> str:
        """Convert HTML to plain text"""
        if self._check_bs4():
            return self._html_to_text_bs4(html, include_links, extract_main)
        return self._html_to_text_regex(html, include_links)

    def _html_to_markdown(self, html: str, extract_main: bool = False) -> str:
        """Convert HTML to markdown"""
        if self._check_bs4():
            return self._html_to_markdown_bs4(html, extract_main)
        return self._html_to_markdown_regex(html)

    def _get_proxy_config(self) -> Optional[dict]:
        """Get proxy configuration from environment variables"""
        http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")

        if http_proxy or https_proxy:
            return {
                "http://": http_proxy,
                "https://": https_proxy or http_proxy,
            }
        return None

    async def execute(
        self,
        url: str,
        format: str = "text",
        timeout: int = 30,
        max_length: int = 50000,
        extract_main: bool = False,
        include_links: bool = True,
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

        cache_key = f"{url}:{format}:{extract_main}:{include_links}"
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
            import httpx

            # Build client configuration
            client_kwargs = {
                "timeout": httpx.Timeout(timeout),
                "follow_redirects": True,
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
                    "Accept-Encoding": "gzip, deflate",
                },
            }

            # Add proxy if configured
            proxy = self._get_proxy_config()
            if proxy:
                client_kwargs["proxies"] = proxy

            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.get(url)

                if response.status_code >= 400:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"HTTP {response.status_code}: {response.reason_phrase}",
                    )

                # Handle redirects to different hosts (inform user)
                if response.history:
                    final_url = str(response.url)
                    original_host = urlparse(url).netloc
                    final_host = urlparse(final_url).netloc
                    if original_host != final_host:
                        # Different host redirect
                        return ToolResult(
                            success=True,
                            output=f"Redirected to different host: {final_url}",
                            metadata={
                                "redirect": True,
                                "original_url": url,
                                "final_url": final_url,
                            },
                        )

                # Try to detect encoding
                html = response.text

            # Convert content based on format
            if format == "html":
                content = html
            elif format == "markdown":
                content = self._html_to_markdown(html, extract_main)
            else:
                content = self._html_to_text(html, include_links, extract_main)

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
                    "used_bs4": self._check_bs4(),
                    "extracted_main": extract_main,
                },
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error=f"Request timed out after {timeout} seconds",
            )
        except httpx.ConnectError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Connection error: {e}",
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"HTTP error: {e}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to fetch URL: {e}",
            )

    @classmethod
    def clear_cache(cls) -> int:
        """Clear the URL cache and return number of cleared entries"""
        count = len(cls._cache)
        cls._cache.clear()
        return count
