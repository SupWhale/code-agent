"""
Synchronization Tools

VS Code Extension을 위한 파일 동기화 도구
"""

from typing import Dict, Any
import difflib
import logging

from .base import BaseTool

logger = logging.getLogger(__name__)


class SessionReadFileTool(BaseTool):
    """
    세션 파일 읽기 도구

    SessionManager의 파일을 읽습니다.
    """

    def __init__(self, session_manager):
        """
        Args:
            session_manager: SessionManager 인스턴스
        """
        super().__init__(workspace_path=None)
        self.session_manager = session_manager

    async def execute(self, params: Dict[str, Any]) -> str:
        """
        세션 파일 읽기

        Args:
            params: {
                "session_id": str,  # 세션 ID
                "path": str         # 파일 경로
            }

        Returns:
            파일 내용

        Raises:
            ValueError: 파라미터 누락 또는 세션/파일을 찾을 수 없음
        """
        self._validate_params(params, ["session_id", "path"])

        session_id = params["session_id"]
        file_path = params["path"]

        content = self.session_manager.get_file_from_session(session_id, file_path)

        if content is None:
            raise ValueError(
                f"File not found in session {session_id}: {file_path}"
            )

        logger.info(f"Session {session_id}: Read file {file_path}")
        return content


class SessionWriteFileTool(BaseTool):
    """
    세션 파일 쓰기 도구

    SessionManager의 파일을 업데이트합니다.
    """

    def __init__(self, session_manager):
        """
        Args:
            session_manager: SessionManager 인스턴스
        """
        super().__init__(workspace_path=None)
        self.session_manager = session_manager

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        세션 파일 쓰기

        Args:
            params: {
                "session_id": str,  # 세션 ID
                "path": str,        # 파일 경로
                "content": str      # 파일 내용
            }

        Returns:
            결과 딕셔너리

        Raises:
            ValueError: 파라미터 누락 또는 세션을 찾을 수 없음
        """
        self._validate_params(params, ["session_id", "path", "content"])

        session_id = params["session_id"]
        file_path = params["path"]
        content = params["content"]

        success = self.session_manager.add_file_to_session(
            session_id,
            file_path,
            content
        )

        if not success:
            raise ValueError(f"Failed to write file to session {session_id}")

        logger.info(f"Session {session_id}: Wrote file {file_path}")

        return {
            "success": True,
            "path": file_path,
            "size": len(content)
        }


class DiffTool(BaseTool):
    """
    Diff 생성 도구

    두 파일 내용의 차이를 unified diff 형식으로 생성합니다.
    """

    def __init__(self):
        """DiffTool은 workspace_path가 필요 없음"""
        super().__init__(workspace_path=None)

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Diff 생성

        Args:
            params: {
                "old_content": str,  # 원본 내용
                "new_content": str,  # 새 내용
                "file_path": str     # 파일 경로 (선택사항, diff 헤더용)
            }

        Returns:
            Diff 정보 딕셔너리

        Raises:
            ValueError: 파라미터 누락
        """
        self._validate_params(params, ["old_content", "new_content"])

        old_content = params["old_content"]
        new_content = params["new_content"]
        file_path = params.get("file_path", "file")

        # 줄 단위로 분할
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        # Unified diff 생성
        diff_lines = list(difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm=''
        ))

        diff_text = ''.join(diff_lines)

        # 통계 계산
        added_lines = sum(1 for line in diff_lines if line.startswith('+') and not line.startswith('+++'))
        removed_lines = sum(1 for line in diff_lines if line.startswith('-') and not line.startswith('---'))

        logger.info(
            f"Diff generated for {file_path}: "
            f"+{added_lines} -{removed_lines}"
        )

        return {
            "diff": diff_text,
            "file_path": file_path,
            "added_lines": added_lines,
            "removed_lines": removed_lines,
            "has_changes": bool(diff_lines)
        }


class SessionListFilesTool(BaseTool):
    """
    세션 파일 목록 도구

    세션의 모든 파일 목록을 반환합니다.
    """

    def __init__(self, session_manager):
        """
        Args:
            session_manager: SessionManager 인스턴스
        """
        super().__init__(workspace_path=None)
        self.session_manager = session_manager

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        세션 파일 목록 조회

        Args:
            params: {
                "session_id": str  # 세션 ID
            }

        Returns:
            파일 목록 딕셔너리

        Raises:
            ValueError: 세션을 찾을 수 없음
        """
        self._validate_params(params, ["session_id"])

        session_id = params["session_id"]
        session = self.session_manager.get_session(session_id)

        if not session:
            raise ValueError(f"Session not found: {session_id}")

        files = session.list_files()

        logger.info(f"Session {session_id}: Listed {len(files)} files")

        return {
            "session_id": session_id,
            "files": files,
            "count": len(files)
        }
