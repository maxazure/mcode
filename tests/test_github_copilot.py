"""Tests for GitHub Copilot authentication"""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maxagent.auth.github_copilot import (
    GitHubCopilotAuth,
    CopilotToken,
    CopilotSession,
    DeviceCodeResponse,
    GITHUB_CLIENT_ID,
)


class TestCopilotToken:
    """Tests for CopilotToken class"""

    def test_token_not_expired(self):
        """Test token that is not expired"""
        future_time = int(time.time()) + 3600  # 1 hour from now
        token = CopilotToken(token="test_token", expires_at=future_time)
        assert not token.is_expired

    def test_token_expired(self):
        """Test token that is expired"""
        past_time = int(time.time()) - 3600  # 1 hour ago
        token = CopilotToken(token="test_token", expires_at=past_time)
        assert token.is_expired

    def test_token_expires_soon(self):
        """Test token that expires within 5 minute buffer"""
        almost_expired = int(time.time()) + 200  # 3.3 minutes from now
        token = CopilotToken(token="test_token", expires_at=almost_expired)
        assert token.is_expired  # Should be considered expired due to buffer

    def test_to_dict(self):
        """Test conversion to dictionary"""
        token = CopilotToken(
            token="test_token",
            expires_at=12345,
            refresh_token="refresh",
            github_token="github",
        )
        data = token.to_dict()
        assert data["token"] == "test_token"
        assert data["expires_at"] == 12345
        assert data["refresh_token"] == "refresh"
        assert data["github_token"] == "github"

    def test_from_dict(self):
        """Test creation from dictionary"""
        data = {
            "token": "test_token",
            "expires_at": 12345,
            "refresh_token": "refresh",
            "github_token": "github",
        }
        token = CopilotToken.from_dict(data)
        assert token.token == "test_token"
        assert token.expires_at == 12345
        assert token.refresh_token == "refresh"
        assert token.github_token == "github"


class TestCopilotSession:
    """Tests for CopilotSession class"""

    def test_first_message_returns_user(self):
        """First message should return 'user' initiator"""
        session = CopilotSession()
        assert session.get_initiator() == "user"

    def test_subsequent_messages_return_agent(self):
        """Subsequent messages should return 'agent' initiator"""
        session = CopilotSession()
        session.get_initiator()  # First message
        assert session.get_initiator() == "agent"
        assert session.get_initiator() == "agent"

    def test_reset_session(self):
        """Reset should allow 'user' initiator again"""
        session = CopilotSession()
        session.get_initiator()  # First message
        session.get_initiator()  # Second message
        session.reset()
        assert session.get_initiator() == "user"

    def test_message_count(self):
        """Test message count tracking"""
        session = CopilotSession()
        assert session.message_count == 0
        session.get_initiator()
        assert session.message_count == 1
        session.get_initiator()
        assert session.message_count == 2


class TestGitHubCopilotAuth:
    """Tests for GitHubCopilotAuth class"""

    def test_init_default_paths(self):
        """Test default token directory"""
        auth = GitHubCopilotAuth()
        assert auth.token_dir == Path.home() / ".mcode" / "copilot"

    def test_init_custom_path(self):
        """Test custom token directory"""
        custom_path = Path("/custom/path")
        auth = GitHubCopilotAuth(token_dir=custom_path)
        assert auth.token_dir == custom_path

    def test_save_and_load_token(self):
        """Test token persistence"""
        with tempfile.TemporaryDirectory() as tmpdir:
            auth = GitHubCopilotAuth(token_dir=Path(tmpdir))

            token = CopilotToken(
                token="test_token",
                expires_at=int(time.time()) + 3600,
                github_token="github_token",
            )
            auth.save_token(token)

            # Create new instance to test loading
            auth2 = GitHubCopilotAuth(token_dir=Path(tmpdir))
            loaded = auth2.load_token()

            assert loaded is not None
            assert loaded.token == "test_token"

    def test_clear_token(self):
        """Test token clearing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            auth = GitHubCopilotAuth(token_dir=Path(tmpdir))

            token = CopilotToken(
                token="test_token",
                expires_at=int(time.time()) + 3600,
            )
            auth.save_token(token)
            assert auth.is_authenticated

            auth.clear_token()
            assert not auth.is_authenticated

    def test_is_authenticated(self):
        """Test authentication status check"""
        with tempfile.TemporaryDirectory() as tmpdir:
            auth = GitHubCopilotAuth(token_dir=Path(tmpdir))
            assert not auth.is_authenticated

            token = CopilotToken(
                token="test_token",
                expires_at=int(time.time()) + 3600,
            )
            auth.save_token(token)
            assert auth.is_authenticated

    def test_has_valid_token(self):
        """Test valid token check"""
        with tempfile.TemporaryDirectory() as tmpdir:
            auth = GitHubCopilotAuth(token_dir=Path(tmpdir))
            assert not auth.has_valid_token

            # Save valid token
            token = CopilotToken(
                token="test_token",
                expires_at=int(time.time()) + 3600,
            )
            auth.save_token(token)
            assert auth.has_valid_token

            # Save expired token
            expired_token = CopilotToken(
                token="expired_token",
                expires_at=int(time.time()) - 3600,
            )
            auth.save_token(expired_token)
            assert not auth.has_valid_token

    def test_new_session(self):
        """Test creating new session"""
        auth = GitHubCopilotAuth()
        session1 = auth.session
        session1.get_initiator()  # Mark first message

        session2 = auth.new_session()
        assert session1 is not session2
        assert session2.is_first_message

    def test_get_api_headers_requires_token(self):
        """Test that get_api_headers raises without token"""
        with tempfile.TemporaryDirectory() as tmpdir:
            auth = GitHubCopilotAuth(token_dir=Path(tmpdir))
            with pytest.raises(ValueError, match="No Copilot token"):
                auth.get_api_headers()

    def test_get_api_headers_with_token(self):
        """Test API headers generation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            auth = GitHubCopilotAuth(token_dir=Path(tmpdir))
            token = CopilotToken(
                token="test_token",
                expires_at=int(time.time()) + 3600,
            )
            auth.save_token(token)

            headers = auth.get_api_headers()
            assert "Authorization" in headers
            assert headers["Authorization"] == "Bearer test_token"
            assert "X-Initiator" in headers
            assert "Editor-Version" in headers
            assert "Copilot-Integration-Id" in headers


class TestGitHubCopilotAuthAsync:
    """Async tests for GitHubCopilotAuth"""

    @pytest.mark.asyncio
    async def test_get_device_code(self):
        """Test device code request"""
        with tempfile.TemporaryDirectory() as tmpdir:
            auth = GitHubCopilotAuth(token_dir=Path(tmpdir))

            mock_response = {
                "device_code": "test_device_code",
                "user_code": "ABCD-1234",
                "verification_uri": "https://github.com/login/device",
                "expires_in": 900,
                "interval": 5,
            }

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_response_obj = MagicMock()
                mock_response_obj.json.return_value = mock_response
                mock_response_obj.raise_for_status = MagicMock()
                mock_client.post.return_value = mock_response_obj
                mock_client_class.return_value = mock_client

                result = await auth.get_device_code()

                assert result.device_code == "test_device_code"
                assert result.user_code == "ABCD-1234"
                assert result.verification_uri == "https://github.com/login/device"

    @pytest.mark.asyncio
    async def test_get_copilot_token(self):
        """Test getting Copilot token from GitHub token"""
        with tempfile.TemporaryDirectory() as tmpdir:
            auth = GitHubCopilotAuth(token_dir=Path(tmpdir))
            auth._github_token = "test_github_token"

            future_time = int(time.time()) + 3600
            mock_response = {
                "token": "copilot_token",
                "expires_at": future_time,
            }

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_response_obj = MagicMock()
                mock_response_obj.json.return_value = mock_response
                mock_response_obj.raise_for_status = MagicMock()
                mock_client.get.return_value = mock_response_obj
                mock_client_class.return_value = mock_client

                result = await auth.get_copilot_token()

                assert result.token == "copilot_token"
                assert result.expires_at == future_time

    @pytest.mark.asyncio
    async def test_ensure_valid_token_with_valid_token(self):
        """Test ensure_valid_token returns existing valid token"""
        with tempfile.TemporaryDirectory() as tmpdir:
            auth = GitHubCopilotAuth(token_dir=Path(tmpdir))

            token = CopilotToken(
                token="valid_token",
                expires_at=int(time.time()) + 3600,
            )
            auth.save_token(token)

            result = await auth.ensure_valid_token()
            assert result.token == "valid_token"

    @pytest.mark.asyncio
    async def test_ensure_valid_token_without_token(self):
        """Test ensure_valid_token raises without token"""
        with tempfile.TemporaryDirectory() as tmpdir:
            auth = GitHubCopilotAuth(token_dir=Path(tmpdir))

            with pytest.raises(ValueError, match="No valid Copilot token"):
                await auth.ensure_valid_token()
