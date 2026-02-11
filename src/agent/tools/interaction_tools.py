"""
Interaction Tools

Tools for agent-user interaction and task control.
"""

from typing import Dict, Any, Optional
import logging

from .base import BaseTool

logger = logging.getLogger(__name__)


class FinishTool(BaseTool):
    """
    작업 완료 도구

    에이전트가 작업을 완료했음을 표시합니다.
    """

    def __init__(self):
        """FinishTool은 workspace_path가 필요 없음"""
        super().__init__(workspace_path=None)

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        작업 완료 처리

        Args:
            params: {
                "success": bool,  # 작업 성공 여부
                "message": str,   # 완료 메시지 (optional)
                "result": dict    # 결과 데이터 (optional)
            }

        Returns:
            완료 정보 딕셔너리
        """
        success = params.get("success", True)
        message = params.get("message", "Task completed")
        result = params.get("result", {})

        logger.info(f"Task finished: success={success}, message={message}")

        return {
            "finished": True,
            "success": success,
            "message": message,
            "result": result
        }


class AskUserTool(BaseTool):
    """
    사용자 질문 도구

    에이전트가 사용자에게 질문하거나 입력을 요청합니다.
    """

    def __init__(self):
        """AskUserTool은 workspace_path가 필요 없음"""
        super().__init__(workspace_path=None)

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        사용자 질문 처리

        Args:
            params: {
                "question": str,      # 질문 내용
                "options": list,      # 선택지 (optional)
                "default": str        # 기본값 (optional)
            }

        Returns:
            질문 정보 딕셔너리
        """
        self._validate_params(params, ["question"])

        question = params["question"]
        options = params.get("options")
        default = params.get("default")

        logger.info(f"Asking user: {question}")

        # 실제 구현에서는 WebSocket이나 API를 통해 사용자 입력을 대기
        return {
            "asked": True,
            "question": question,
            "options": options,
            "default": default,
            "awaiting_response": True
        }


class ReportErrorTool(BaseTool):
    """
    에러 보고 도구

    에이전트가 치명적인 에러를 발견했을 때 보고합니다.
    """

    def __init__(self):
        """ReportErrorTool은 workspace_path가 필요 없음"""
        super().__init__(workspace_path=None)

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        에러 보고 처리

        Args:
            params: {
                "error": str,         # 에러 메시지
                "details": str,       # 상세 정보 (optional)
                "recoverable": bool   # 복구 가능 여부 (optional)
            }

        Returns:
            에러 정보 딕셔너리
        """
        self._validate_params(params, ["error"])

        error = params["error"]
        details = params.get("details", "")
        recoverable = params.get("recoverable", False)

        logger.error(f"Agent reported error: {error}")
        if details:
            logger.error(f"Error details: {details}")

        return {
            "error_reported": True,
            "error": error,
            "details": details,
            "recoverable": recoverable
        }
