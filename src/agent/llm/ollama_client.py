"""
Ollama LLM Client for Agent

Handles communication with Ollama and parses JSON responses.
"""

import json
import re
from typing import List, Dict, Optional, Any
from pathlib import Path
import logging

try:
    import ollama
except ImportError:
    ollama = None

logger = logging.getLogger(__name__)


class AgentResponse:
    """에이전트 응답"""

    def __init__(self, reasoning: Optional[str], actions: List[Dict], raw_response: str):
        self.reasoning = reasoning
        self.actions = actions
        self.raw_response = raw_response

    def __repr__(self) -> str:
        return (
            f"<AgentResponse reasoning={bool(self.reasoning)} "
            f"actions={len(self.actions)}>"
        )


class OllamaAgentClient:
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
            # Ollama 호출
            response = self.client.chat(
                model=self.model,
                messages=messages,
                options={"temperature": self.temperature},
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

Available tools:
- read_file: Read a file
- edit_file: Edit a file using string replacement
- create_file: Create a new file
- delete_file: Delete a file
- list_files: List files in a directory
- search_code: Search for code patterns
- run_tests: Run tests
- run_command: Run allowed commands
- finish: Mark task as complete

Always respond with valid JSON. No markdown, no explanations outside JSON."""
