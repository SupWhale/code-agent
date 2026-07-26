"""
LLM Client Factory

전략 패턴의 선택기 — provider 이름으로 구체적인 LLMClient 구현체를 생성한다.
새 provider를 추가할 때는 _PROVIDERS 레지스트리에 등록만 하면 되고,
AgentOrchestrator/TaskManager 등 호출부는 LLMClient 인터페이스만 알면 된다.
"""

from typing import Dict, Optional, Type

from .base import LLMClient
from .ollama_client import OllamaAgentClient

_PROVIDERS: Dict[str, Type[LLMClient]] = {
    "ollama": OllamaAgentClient,
}


def create_llm_client(
    provider: str,
    model: str,
    host: str,
    temperature: float = 0.1,
    system_prompt_path: Optional[str] = None,
) -> LLMClient:
    """
    provider 이름에 해당하는 LLMClient 구현체를 생성한다.

    Args:
        provider: 레지스트리에 등록된 provider 이름 (예: "ollama")
        model: 해당 provider 안에서 사용할 모델 이름
        host: 백엔드 호스트 URL
        temperature: 생성 온도
        system_prompt_path: 시스템 프롬프트 파일 경로

    Returns:
        LLMClient 인스턴스

    Raises:
        ValueError: 등록되지 않은 provider
    """
    client_cls = _PROVIDERS.get(provider)
    if client_cls is None:
        raise ValueError(
            f"Unknown LLM provider: {provider!r}. "
            f"Available providers: {sorted(_PROVIDERS)}"
        )

    return client_cls(
        host=host,
        model=model,
        temperature=temperature,
        system_prompt_path=system_prompt_path,
    )
