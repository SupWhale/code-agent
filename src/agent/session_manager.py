"""
Session Manager

VS Code Extension을 위한 클라이언트 세션 관리
"""

from typing import Dict, Optional, List
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timedelta
import uuid
import shutil
import logging

logger = logging.getLogger(__name__)


@dataclass
class FileInfo:
    """파일 정보"""
    path: str
    content: str
    last_modified: datetime = field(default_factory=datetime.now)


@dataclass
class ClientSession:
    """
    클라이언트 세션

    각 VS Code 클라이언트마다 격리된 작업 환경을 제공합니다.
    """
    session_id: str
    workspace_path: Path
    files: Dict[str, FileInfo] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)

    def update_activity(self) -> None:
        """마지막 활동 시간 업데이트"""
        self.last_activity = datetime.now()

    def is_expired(self, timeout_minutes: int = 30) -> bool:
        """세션 만료 여부 확인"""
        return datetime.now() - self.last_activity > timedelta(minutes=timeout_minutes)

    def add_file(self, file_path: str, content: str) -> None:
        """파일 추가 또는 업데이트"""
        self.files[file_path] = FileInfo(
            path=file_path,
            content=content,
            last_modified=datetime.now()
        )
        self.update_activity()
        logger.debug(f"Session {self.session_id}: File added/updated: {file_path}")

    def get_file(self, file_path: str) -> Optional[str]:
        """파일 내용 조회"""
        file_info = self.files.get(file_path)
        if file_info:
            self.update_activity()
            return file_info.content
        return None

    def list_files(self) -> List[str]:
        """모든 파일 경로 목록"""
        return list(self.files.keys())

    def get_file_count(self) -> int:
        """파일 개수"""
        return len(self.files)

    def clear_files(self) -> None:
        """모든 파일 삭제"""
        self.files.clear()
        logger.info(f"Session {self.session_id}: All files cleared")

    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            "session_id": self.session_id,
            "workspace_path": str(self.workspace_path),
            "file_count": self.get_file_count(),
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "is_expired": self.is_expired()
        }


class SessionManager:
    """
    세션 관리자

    여러 클라이언트의 세션을 관리하고 격리된 workspace를 제공합니다.
    """

    def __init__(self, base_workspace_path: str):
        """
        Args:
            base_workspace_path: 세션별 workspace의 기본 경로
        """
        self.base_workspace_path = Path(base_workspace_path)
        self.sessions: Dict[str, ClientSession] = {}

        # Base workspace 디렉토리 생성
        self.base_workspace_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"SessionManager initialized: {self.base_workspace_path}")

    def create_session(self, session_id: Optional[str] = None) -> ClientSession:
        """
        새 세션 생성

        Args:
            session_id: 세션 ID (없으면 자동 생성)

        Returns:
            생성된 ClientSession

        Raises:
            ValueError: session_id가 이미 존재하는 경우
        """
        if session_id is None:
            session_id = str(uuid.uuid4())

        if session_id in self.sessions:
            raise ValueError(f"Session {session_id} already exists")

        # 세션별 workspace 디렉토리 생성
        workspace_path = self.base_workspace_path / session_id
        workspace_path.mkdir(parents=True, exist_ok=True)

        session = ClientSession(
            session_id=session_id,
            workspace_path=workspace_path
        )

        self.sessions[session_id] = session
        logger.info(f"Session created: {session_id}")

        return session

    def get_session(self, session_id: str) -> Optional[ClientSession]:
        """
        세션 조회

        Args:
            session_id: 세션 ID

        Returns:
            ClientSession 또는 None
        """
        session = self.sessions.get(session_id)
        if session:
            session.update_activity()
        return session

    def delete_session(self, session_id: str) -> bool:
        """
        세션 삭제

        Args:
            session_id: 세션 ID

        Returns:
            삭제 성공 여부
        """
        session = self.sessions.get(session_id)
        if not session:
            return False

        # Workspace 디렉토리 삭제
        try:
            if session.workspace_path.exists():
                shutil.rmtree(session.workspace_path)
                logger.info(f"Session workspace deleted: {session.workspace_path}")
        except Exception as e:
            logger.error(f"Failed to delete workspace: {e}")

        # 세션 제거
        del self.sessions[session_id]
        logger.info(f"Session deleted: {session_id}")

        return True

    def cleanup_expired_sessions(self, timeout_minutes: int = 30) -> int:
        """
        만료된 세션 정리

        Args:
            timeout_minutes: 타임아웃 (분)

        Returns:
            삭제된 세션 수
        """
        expired_sessions = [
            session_id
            for session_id, session in self.sessions.items()
            if session.is_expired(timeout_minutes)
        ]

        for session_id in expired_sessions:
            self.delete_session(session_id)

        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

        return len(expired_sessions)

    def list_sessions(self) -> List[ClientSession]:
        """모든 세션 목록"""
        return list(self.sessions.values())

    def get_stats(self) -> Dict:
        """세션 통계"""
        total_sessions = len(self.sessions)
        active_sessions = sum(
            1 for s in self.sessions.values()
            if not s.is_expired()
        )
        expired_sessions = total_sessions - active_sessions
        total_files = sum(s.get_file_count() for s in self.sessions.values())

        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "expired_sessions": expired_sessions,
            "total_files": total_files
        }

    def add_file_to_session(
        self,
        session_id: str,
        file_path: str,
        content: str
    ) -> bool:
        """
        세션에 파일 추가

        Args:
            session_id: 세션 ID
            file_path: 파일 경로
            content: 파일 내용

        Returns:
            성공 여부
        """
        session = self.get_session(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            return False

        session.add_file(file_path, content)

        # 실제 파일 시스템에도 저장 (선택사항)
        try:
            full_path = session.workspace_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding='utf-8')
            logger.debug(f"File written to disk: {full_path}")
        except Exception as e:
            logger.error(f"Failed to write file to disk: {e}")

        return True

    def get_file_from_session(
        self,
        session_id: str,
        file_path: str
    ) -> Optional[str]:
        """
        세션에서 파일 내용 조회

        Args:
            session_id: 세션 ID
            file_path: 파일 경로

        Returns:
            파일 내용 또는 None
        """
        session = self.get_session(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            return None

        return session.get_file(file_path)

    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"<SessionManager sessions={stats['total_sessions']} "
            f"active={stats['active_sessions']} "
            f"files={stats['total_files']}>"
        )
