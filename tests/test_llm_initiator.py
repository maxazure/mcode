import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from maxagent.llm.client import LLMClient, LLMConfig
from maxagent.llm.models import Message


def _mock_chat_response(content: str = "ok"):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "id": "test",
        "model": "test-model",
        "choices": [{"message": {"content": content}}],
        "usage": {},
    }
    return resp


@pytest.mark.asyncio
async def test_llmclient_adds_x_initiator_header_sequence():
    config = LLMConfig(
        base_url="http://example.com",
        api_key="test-key",
        model="test-model",
        parse_thinking=False,
    )
    llm = LLMClient(config)

    mock_client = AsyncMock()
    mock_client.is_closed = False
    mock_client.post.return_value = _mock_chat_response()

    with patch("httpx.AsyncClient", return_value=mock_client):
        messages = [Message(role="user", content="hi")]
        await llm.chat(messages=messages, stream=False)
        await llm.chat(messages=messages, stream=False)

    first_headers = mock_client.post.call_args_list[0].kwargs.get("headers", {})
    second_headers = mock_client.post.call_args_list[1].kwargs.get("headers", {})
    assert first_headers["X-Initiator"] == "user"
    assert second_headers["X-Initiator"] == "agent"


@pytest.mark.asyncio
async def test_new_session_resets_initiator():
    config = LLMConfig(
        base_url="http://example.com",
        api_key="test-key",
        model="test-model",
        parse_thinking=False,
    )
    llm = LLMClient(config)

    mock_client = AsyncMock()
    mock_client.is_closed = False
    mock_client.post.return_value = _mock_chat_response()

    with patch("httpx.AsyncClient", return_value=mock_client):
        messages = [Message(role="user", content="hi")]
        await llm.chat(messages=messages, stream=False)
        llm.new_session()
        await llm.chat(messages=messages, stream=False)

    headers1 = mock_client.post.call_args_list[0].kwargs.get("headers", {})
    headers2 = mock_client.post.call_args_list[1].kwargs.get("headers", {})
    assert headers1["X-Initiator"] == "user"
    assert headers2["X-Initiator"] == "user"

