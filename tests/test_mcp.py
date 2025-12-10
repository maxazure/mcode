"""Tests for MCP (Model Context Protocol) module"""

from __future__ import annotations

import json
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from maxagent.mcp.config import (
    MCPServerConfig,
    MCPConfig,
    get_mcp_config_path,
    load_mcp_config,
    save_mcp_config,
    add_mcp_server,
    remove_mcp_server,
    list_mcp_servers,
)
from maxagent.mcp.client import (
    MCPClient,
    MCPStdioClient,
    MCPClientBase,
    MCPToolDefinition,
    MCPToolResult,
    MCPError,
    create_mcp_client,
)


class TestMCPServerConfig:
    """Tests for MCPServerConfig"""

    def test_default_values(self):
        """Test default values"""
        config = MCPServerConfig(name="test", url="http://localhost:8080")
        assert config.name == "test"
        assert config.url == "http://localhost:8080"
        assert config.type == "http"
        assert config.headers == {}
        assert config.enabled is True
        assert config.env_vars == {}

    def test_with_headers(self):
        """Test with headers"""
        config = MCPServerConfig(
            name="test",
            url="http://localhost:8080",
            headers={"Authorization": "Bearer token123"},
        )
        assert config.headers == {"Authorization": "Bearer token123"}

    def test_get_resolved_headers_simple(self):
        """Test get_resolved_headers with simple value"""
        config = MCPServerConfig(
            name="test",
            url="http://localhost:8080",
            headers={"Authorization": "Bearer token123"},
        )
        resolved = config.get_resolved_headers()
        assert resolved == {"Authorization": "Bearer token123"}

    def test_get_resolved_headers_env_var(self):
        """Test get_resolved_headers with environment variable"""
        with patch.dict(os.environ, {"TEST_API_KEY": "secret123"}):
            config = MCPServerConfig(
                name="test",
                url="http://localhost:8080",
                headers={"Authorization": "Bearer ${TEST_API_KEY}"},
            )
            resolved = config.get_resolved_headers()
            assert resolved == {"Authorization": "Bearer secret123"}

    def test_get_resolved_headers_missing_env_var(self):
        """Test get_resolved_headers with missing environment variable"""
        config = MCPServerConfig(
            name="test",
            url="http://localhost:8080",
            headers={"Authorization": "Bearer ${NONEXISTENT_VAR}"},
        )
        resolved = config.get_resolved_headers()
        assert resolved == {"Authorization": "Bearer "}

    def test_get_resolved_url_simple(self):
        """Test get_resolved_url with simple URL"""
        config = MCPServerConfig(
            name="test",
            url="http://localhost:8080/api",
        )
        assert config.get_resolved_url() == "http://localhost:8080/api"

    def test_get_resolved_url_env_var(self):
        """Test get_resolved_url with environment variable"""
        with patch.dict(os.environ, {"API_HOST": "api.example.com"}):
            config = MCPServerConfig(
                name="test",
                url="https://${API_HOST}/mcp",
            )
            assert config.get_resolved_url() == "https://api.example.com/mcp"


class TestMCPConfig:
    """Tests for MCPConfig"""

    def test_default_values(self):
        """Test default values"""
        config = MCPConfig()
        assert config.servers == {}

    def test_with_servers(self):
        """Test with servers"""
        server = MCPServerConfig(name="test", url="http://localhost:8080")
        config = MCPConfig(servers={"test": server})
        assert "test" in config.servers
        assert config.servers["test"].url == "http://localhost:8080"


class TestMCPConfigIO:
    """Tests for MCP config I/O functions"""

    def test_load_mcp_config_no_file(self, tmp_path):
        """Test loading config when file doesn't exist"""
        with patch("maxagent.mcp.config.get_mcp_config_path", return_value=tmp_path / "mcp.json"):
            config = load_mcp_config()
            assert config.servers == {}

    def test_load_and_save_config(self, tmp_path):
        """Test saving and loading config"""
        config_path = tmp_path / "mcp_servers.json"

        with patch("maxagent.mcp.config.get_mcp_config_path", return_value=config_path):
            # Create and save config
            server = MCPServerConfig(
                name="test-server",
                url="http://localhost:8080",
                headers={"Authorization": "Bearer token"},
            )
            config = MCPConfig(servers={"test-server": server})
            save_mcp_config(config)

            # Load config
            loaded = load_mcp_config()
            assert "test-server" in loaded.servers
            assert loaded.servers["test-server"].url == "http://localhost:8080"
            assert loaded.servers["test-server"].headers == {"Authorization": "Bearer token"}

    def test_add_mcp_server(self, tmp_path):
        """Test add_mcp_server function"""
        config_path = tmp_path / "mcp_servers.json"

        with patch("maxagent.mcp.config.get_mcp_config_path", return_value=config_path):
            server = add_mcp_server(
                name="web-reader",
                url="https://api.example.com/mcp",
                headers={"Authorization": "Bearer token"},
            )

            assert server.name == "web-reader"
            assert server.url == "https://api.example.com/mcp"

            # Verify it was saved
            config = load_mcp_config()
            assert "web-reader" in config.servers

    def test_remove_mcp_server(self, tmp_path):
        """Test remove_mcp_server function"""
        config_path = tmp_path / "mcp_servers.json"

        with patch("maxagent.mcp.config.get_mcp_config_path", return_value=config_path):
            # Add server first
            add_mcp_server(name="test", url="http://localhost:8080")

            # Remove it
            result = remove_mcp_server("test")
            assert result is True

            # Verify it was removed
            config = load_mcp_config()
            assert "test" not in config.servers

    def test_remove_nonexistent_server(self, tmp_path):
        """Test removing nonexistent server"""
        config_path = tmp_path / "mcp_servers.json"

        with patch("maxagent.mcp.config.get_mcp_config_path", return_value=config_path):
            result = remove_mcp_server("nonexistent")
            assert result is False

    def test_list_mcp_servers(self, tmp_path):
        """Test list_mcp_servers function"""
        config_path = tmp_path / "mcp_servers.json"

        with patch("maxagent.mcp.config.get_mcp_config_path", return_value=config_path):
            # Add some servers
            add_mcp_server(name="server1", url="http://localhost:8080")
            add_mcp_server(name="server2", url="http://localhost:8081")

            servers = list_mcp_servers()
            assert len(servers) == 2
            assert "server1" in servers
            assert "server2" in servers


class TestMCPToolDefinition:
    """Tests for MCPToolDefinition"""

    def test_basic_definition(self):
        """Test basic tool definition"""
        tool = MCPToolDefinition(
            name="webReader",
            description="Fetch web content",
            input_schema={"type": "object", "properties": {"url": {"type": "string"}}},
            server_name="web-reader",
        )
        assert tool.name == "webReader"
        assert tool.description == "Fetch web content"
        assert tool.server_name == "web-reader"

    def test_to_openai_schema(self):
        """Test conversion to OpenAI schema"""
        tool = MCPToolDefinition(
            name="webReader",
            description="Fetch web content",
            input_schema={
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
            server_name="web-reader",
        )

        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "mcp_web-reader_webReader"
        assert "[MCP:web-reader]" in schema["function"]["description"]
        assert schema["function"]["parameters"]["type"] == "object"


class TestMCPToolResult:
    """Tests for MCPToolResult"""

    def test_text_content(self):
        """Test getting text content"""
        result = MCPToolResult(
            content=[
                {"type": "text", "text": "Hello"},
                {"type": "text", "text": "World"},
            ]
        )
        assert result.get_text() == "Hello\nWorld"

    def test_empty_content(self):
        """Test empty content"""
        result = MCPToolResult(content=[])
        assert result.get_text() == ""

    def test_error_result(self):
        """Test error result"""
        result = MCPToolResult(
            content=[{"type": "text", "text": "Error occurred"}],
            is_error=True,
        )
        assert result.is_error is True
        assert result.get_text() == "Error occurred"


class TestMCPClient:
    """Tests for MCPClient"""

    def test_init(self):
        """Test client initialization"""
        config = MCPServerConfig(name="test", url="http://localhost:8080")
        client = MCPClient(config)

        assert client.config == config
        assert client.session_id is None
        assert client._initialized is False

    def test_get_headers(self):
        """Test getting request headers"""
        config = MCPServerConfig(
            name="test",
            url="http://localhost:8080",
            headers={"Authorization": "Bearer token"},
        )
        client = MCPClient(config)

        headers = client._get_headers()
        assert "Content-Type" in headers
        assert "MCP-Protocol-Version" in headers
        assert headers["Authorization"] == "Bearer token"

    def test_get_headers_with_session(self):
        """Test getting headers with session ID"""
        config = MCPServerConfig(name="test", url="http://localhost:8080")
        client = MCPClient(config)
        client.session_id = "test-session-123"

        headers = client._get_headers()
        assert headers["Mcp-Session-Id"] == "test-session-123"

    @pytest.mark.asyncio
    async def test_initialize_already_initialized(self):
        """Test initialize when already initialized"""
        config = MCPServerConfig(name="test", url="http://localhost:8080")
        client = MCPClient(config)
        client._initialized = True

        result = await client.initialize()
        assert result == {}

    @pytest.mark.asyncio
    async def test_list_tools_not_initialized(self):
        """Test list_tools calls initialize if not initialized"""
        config = MCPServerConfig(name="test", url="http://localhost:8080")
        client = MCPClient(config)

        with patch.object(client, "initialize", new_callable=AsyncMock) as mock_init:
            with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = {"tools": []}

                await client.list_tools()
                mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_tool_not_initialized(self):
        """Test call_tool calls initialize if not initialized"""
        config = MCPServerConfig(name="test", url="http://localhost:8080")
        client = MCPClient(config)

        with patch.object(client, "initialize", new_callable=AsyncMock) as mock_init:
            with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = {"content": []}

                await client.call_tool("test", {"arg": "value"})
                mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager"""
        config = MCPServerConfig(name="test", url="http://localhost:8080")

        async with MCPClient(config) as client:
            assert isinstance(client, MCPClient)


class TestMCPError:
    """Tests for MCPError"""

    def test_error_message(self):
        """Test error message"""
        error = MCPError("Connection failed")
        assert str(error) == "Connection failed"


class TestMCPServerConfigStdio:
    """Tests for MCPServerConfig stdio transport"""

    def test_stdio_config(self):
        """Test stdio configuration"""
        config = MCPServerConfig(
            name="test-stdio",
            type="stdio",
            command="mcp-server",
            args=["--port", "8080"],
            env={"API_KEY": "secret"},
        )
        assert config.name == "test-stdio"
        assert config.type == "stdio"
        assert config.command == "mcp-server"
        assert config.args == ["--port", "8080"]
        assert config.env == {"API_KEY": "secret"}
        assert config.url is None

    def test_get_resolved_command_simple(self):
        """Test get_resolved_command with simple command"""
        config = MCPServerConfig(
            name="test",
            type="stdio",
            command="mcp-server",
        )
        assert config.get_resolved_command() == "mcp-server"

    def test_get_resolved_command_env_var(self):
        """Test get_resolved_command with environment variable"""
        with patch.dict(os.environ, {"MCP_CMD": "/usr/local/bin/mcp-server"}):
            config = MCPServerConfig(
                name="test",
                type="stdio",
                command="${MCP_CMD}",
            )
            assert config.get_resolved_command() == "/usr/local/bin/mcp-server"

    def test_get_resolved_command_none(self):
        """Test get_resolved_command when command is None"""
        config = MCPServerConfig(
            name="test",
            url="http://localhost:8080",
        )
        assert config.get_resolved_command() is None

    def test_get_resolved_env(self):
        """Test get_resolved_env"""
        with patch.dict(os.environ, {"BASE_URL": "http://localhost:8888"}):
            config = MCPServerConfig(
                name="test",
                type="stdio",
                command="mcp-server",
                env={"SEARXNG_URL": "${BASE_URL}/search"},
            )
            resolved = config.get_resolved_env()
            assert resolved["SEARXNG_URL"] == "http://localhost:8888/search"

    def test_get_resolved_env_inherits_os_env(self):
        """Test get_resolved_env inherits OS environment"""
        with patch.dict(os.environ, {"PATH": "/usr/bin", "HOME": "/home/user"}):
            config = MCPServerConfig(
                name="test",
                type="stdio",
                command="mcp-server",
                env={"MY_VAR": "value"},
            )
            resolved = config.get_resolved_env()
            assert resolved["MY_VAR"] == "value"
            assert resolved["PATH"] == "/usr/bin"
            assert resolved["HOME"] == "/home/user"


class TestMCPStdioClient:
    """Tests for MCPStdioClient"""

    def test_init(self):
        """Test client initialization"""
        config = MCPServerConfig(
            name="test",
            type="stdio",
            command="mcp-server",
        )
        client = MCPStdioClient(config)

        assert client.config == config
        assert client._initialized is False
        assert client._process is None

    @pytest.mark.asyncio
    async def test_start_process_no_command(self):
        """Test starting process without command raises error"""
        config = MCPServerConfig(
            name="test",
            url="http://localhost:8080",  # HTTP config, no command
        )
        client = MCPStdioClient(config)

        with pytest.raises(MCPError, match="No command specified"):
            await client._start_process()

    @pytest.mark.asyncio
    async def test_start_process_command_not_found(self):
        """Test starting process with nonexistent command"""
        config = MCPServerConfig(
            name="test",
            type="stdio",
            command="nonexistent-mcp-server-xyz123",
        )
        client = MCPStdioClient(config)

        with pytest.raises(MCPError, match="Command not found"):
            await client._start_process()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager"""
        config = MCPServerConfig(
            name="test",
            type="stdio",
            command="echo",
        )

        async with MCPStdioClient(config) as client:
            assert isinstance(client, MCPStdioClient)

    @pytest.mark.asyncio
    async def test_close_no_process(self):
        """Test close when no process is running"""
        config = MCPServerConfig(
            name="test",
            type="stdio",
            command="echo",
        )
        client = MCPStdioClient(config)

        # Should not raise
        await client.close()
        assert client._process is None


class TestCreateMCPClient:
    """Tests for create_mcp_client factory function"""

    def test_create_http_client(self):
        """Test creating HTTP client"""
        config = MCPServerConfig(
            name="test",
            type="http",
            url="http://localhost:8080",
        )
        client = create_mcp_client(config)
        assert isinstance(client, MCPClient)

    def test_create_stdio_client(self):
        """Test creating stdio client"""
        config = MCPServerConfig(
            name="test",
            type="stdio",
            command="mcp-server",
        )
        client = create_mcp_client(config)
        assert isinstance(client, MCPStdioClient)

    def test_default_is_http(self):
        """Test default transport type is HTTP"""
        config = MCPServerConfig(
            name="test",
            url="http://localhost:8080",
        )
        client = create_mcp_client(config)
        assert isinstance(client, MCPClient)


class TestAddMCPServerStdio:
    """Tests for add_mcp_server with stdio transport"""

    def test_add_stdio_server(self, tmp_path):
        """Test adding a stdio server"""
        config_path = tmp_path / "mcp_servers.json"

        with patch("maxagent.mcp.config.get_mcp_config_path", return_value=config_path):
            server = add_mcp_server(
                name="searxng",
                transport_type="stdio",
                command="mcp-searxng",
                args=["--verbose"],
                env={"SEARXNG_URL": "http://localhost:8888"},
            )

            assert server.name == "searxng"
            assert server.type == "stdio"
            assert server.command == "mcp-searxng"
            assert server.args == ["--verbose"]
            assert server.env == {"SEARXNG_URL": "http://localhost:8888"}

            # Verify it was saved
            config = load_mcp_config()
            assert "searxng" in config.servers
            saved_server = config.servers["searxng"]
            assert saved_server.command == "mcp-searxng"
            assert saved_server.env == {"SEARXNG_URL": "http://localhost:8888"}


class TestParseClaludeStyleArgs:
    """Tests for parse_claude_style_args function"""

    def test_parse_env_and_command(self):
        """Test parsing env vars and command"""
        from maxagent.cli.mcp_cmd import parse_claude_style_args

        args = ["env", "KEY1=VALUE1", "KEY2=VALUE2", "mcp-server"]
        env_vars, command, cmd_args = parse_claude_style_args(args)

        assert env_vars == {"KEY1": "VALUE1", "KEY2": "VALUE2"}
        assert command == "mcp-server"
        assert cmd_args == []

    def test_parse_env_command_and_args(self):
        """Test parsing env vars, command, and arguments"""
        from maxagent.cli.mcp_cmd import parse_claude_style_args

        args = ["env", "SEARXNG_URL=http://localhost:8888", "mcp-searxng", "--verbose"]
        env_vars, command, cmd_args = parse_claude_style_args(args)

        assert env_vars == {"SEARXNG_URL": "http://localhost:8888"}
        assert command == "mcp-searxng"
        assert cmd_args == ["--verbose"]

    def test_parse_command_only(self):
        """Test parsing command without env vars"""
        from maxagent.cli.mcp_cmd import parse_claude_style_args

        args = ["mcp-server", "--arg1", "--arg2"]
        env_vars, command, cmd_args = parse_claude_style_args(args)

        assert env_vars == {}
        assert command == "mcp-server"
        assert cmd_args == ["--arg1", "--arg2"]

    def test_parse_empty_args(self):
        """Test parsing empty arguments"""
        from maxagent.cli.mcp_cmd import parse_claude_style_args

        args = []
        env_vars, command, cmd_args = parse_claude_style_args(args)

        assert env_vars == {}
        assert command == ""
        assert cmd_args == []

    def test_parse_python_module_command(self):
        """Test parsing python -m style command"""
        from maxagent.cli.mcp_cmd import parse_claude_style_args

        args = ["env", "DEBUG=1", "python", "-m", "my_mcp_server", "--verbose"]
        env_vars, command, cmd_args = parse_claude_style_args(args)

        assert env_vars == {"DEBUG": "1"}
        assert command == "python"
        assert cmd_args == ["-m", "my_mcp_server", "--verbose"]

    def test_parse_multiple_env_vars(self):
        """Test parsing multiple environment variables"""
        from maxagent.cli.mcp_cmd import parse_claude_style_args

        args = ["env", "VAR1=a", "VAR2=b", "VAR3=c", "command"]
        env_vars, command, cmd_args = parse_claude_style_args(args)

        assert env_vars == {"VAR1": "a", "VAR2": "b", "VAR3": "c"}
        assert command == "command"
        assert cmd_args == []

    def test_parse_env_value_with_special_chars(self):
        """Test parsing env value with special characters"""
        from maxagent.cli.mcp_cmd import parse_claude_style_args

        args = ["env", "URL=http://localhost:8888/path?query=1", "server"]
        env_vars, command, cmd_args = parse_claude_style_args(args)

        assert env_vars == {"URL": "http://localhost:8888/path?query=1"}
        assert command == "server"


class TestPreprocessArgv:
    """Tests for preprocess_argv function"""

    def test_preprocess_with_separator(self):
        """Test preprocessing argv with -- separator"""
        import sys
        from maxagent.cli import mcp_cmd

        original_argv = sys.argv.copy()
        try:
            sys.argv = [
                "llc",
                "mcp",
                "add",
                "test",
                "--transport",
                "stdio",
                "--",
                "env",
                "KEY=VALUE",
                "cmd",
            ]
            mcp_cmd.preprocess_argv()

            # Check sys.argv was modified
            assert "--" not in sys.argv
            assert "env" not in sys.argv
            assert sys.argv == ["llc", "mcp", "add", "test", "--transport", "stdio"]

            # Check extra args were captured
            assert mcp_cmd._claude_extra_args == ["env", "KEY=VALUE", "cmd"]
        finally:
            sys.argv = original_argv
            mcp_cmd._claude_extra_args = []

    def test_preprocess_without_separator(self):
        """Test preprocessing argv without -- separator"""
        import sys
        from maxagent.cli import mcp_cmd

        original_argv = sys.argv.copy()
        try:
            sys.argv = ["llc", "mcp", "add", "test", "--command", "cmd"]
            mcp_cmd.preprocess_argv()

            # Check sys.argv was not modified
            assert sys.argv == ["llc", "mcp", "add", "test", "--command", "cmd"]

            # Check extra args are empty
            assert mcp_cmd._claude_extra_args == []
        finally:
            sys.argv = original_argv
            mcp_cmd._claude_extra_args = []


class TestGetProjectMCPConfigPath:
    """Tests for get_project_mcp_config_path function"""

    def test_returns_path_in_cwd(self, tmp_path, monkeypatch):
        """Test that it returns path in current working directory"""
        from maxagent.cli.mcp_cmd import get_project_mcp_config_path

        monkeypatch.chdir(tmp_path)
        path = get_project_mcp_config_path()

        assert path == tmp_path / ".maxagent" / "mcp_servers.json"


class TestTestAllServers:
    """Tests for _test_all_servers function"""

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_enabled_servers(self):
        """Test that empty dict is returned when no servers are enabled"""
        from maxagent.cli.mcp_cmd import _test_all_servers

        servers = {
            "test1": MCPServerConfig(name="test1", url="http://localhost:8080", enabled=False),
            "test2": MCPServerConfig(name="test2", url="http://localhost:8081", enabled=False),
        }

        results = await _test_all_servers(servers)
        assert results == {}

    @pytest.mark.asyncio
    async def test_returns_failure_for_invalid_server(self):
        """Test that failure is returned for server that can't connect"""
        from maxagent.cli.mcp_cmd import _test_all_servers

        servers = {
            "test": MCPServerConfig(
                name="test",
                type="stdio",
                command="nonexistent-command-xyz",
                enabled=True,
            ),
        }

        results = await _test_all_servers(servers)
        assert "test" in results
        ok, msg, tool_count = results["test"]
        assert ok is False
        assert tool_count == 0
        assert "not found" in msg.lower() or "command" in msg.lower()

    @pytest.mark.asyncio
    async def test_success_with_mock_client(self):
        """Test success case with mocked client"""
        from maxagent.cli.mcp_cmd import _test_all_servers
        from maxagent.mcp.client import MCPToolDefinition

        servers = {
            "test": MCPServerConfig(
                name="test",
                type="stdio",
                command="echo",
                enabled=True,
            ),
        }

        mock_tools = [
            MCPToolDefinition(name="tool1", description="Test tool 1", input_schema={}),
            MCPToolDefinition(name="tool2", description="Test tool 2", input_schema={}),
        ]

        with patch("maxagent.cli.mcp_cmd.create_mcp_client") as mock_create:
            mock_client = AsyncMock()
            mock_client.initialize = AsyncMock(return_value=None)
            mock_client.list_tools = AsyncMock(return_value=mock_tools)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_create.return_value = mock_client

            results = await _test_all_servers(servers)

            assert "test" in results
            ok, msg, tool_count = results["test"]
            assert ok is True
            assert tool_count == 2
            assert msg == ""
