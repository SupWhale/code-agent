"""
Interaction Tools

Tools for agent-user interaction and task control.
"""

from typing import Dict, Any, List, Optional
import logging

from .base import BaseTool

logger = logging.getLogger(__name__)


def _as_bool(value: Any, default: bool = True) -> bool:
    """모델이 불리언 자리에 문자열/숫자를 넣어도 받아준다."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "y", "1"):
            return True
        if lowered in ("false", "no", "n", "0"):
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _as_str_list(value: Any) -> List[str]:
    """경로 리스트 정규화. 파일 하나를 문자열로 보내는 경우가 잦다."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


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
                "success": bool,          # 작업 성공 여부
                "message": str,           # 완료 메시지 (optional)
                "changed_files": [str],   # 변경했다고 주장하는 파일 (optional)
                "summary": dict,          # 변경 통계 (optional)
                "result": dict            # 결과 데이터 (optional, 레거시)
            }

        시스템 프롬프트는 changed_files/summary를 finish 계약에 포함시켜 놓고도
        이 도구는 success/message/result만 읽고 나머지를 버렸다. 그래서 모델이
        계약대로 보낸 정보가 검증 단계에 닿지 못했다. 여기서 정식 필드로 받는다.

        Returns:
            완료 정보 딕셔너리
        """
        message_raw = params.get("message")
        summary_raw = params.get("summary")

        # message(문자열)와 summary(객체)의 타입을 서로 바꿔 보내는 모델이 있어,
        # 필드 이름이 아니라 타입을 기준으로 각자 제자리를 찾아준다.
        message = "Task completed"
        for candidate in (message_raw, summary_raw):
            if isinstance(candidate, str) and candidate.strip():
                message = candidate.strip()
                break

        summary: Dict[str, Any] = {}
        for candidate in (summary_raw, message_raw):
            if isinstance(candidate, dict) and candidate:
                summary = candidate
                break

        success = _as_bool(params.get("success", True))
        changed_files = _as_str_list(params.get("changed_files"))

        result = params.get("result")
        if not isinstance(result, dict):
            result = {}

        logger.info(
            f"Task finished: success={success}, message={message}, "
            f"changed_files={changed_files}"
        )

        return {
            "finished": True,
            "success": success,
            "message": message,
            "changed_files": changed_files,
            "summary": summary,
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
