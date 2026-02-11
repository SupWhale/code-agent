"""
Base Tool Interface for Agent Tools

All agent tools must inherit from BaseTool and implement the execute method.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """도구 실행 중 발생한 에러"""
    pass


class BaseTool(ABC):
    """
    에이전트 도구 베이스 클래스

    모든 도구는 이 클래스를 상속받아 execute 메서드를 구현해야 합니다.
    """

    def __init__(self, workspace_path: Optional[str] = None):
        """
        Args:
            workspace_path: 작업 디렉토리 경로 (파일 관련 도구에서 사용)
        """
        self.workspace_path = Path(workspace_path).resolve() if workspace_path else None
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> Any:
        """
        도구 실행 (서브클래스에서 구현)

        Args:
            params: 도구 파라미터 딕셔너리

        Returns:
            도구 실행 결과 (도구마다 다름)

        Raises:
            ToolExecutionError: 도구 실행 실패 시
            ValueError: 잘못된 파라미터
            FileNotFoundError: 파일을 찾을 수 없음
            PermissionError: 권한 없음
        """
        pass

    def _resolve_path(self, path: str) -> Path:
        """
        경로 해석 (workspace 기준)

        Args:
            path: 상대/절대 경로

        Returns:
            절대 경로 (Path 객체)

        Raises:
            ValueError: workspace_path가 설정되지 않았거나 잘못된 경로
        """
        if not self.workspace_path:
            raise ValueError("workspace_path is not set for this tool")

        p = Path(path)

        # 절대 경로면 그대로 반환
        if p.is_absolute():
            return p.resolve()

        # 상대 경로면 workspace 기준으로 해석
        return (self.workspace_path / path).resolve()

    def _validate_params(self, params: Dict[str, Any], required_keys: list) -> None:
        """
        파라미터 검증

        Args:
            params: 파라미터 딕셔너리
            required_keys: 필수 키 리스트

        Raises:
            ValueError: 필수 파라미터가 없는 경우
        """
        missing_keys = [key for key in required_keys if key not in params]

        if missing_keys:
            raise ValueError(
                f"Missing required parameters: {', '.join(missing_keys)}"
            )

    def __str__(self) -> str:
        """도구 이름 반환"""
        return self.__class__.__name__

    def __repr__(self) -> str:
        """도구 표현"""
        return f"<{self.__class__.__name__} workspace={self.workspace_path}>"
