"""
LLM Client Strategy Interface

에이전트가 사용하는 모든 LLM 백엔드(Ollama, 추후 다른 provider)가 구현해야 하는 공통
인터페이스. AgentOrchestrator/TaskManager는 이 인터페이스만 알고, 구체적인 구현체는
`src/agent/llm/factory.py`의 레지스트리를 통해 선택된다 — 전략 패턴.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List, Optional


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

    async def stream_next_actions(
        self,
        conversation_history: List[Dict[str, str]],
        workspace_path: str
    ) -> AsyncIterator[Dict]:
        """
        다음 액션을 스트리밍으로 요청한다.

        논스트리밍 백엔드를 위한 기본 구현은 get_next_actions_async()를 그대로
        감싸 "done" 이벤트 하나만 낸다. 토큰 단위로 응답을 흘려보낼 수 있는
        백엔드(OllamaAgentClient 등)는 이 메서드를 오버라이드해서, 생성이
        완료될 때까지 아무 이벤트도 안 나가는 침묵 구간(SSE/WebSocket이 nginx
        idle 타임아웃에 걸리는 원인)을 없앤다.

        Yields:
            {"type": "token", "content": str} — 생성 중 텍스트 조각 (지원하는 백엔드만)
            {"type": "done", "response": AgentResponse} — 최종 응답 (항상 마지막에 1회)
        """
        response = await self.get_next_actions_async(conversation_history, workspace_path)
        yield {"type": "done", "response": response}

    @abstractmethod
    def test_connection(self) -> bool:
        """백엔드 연결 가능 여부 확인."""
        raise NotImplementedError

    @abstractmethod
    def check_model_available(self) -> bool:
        """설정된 모델이 실제로 사용 가능한지 확인."""
        raise NotImplementedError
