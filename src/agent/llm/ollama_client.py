"""
Ollama LLM Client for Agent

Handles communication with Ollama and parses JSON responses.
"""

import json
import re
from typing import List, Dict, Optional, Any
from pathlib import Path
import logging

from pydantic import BaseModel

from .base import AgentResponse, LLMClient

try:
    import ollama
except ImportError:
    ollama = None

logger = logging.getLogger(__name__)


class _ActionSchema(BaseModel):
    """LLM 응답의 각 액션에 대해 구조화된 출력을 강제하기 위한 스키마.

    params는 도구마다 모양이 다르므로 여기서는 최소한의 형태(dict)만 강제하고,
    개별 도구별 필수 파라미터 검증은 기존처럼 ToolExecutor/SecurityValidator가 담당한다."""

    tool: str
    params: Dict[str, Any] = {}


class _AgentResponseSchema(BaseModel):
    """Ollama의 constrained decoding(`format` 파라미터)에 넘길 응답 스키마.

    이걸 강제하면 모델이 마크다운 코드펜스를 섞거나 따옴표/줄바꿈 이스케이프를
    틀려서 JSON 파싱 자체가 깨지는 실패(오늘 라이브 에이전트 위임에서 반복 관찰됨)를
    샘플링 단계에서부터 구조적으로 막는다. 필드 값 자체의 정확성(예: 존재하지 않는
    파라미터를 지어내는 것)까지 막아주진 않는다."""

    reasoning: Optional[str] = None
    actions: List[_ActionSchema] = []


class OllamaAgentClient(LLMClient):
    """
    Ollama를 사용한 에이전트 LLM 클라이언트

    시스템 프롬프트와 대화 히스토리를 사용하여
    LLM에게 다음 액션을 요청하고 JSON으로 파싱합니다.
    """

    def __init__(
        self,
        host: str,
        model: str = "qwen2.5-coder:7b",
        temperature: float = 0.1,
        system_prompt_path: Optional[str] = None
    ):
        """
        Args:
            host: Ollama 호스트 URL (예: "http://localhost:11434")
            model: 사용할 모델 이름
            temperature: 생성 온도 (0.0 ~ 2.0)
            system_prompt_path: 시스템 프롬프트 파일 경로
        """
        if ollama is None:
            raise ImportError(
                "ollama package is not installed. "
                "Install it with: pip install ollama"
            )

        self.client = ollama.Client(host=host)
        self.model = model
        self.temperature = temperature

        # 시스템 프롬프트 로드
        if system_prompt_path and Path(system_prompt_path).exists():
            with open(system_prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()
            logger.info(f"Loaded system prompt from {system_prompt_path}")
        else:
            # 기본 시스템 프롬프트
            self.system_prompt = self._default_system_prompt()
            logger.warning("Using default system prompt")

        logger.info(
            f"OllamaAgentClient initialized: model={model}, "
            f"temperature={temperature}"
        )

    def get_next_actions(
        self,
        conversation_history: List[Dict[str, str]],
        workspace_path: str
    ) -> AgentResponse:
        """
        다음 액션 생성 (동기)

        Args:
            conversation_history: 대화 히스토리 [{"role": "user", "content": "..."}]
            workspace_path: 작업 디렉토리 경로

        Returns:
            AgentResponse (reasoning, actions, raw_response)

        Raises:
            ValueError: JSON 파싱 실패
            Exception: Ollama 통신 실패
        """
        # 시스템 프롬프트에 workspace 정보 추가
        full_system_prompt = (
            f"{self.system_prompt}\n\n"
            f"**Current workspace**: {workspace_path}\n"
            f"**Important**: Respond ONLY with valid JSON. No markdown, no code blocks, just pure JSON."
        )

        # 메시지 구성
        messages = [
            {"role": "system", "content": full_system_prompt}
        ] + conversation_history

        logger.info(f"Requesting next actions from LLM (history: {len(conversation_history)} messages)")

        try:
            # Ollama 호출 — format에 JSON 스키마를 넘겨 샘플링 단계에서부터 문법적으로
            # 유효한 JSON만 생성하도록 강제한다(Ollama 0.3.0+ Structured Outputs).
            response = self.client.chat(
                model=self.model,
                messages=messages,
                options={"temperature": self.temperature},
                format=_AgentResponseSchema.model_json_schema(),
                stream=False
            )

            raw_response = response["message"]["content"]

            logger.debug(f"LLM response ({len(raw_response)} chars):\n{raw_response[:200]}...")

            # JSON 파싱
            parsed = self._parse_json_response(raw_response)

            agent_response = AgentResponse(
                reasoning=parsed.get("reasoning"),
                actions=parsed.get("actions", []),
                raw_response=raw_response
            )

            logger.info(
                f"Parsed agent response: {len(agent_response.actions)} actions"
            )

            return agent_response

        except Exception as e:
            logger.error(f"Failed to get next actions: {e}")
            raise

    async def get_next_actions_async(
        self,
        conversation_history: List[Dict[str, str]],
        workspace_path: str
    ) -> AgentResponse:
        """
        다음 액션 생성 (비동기)

        Args:
            conversation_history: 대화 히스토리
            workspace_path: 작업 디렉토리 경로

        Returns:
            AgentResponse
        """
        # 비동기 버전 (필요시 구현)
        # 현재는 동기 버전 호출
        import asyncio
        return await asyncio.to_thread(
            self.get_next_actions,
            conversation_history,
            workspace_path
        )

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """
        LLM 응답에서 JSON 추출

        LLM은 종종 ```json ... ``` 같은 코드 블록으로 감싸므로 제거
        """
        # 1. 코드 블록 제거
        cleaned = response.strip()

        # ```json ... ``` 패턴 제거
        cleaned = re.sub(r'```json\s*', '', cleaned)
        cleaned = re.sub(r'```\s*', '', cleaned)

        # 2. JSON 파싱 시도
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"Initial JSON parse failed: {e}")

            # 3. {} 패턴 찾기 시도
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

            # 4. 더 관대한 파싱 시도 (줄바꿈 등 정리)
            try:
                # 불필요한 공백 제거
                cleaned_minimal = re.sub(r'\s+', ' ', cleaned)
                return json.loads(cleaned_minimal)
            except json.JSONDecodeError:
                pass

            # 파싱 실패
            logger.error(f"Failed to parse JSON response:\n{response[:500]}")
            raise ValueError(
                f"Failed to parse LLM response as JSON. "
                f"Response:\n{response[:500]}...\n\n"
                f"Error: {e}"
            )

    def test_connection(self) -> bool:
        """
        Ollama 연결 테스트

        Returns:
            연결 성공 여부
        """
        try:
            models = self.client.list()
            logger.info(f"Connected to Ollama: {len(models.get('models', []))} models available")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {e}")
            return False

    def check_model_available(self) -> bool:
        """
        모델 사용 가능 여부 확인

        Returns:
            모델이 다운로드되어 있는지 여부
        """
        try:
            models = self.client.list()
            available = any(
                self.model in model.get("name", "")
                for model in models.get("models", [])
            )

            if available:
                logger.info(f"Model {self.model} is available")
            else:
                logger.warning(
                    f"Model {self.model} not found. "
                    f"Download with: ollama pull {self.model}"
                )

            return available

        except Exception as e:
            logger.error(f"Failed to check model availability: {e}")
            return False

    def _default_system_prompt(self) -> str:
        """기본 시스템 프롬프트"""
        return """You are an AI coding agent that helps users modify code.

You can only respond with JSON in this format:
{
  "reasoning": "Why you're taking this action (optional)",
  "actions": [
    {
      "tool": "tool_name",
      "params": {"param1": "value1"}
    }
  ]
}

Available tools and their REQUIRED parameters:
- read_file: {"path": "src/main.py"}
- edit_file: {"path": "src/main.py", "old_string": "old code", "new_string": "new code"}
- create_file: {"path": "src/new_file.py", "content": "file content here"}
- delete_file: {"path": "src/old_file.py", "confirm": true}
- list_files: {"path": "."} or {"path": "src"}
- search_code: {"pattern": "def hello", "path": "."}
- run_tests: {"scope": "all"} or {"scope": "directory", "path": "tests/"} or {"scope": "filter", "filter": "test_name"}
- run_command: {"command": "pytest tests/"}
- finish: {"message": "Task completed successfully"}

CRITICAL PATH RULES:
1. "path" parameter is ALWAYS required for all file tools
2. ALWAYS use relative paths (e.g., "src/main.py", NOT "/workspace/src/main.py")
3. The workspace root is shown as "Current workspace" in this prompt
4. Files are relative to that workspace root

CRITICAL COMPLETION RULE:
- After ALL requested actions succeed, you MUST call the finish tool immediately.
- Do NOT repeat an action that already succeeded.
- Do NOT call create_file if the file was already created successfully.

Example of correct workflow:
1. User asks to create a file → call create_file
2. Tool result shows success → call finish
{"reasoning": "File created successfully", "actions": [{"tool": "finish", "params": {"message": "Created the file as requested"}}]}

Always respond with valid JSON. No markdown, no explanations outside JSON."""
