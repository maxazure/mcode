"""MCP Client implementations for HTTP and Stdio transports"""

from __future__ import annotations

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

import httpx

from maxagent.mcp.config import MCPServerConfig


@dataclass
class MCPToolDefinition:
    """Definition of an MCP tool"""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: Optional[dict[str, Any]] = None
    title: Optional[str] = None
    server_name: str = ""

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function schema format"""
        return {
            "type": "function",
            "function": {
                "name": f"mcp_{self.server_name}_{self.name}",
                "description": f"[MCP:{self.server_name}] {self.description}",
                "parameters": self.input_schema,
            },
        }


@dataclass
class MCPToolResult:
    """Result from an MCP tool call"""

    content: list[dict[str, Any]]
    is_error: bool = False
    structured_content: Optional[dict[str, Any]] = None

    def get_text(self) -> str:
        """Get text content from result"""
        texts = []
        for item in self.content:
            if item.get("type") == "text":
                texts.append(item.get("text", ""))
        return "\n".join(texts)


class MCPClientBase(ABC):
    """Abstract base class for MCP clients"""

    MCP_PROTOCOL_VERSION = "2025-06-18"

    def __init__(self, config: MCPServerConfig):
        """Initialize MCP client

        Args:
            config: Server configuration
        """
        self.config = config
        self._initialized = False
        self._tools: list[MCPToolDefinition] = []

    @abstractmethod
    async def _send_request(
        self, method: str, params: Optional[dict[str, Any]] = None, is_notification: bool = False
    ) -> Optional[dict[str, Any]]:
        """Send a JSON-RPC request to the MCP server"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the MCP connection"""
        pass

    async def initialize(self) -> dict[str, Any]:
        """Initialize the MCP connection

        Returns:
            Server capabilities
        """
        if self._initialized:
            return {}

        params = {
            "protocolVersion": self.MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {},  # We support calling tools
            },
            "clientInfo": {
                "name": "MaxAgent",
                "version": "0.1.0",
            },
        }

        result = await self._send_request("initialize", params)
        self._initialized = True

        # Send initialized notification
        await self._send_request("notifications/initialized", is_notification=True)

        return result or {}

    async def list_tools(self) -> list[MCPToolDefinition]:
        """List available tools from the MCP server

        Returns:
            List of tool definitions
        """
        if not self._initialized:
            await self.initialize()

        result = await self._send_request("tools/list")

        tools = []
        if result and "tools" in result:
            for tool_data in result["tools"]:
                tool = MCPToolDefinition(
                    name=tool_data.get("name", ""),
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("inputSchema", {}),
                    output_schema=tool_data.get("outputSchema"),
                    title=tool_data.get("title"),
                    server_name=self.config.name,
                )
                tools.append(tool)

        self._tools = tools
        return tools

    async def call_tool(
        self, name: str, arguments: Optional[dict[str, Any]] = None
    ) -> MCPToolResult:
        """Call an MCP tool

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result
        """
        if not self._initialized:
            await self.initialize()

        params: dict[str, Any] = {
            "name": name,
        }
        if arguments:
            params["arguments"] = arguments

        result = await self._send_request("tools/call", params)

        if result:
            return MCPToolResult(
                content=result.get("content", []),
                is_error=result.get("isError", False),
                structured_content=result.get("structuredContent"),
            )
        else:
            return MCPToolResult(content=[], is_error=True)

    async def __aenter__(self) -> "MCPClientBase":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


class MCPClient(MCPClientBase):
    """MCP HTTP Client for Streamable HTTP transport"""

    def __init__(self, config: MCPServerConfig):
        """Initialize MCP client

        Args:
            config: Server configuration
        """
        super().__init__(config)
        self.session_id: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for requests"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self.MCP_PROTOCOL_VERSION,
        }
        # Add resolved headers from config
        headers.update(self.config.get_resolved_headers())
        # Add session ID if available
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    async def _send_request(
        self, method: str, params: Optional[dict[str, Any]] = None, is_notification: bool = False
    ) -> Optional[dict[str, Any]]:
        """Send a JSON-RPC request to the MCP server

        Args:
            method: JSON-RPC method name
            params: Method parameters
            is_notification: If True, don't expect a response

        Returns:
            Response result or None for notifications
        """
        client = await self._get_client()
        url = self.config.get_resolved_url()

        request_id = str(uuid.uuid4()) if not is_notification else None

        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params:
            payload["params"] = params
        if request_id:
            payload["id"] = request_id

        headers = self._get_headers()

        try:
            response = await client.post(url, json=payload, headers=headers)

            # Handle session ID from response
            if "Mcp-Session-Id" in response.headers:
                self.session_id = response.headers["Mcp-Session-Id"]

            # Notification response
            if is_notification:
                if response.status_code == 202:
                    return None
                elif response.status_code >= 400:
                    raise MCPError(f"Notification failed: {response.status_code}")
                return None

            # Handle response content type
            content_type = response.headers.get("Content-Type", "")

            if "text/event-stream" in content_type:
                # SSE response - parse events
                return await self._handle_sse_response(response, request_id)
            elif "application/json" in content_type:
                # JSON response
                data = response.json()
                if "error" in data:
                    raise MCPError(f"JSON-RPC error: {data['error']}")
                return data.get("result")
            else:
                raise MCPError(f"Unexpected content type: {content_type}")

        except httpx.HTTPError as e:
            raise MCPError(f"HTTP error: {e}")

    async def _handle_sse_response(
        self, response: httpx.Response, request_id: Optional[str]
    ) -> Optional[dict[str, Any]]:
        """Handle Server-Sent Events response

        Args:
            response: HTTP response with SSE content
            request_id: Expected request ID for the response

        Returns:
            The JSON-RPC result
        """
        result = None
        current_event = ""
        current_data = ""
        current_id = ""

        async for line in response.aiter_lines():
            line = line.strip()
            if not line:
                # Empty line means end of event
                if current_data and current_event == "message":
                    try:
                        data = json.loads(current_data)
                        # Check if this is our response (match by id field in data)
                        data_id = data.get("id")
                        if data_id == request_id or str(data_id) == str(request_id):
                            if "error" in data:
                                raise MCPError(f"JSON-RPC error: {data['error']}")
                            result = data.get("result")
                    except json.JSONDecodeError:
                        pass
                current_event = ""
                current_data = ""
                current_id = ""
            elif line.startswith("id:"):
                current_id = line[3:].strip()
            elif line.startswith("event:"):
                current_event = line[6:].strip()
            elif line.startswith("data:"):
                current_data = line[5:].strip()

        # Handle case where there's no trailing empty line
        if current_data and current_event == "message":
            try:
                data = json.loads(current_data)
                data_id = data.get("id")
                if data_id == request_id or str(data_id) == str(request_id):
                    if "error" in data:
                        raise MCPError(f"JSON-RPC error: {data['error']}")
                    result = data.get("result")
            except json.JSONDecodeError:
                pass

        return result

    async def close(self) -> None:
        """Close the MCP connection"""
        if self._client:
            # Try to terminate session
            if self.session_id:
                try:
                    await self._client.delete(
                        self.config.get_resolved_url(),
                        headers=self._get_headers(),
                    )
                except Exception:
                    pass

            await self._client.aclose()
            self._client = None

        self._initialized = False
        self.session_id = None

    async def __aenter__(self) -> "MCPClient":
        return self


class MCPStdioClient(MCPClientBase):
    """MCP Stdio Client for subprocess-based transport

    This client communicates with MCP servers via stdin/stdout using JSON-RPC.
    """

    def __init__(self, config: MCPServerConfig):
        """Initialize MCP Stdio client

        Args:
            config: Server configuration with command and args
        """
        super().__init__(config)
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._pending_requests: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: Optional[asyncio.Task[None]] = None
        self._lock = asyncio.Lock()

    async def _start_process(self) -> None:
        """Start the MCP server subprocess"""
        if self._process is not None:
            return

        command = self.config.get_resolved_command()
        if not command:
            raise MCPError("No command specified for stdio transport")

        # Build command with args
        cmd_parts = [command] + self.config.args

        # Get environment with substitution
        env = self.config.get_resolved_env()

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError:
            raise MCPError(f"Command not found: {command}")
        except Exception as e:
            raise MCPError(f"Failed to start process: {e}")

        # Start reader task
        self._reader_task = asyncio.create_task(self._read_responses())

    async def _read_responses(self) -> None:
        """Read responses from stdout"""
        if self._process is None or self._process.stdout is None:
            return

        buffer = ""
        while True:
            try:
                # Read line by line
                line = await self._process.stdout.readline()
                if not line:
                    # Process ended
                    break

                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue

                try:
                    data = json.loads(line_str)

                    # Handle response
                    request_id = data.get("id")
                    if request_id is not None:
                        request_id_str = str(request_id)
                        if request_id_str in self._pending_requests:
                            future = self._pending_requests.pop(request_id_str)
                            if "error" in data:
                                future.set_exception(MCPError(f"JSON-RPC error: {data['error']}"))
                            else:
                                future.set_result(data.get("result", {}))

                except json.JSONDecodeError:
                    # Skip invalid JSON
                    continue

            except asyncio.CancelledError:
                break
            except Exception:
                break

    async def _send_request(
        self, method: str, params: Optional[dict[str, Any]] = None, is_notification: bool = False
    ) -> Optional[dict[str, Any]]:
        """Send a JSON-RPC request to the MCP server via stdin

        Args:
            method: JSON-RPC method name
            params: Method parameters
            is_notification: If True, don't expect a response

        Returns:
            Response result or None for notifications
        """
        async with self._lock:
            await self._start_process()

        if self._process is None or self._process.stdin is None:
            raise MCPError("Process not started")

        # Generate request ID
        self._request_id += 1
        request_id = str(self._request_id) if not is_notification else None

        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params:
            payload["params"] = params
        if request_id:
            payload["id"] = request_id

        # Create future for response
        future: Optional[asyncio.Future[dict[str, Any]]] = None
        if request_id and not is_notification:
            future = asyncio.Future()
            self._pending_requests[request_id] = future

        # Send request
        try:
            request_line = json.dumps(payload) + "\n"
            self._process.stdin.write(request_line.encode("utf-8"))
            await self._process.stdin.drain()
        except Exception as e:
            if request_id and request_id in self._pending_requests:
                del self._pending_requests[request_id]
            raise MCPError(f"Failed to send request: {e}")

        # Wait for response
        if is_notification or future is None:
            return None

        try:
            result = await asyncio.wait_for(future, timeout=60.0)
            return result
        except asyncio.TimeoutError:
            if request_id and request_id in self._pending_requests:
                del self._pending_requests[request_id]
            raise MCPError("Request timed out")

    async def close(self) -> None:
        """Close the MCP connection and terminate the subprocess"""
        # Cancel reader task
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        # Terminate process
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            except Exception:
                pass
            self._process = None

        # Clear pending requests
        for future in self._pending_requests.values():
            future.cancel()
        self._pending_requests.clear()

        self._initialized = False

    async def __aenter__(self) -> "MCPStdioClient":
        return self


def create_mcp_client(config: MCPServerConfig) -> MCPClientBase:
    """Create an MCP client based on the transport type

    Args:
        config: Server configuration

    Returns:
        Appropriate MCP client instance
    """
    if config.type == "stdio":
        return MCPStdioClient(config)
    else:
        return MCPClient(config)


class MCPError(Exception):
    """MCP protocol error"""

    pass
