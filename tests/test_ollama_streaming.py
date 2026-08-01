"""OllamaAgentClient.stream_next_actions() 테스트

ollama.AsyncClient를 실제로 연결하지 않고, 토큰 청크를 순서대로 내보내는
가짜 async 클라이언트로 대체해 스트리밍 동작만 검증한다.
"""

import pytest

from src.agent.llm.ollama_client import OllamaAgentClient


class _FakeChatStream:
    """ollama.AsyncClient.chat(..., stream=True)가 반환하는 async iterator를 흉내낸다."""

    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for chunk in self._chunks:
            yield chunk


class _FakeAsyncOllamaClient:
    def __init__(self, chunks):
        self._chunks = chunks
        self.received_kwargs = None

    async def chat(self, **kwargs):
        self.received_kwargs = kwargs
        return _FakeChatStream(self._chunks)


class _FailingAsyncOllamaClient:
    async def chat(self, **kwargs):
        raise RuntimeError("connection refused")


@pytest.fixture
def client():
    # __init__은 ollama 연결을 요구하므로 우회하고 필요한 속성만 채운다.
    c = OllamaAgentClient.__new__(OllamaAgentClient)
    c.system_prompt = "SYSTEM PROMPT"
    c.model = "qwen2.5-coder:7b"
    c.temperature = 0.1
    return c


@pytest.mark.asyncio
async def test_stream_next_actions_yields_tokens_then_done(client):
    chunks = [
        {"message": {"content": '{"reasoning": "hi", '}},
        {"message": {"content": '"actions": [{"tool": "finish", "params": {}}]}'}},
        {"message": {"content": ""}, "done": True},  # 빈 content는 토큰 이벤트로 안 나가야 함
    ]
    fake_async_client = _FakeAsyncOllamaClient(chunks)
    client.async_client = fake_async_client

    events = [
        event
        async for event in client.stream_next_actions(
            conversation_history=[], workspace_path="/workspace"
        )
    ]

    token_events = [e for e in events if e["type"] == "token"]
    done_events = [e for e in events if e["type"] == "done"]

    assert [e["content"] for e in token_events] == [
        '{"reasoning": "hi", ',
        '"actions": [{"tool": "finish", "params": {}}]}',
    ]

    assert len(done_events) == 1
    response = done_events[0]["response"]
    assert response.reasoning == "hi"
    assert response.actions[0]["tool"] == "finish"

    # done 이벤트가 항상 마지막
    assert events[-1]["type"] == "done"

    # stream=True로 호출됐고, 기존 Structured Outputs 강제(format)가 그대로 유지되는지
    assert fake_async_client.received_kwargs["stream"] is True
    assert "format" in fake_async_client.received_kwargs


@pytest.mark.asyncio
async def test_stream_next_actions_propagates_error(client):
    client.async_client = _FailingAsyncOllamaClient()

    with pytest.raises(RuntimeError, match="connection refused"):
        async for _event in client.stream_next_actions(
            conversation_history=[], workspace_path="/workspace"
        ):
            pass


@pytest.mark.asyncio
async def test_stream_next_actions_invalid_json_raises(client):
    chunks = [{"message": {"content": "I cannot help with that."}}]
    client.async_client = _FakeAsyncOllamaClient(chunks)

    with pytest.raises(ValueError, match="Failed to parse"):
        async for _event in client.stream_next_actions(
            conversation_history=[], workspace_path="/workspace"
        ):
            pass
