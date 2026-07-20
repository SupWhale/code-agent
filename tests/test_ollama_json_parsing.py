"""OllamaAgentClient JSON 파싱 테스트

ollama 패키지 없이도 동작하도록 __init__을 우회하여 파싱 로직만 검증한다.
"""

import pytest

from src.agent.llm.ollama_client import OllamaAgentClient


@pytest.fixture
def client():
    # __init__은 ollama 연결을 요구하므로 우회
    return OllamaAgentClient.__new__(OllamaAgentClient)


def test_pure_json(client):
    response = '{"reasoning": "test", "actions": [{"tool": "finish", "params": {}}]}'
    parsed = client._parse_json_response(response)
    assert parsed["reasoning"] == "test"
    assert parsed["actions"][0]["tool"] == "finish"


def test_json_in_code_block(client):
    response = '```json\n{"reasoning": "r", "actions": []}\n```'
    parsed = client._parse_json_response(response)
    assert parsed["reasoning"] == "r"


def test_json_in_plain_code_block(client):
    response = '```\n{"actions": []}\n```'
    parsed = client._parse_json_response(response)
    assert parsed["actions"] == []


def test_json_with_surrounding_text(client):
    response = 'Here is my plan:\n{"reasoning": "x", "actions": []}\nDone.'
    parsed = client._parse_json_response(response)
    assert parsed["reasoning"] == "x"


def test_json_with_korean_content(client):
    response = '{"reasoning": "파일을 생성합니다", "actions": []}'
    parsed = client._parse_json_response(response)
    assert parsed["reasoning"] == "파일을 생성합니다"


def test_invalid_response_raises(client):
    with pytest.raises(ValueError, match="Failed to parse"):
        client._parse_json_response("I cannot help with that.")


def test_empty_response_raises(client):
    with pytest.raises(ValueError):
        client._parse_json_response("")
