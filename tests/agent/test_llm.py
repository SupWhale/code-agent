"""
Tests for LLM Integration

Tests LLM client and conversation memory:
- ConversationMemory
- OllamaAgentClient (JSON parsing only, no actual Ollama calls)
"""

import pytest
import json
from pathlib import Path

from src.agent.memory.conversation import ConversationMemory
from src.agent.llm.ollama_client import OllamaAgentClient, AgentResponse


class TestConversationMemory:
    """ConversationMemory 테스트"""

    def test_create_memory(self):
        """메모리 생성 - 성공"""
        memory = ConversationMemory(max_history=10)
        assert memory.count() == 0
        assert len(memory) == 0

    def test_add_user_message(self):
        """사용자 메시지 추가 - 성공"""
        memory = ConversationMemory()

        memory.add_user_message("Hello")

        assert memory.count() == 1
        history = memory.get_history()
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"

    def test_add_assistant_message(self):
        """어시스턴트 메시지 추가 - 성공"""
        memory = ConversationMemory()

        memory.add_assistant_message("Hi there!")

        assert memory.count() == 1
        history = memory.get_history()
        assert history[0]["role"] == "assistant"
        assert history[0]["content"] == "Hi there!"

    def test_add_system_message(self):
        """시스템 메시지 추가 - 성공"""
        memory = ConversationMemory()

        memory.add_system_message("Tool execution result")

        assert memory.count() == 1
        history = memory.get_history()
        assert history[0]["role"] == "system"

    def test_conversation_flow(self):
        """대화 흐름 - 성공"""
        memory = ConversationMemory()

        memory.add_user_message("Add type hints")
        memory.add_assistant_message('{"actions": [{"tool": "read_file"}]}')
        memory.add_system_message("File read successfully")
        memory.add_assistant_message('{"actions": [{"tool": "edit_file"}]}')

        assert memory.count() == 4

        history = memory.get_history()
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
        assert history[2]["role"] == "system"
        assert history[3]["role"] == "assistant"

    def test_max_history_limit(self):
        """히스토리 크기 제한 - 성공"""
        memory = ConversationMemory(max_history=3)

        for i in range(5):
            memory.add_user_message(f"Message {i}")

        # 최대 3개만 유지
        assert memory.count() == 3

        history = memory.get_history()
        assert history[0]["content"] == "Message 2"
        assert history[1]["content"] == "Message 3"
        assert history[2]["content"] == "Message 4"

    def test_get_last_n_messages(self):
        """최근 N개 메시지 조회 - 성공"""
        memory = ConversationMemory()

        for i in range(5):
            memory.add_user_message(f"Message {i}")

        last_2 = memory.get_last_n_messages(2)

        assert len(last_2) == 2
        assert last_2[0]["content"] == "Message 3"
        assert last_2[1]["content"] == "Message 4"

    def test_clear_history(self):
        """히스토리 초기화 - 성공"""
        memory = ConversationMemory()

        memory.add_user_message("Test")
        assert memory.count() == 1

        memory.clear()
        assert memory.count() == 0

    def test_get_summary(self):
        """요약 정보 - 성공"""
        memory = ConversationMemory()

        memory.add_user_message("Hello")
        memory.add_assistant_message("Hi")
        memory.add_system_message("OK")
        memory.add_user_message("Bye")

        summary = memory.get_summary()

        assert summary["total"] == 4
        assert summary["user"] == 2
        assert summary["assistant"] == 1
        assert summary["system"] == 1


class TestOllamaAgentClient:
    """OllamaAgentClient 테스트 (JSON 파싱만)"""

    @pytest.fixture
    def mock_client(self, monkeypatch):
        """Ollama 클라이언트 모킹"""
        # ollama 모듈을 모킹
        class MockOllamaClient:
            def __init__(self, host):
                self.host = host

            def chat(self, model, messages, options=None, stream=False):
                # 간단한 JSON 응답 반환
                return {
                    "message": {
                        "content": json.dumps({
                            "reasoning": "Test reasoning",
                            "actions": [
                                {"tool": "read_file", "params": {"path": "test.py"}}
                            ]
                        })
                    }
                }

            def list(self):
                return {
                    "models": [
                        {"name": "qwen2.5-coder:14b"}
                    ]
                }

        class MockOllama:
            @staticmethod
            def Client(host):
                return MockOllamaClient(host)

        # ollama 모듈을 모킹
        import sys
        sys.modules['ollama'] = MockOllama
        monkeypatch.setattr("src.agent.llm.ollama_client.ollama", MockOllama)

        return MockOllama

    def test_parse_json_clean(self):
        """깔끔한 JSON 파싱 - 성공"""
        # ollama import 우회
        try:
            client = OllamaAgentClient("http://localhost:11434")
        except:
            pytest.skip("ollama not installed")
            return

        json_str = '{"reasoning": "test", "actions": [{"tool": "read_file"}]}'

        result = client._parse_json_response(json_str)

        assert result["reasoning"] == "test"
        assert len(result["actions"]) == 1

    def test_parse_json_with_code_block(self):
        """코드 블록으로 감싼 JSON 파싱 - 성공"""
        try:
            client = OllamaAgentClient("http://localhost:11434")
        except:
            pytest.skip("ollama not installed")
            return

        json_str = '''```json
{
  "reasoning": "test",
  "actions": [{"tool": "read_file"}]
}
```'''

        result = client._parse_json_response(json_str)

        assert result["reasoning"] == "test"
        assert len(result["actions"]) == 1

    def test_parse_json_with_extra_text(self):
        """추가 텍스트가 있는 JSON 파싱 - 성공"""
        try:
            client = OllamaAgentClient("http://localhost:11434")
        except:
            pytest.skip("ollama not installed")
            return

        json_str = '''Here is the response:

{"reasoning": "test", "actions": [{"tool": "read_file"}]}

That's it!'''

        result = client._parse_json_response(json_str)

        assert result["reasoning"] == "test"

    def test_parse_json_invalid(self):
        """잘못된 JSON - 실패"""
        try:
            client = OllamaAgentClient("http://localhost:11434")
        except:
            pytest.skip("ollama not installed")
            return

        json_str = "This is not JSON at all!"

        with pytest.raises(ValueError, match="Failed to parse"):
            client._parse_json_response(json_str)

    def test_default_system_prompt(self):
        """기본 시스템 프롬프트 - 성공"""
        try:
            client = OllamaAgentClient("http://localhost:11434")
        except:
            pytest.skip("ollama not installed")
            return

        assert "JSON" in client.system_prompt
        assert "tools" in client.system_prompt.lower()


class TestAgentResponse:
    """AgentResponse 테스트"""

    def test_create_response(self):
        """응답 생성 - 성공"""
        response = AgentResponse(
            reasoning="Test reasoning",
            actions=[{"tool": "read_file"}],
            raw_response='{"reasoning": "Test reasoning", "actions": [{"tool": "read_file"}]}'
        )

        assert response.reasoning == "Test reasoning"
        assert len(response.actions) == 1
        assert response.actions[0]["tool"] == "read_file"

    def test_response_without_reasoning(self):
        """추론 없는 응답 - 성공"""
        response = AgentResponse(
            reasoning=None,
            actions=[{"tool": "read_file"}],
            raw_response='{}'
        )

        assert response.reasoning is None
        assert len(response.actions) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
