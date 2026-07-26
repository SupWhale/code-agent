"""LLM 클라이언트 팩토리(전략 선택기) 단위 테스트"""

import pytest

from src.agent.llm.factory import create_llm_client
from src.agent.llm.ollama_client import OllamaAgentClient


def test_create_ollama_client(monkeypatch):
    # OllamaAgentClient.__init__은 실제 ollama.Client(host=...)를 만드는데, 여기서는
    # 연결 자체가 필요 없으므로 ollama.Client를 더미로 바꿔치기한다.
    import src.agent.llm.ollama_client as ollama_client_module

    class _FakeOllamaClient:
        def __init__(self, host):
            self.host = host

    monkeypatch.setattr(ollama_client_module.ollama, "Client", _FakeOllamaClient)

    client = create_llm_client("ollama", "qwen2.5-coder:7b", host="http://localhost:11434")

    assert isinstance(client, OllamaAgentClient)
    assert client.model == "qwen2.5-coder:7b"


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_llm_client("does-not-exist", "some-model", host="http://localhost:11434")
