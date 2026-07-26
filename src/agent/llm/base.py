"""
LLM Client Strategy Interface

에이전트가 사용하는 모든 LLM 백엔드(Ollama, 추후 다른 provider)가 구현해야 하는 공통
인터페이스. AgentOrchestrator/TaskManager는 이 인터페이스만 알고, 구체적인 구현체는
`src/agent/llm/factory.py`의 레지스트리를 통해 선택된다 — 전략 패턴.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class AgentResponse:
    """에이전트 응답 (LLM 백엔드 중립적인 값 객체)"""

    def __init__(self, reasoning: Optional[str], actions: List[Dict], raw_response: str):
        self.reasoning = reasoning
        self.actions = actions
        self.raw_response = raw_response

    def __repr__(self) -> str:
        return (
            f"<AgentResponse reasoning={bool(self.reasoning)} "
            f"actions={len(self.actions)}>"
        )


class LLMClient(ABC):
    """LLM 백엔드 전략의 공통 인터페이스."""

    model: str

    @abstractmethod
    async def get_next_actions_async(
        self,
        conversation_history: List[Dict[str, str]],
        workspace_path: str
    ) -> AgentResponse:
        """대화 히스토리를 바탕으로 다음 액션(들)을 요청한다."""
        raise NotImplementedError

    @abstractmethod
    def test_connection(self) -> bool:
        """백엔드 연결 가능 여부 확인."""
        raise NotImplementedError

    @abstractmethod
    def check_model_available(self) -> bool:
        """설정된 모델이 실제로 사용 가능한지 확인."""
        raise NotImplementedError
