"""
Tests for Session Manager

VS Code Extension용 SessionManager 테스트
"""

import pytest
from pathlib import Path
import tempfile
import time

from src.agent.session_manager import SessionManager, ClientSession


@pytest.fixture
def temp_base_workspace():
    """임시 base workspace"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def session_manager(temp_base_workspace):
    """SessionManager 인스턴스"""
    return SessionManager(temp_base_workspace)


class TestClientSession:
    """ClientSession 테스트"""

    def test_session_creation(self, temp_base_workspace):
        """세션 생성 - 성공"""
        workspace = Path(temp_base_workspace) / "test-session"
        workspace.mkdir()

        session = ClientSession(
            session_id="test-123",
            workspace_path=workspace
        )

        assert session.session_id == "test-123"
        assert session.workspace_path == workspace
        assert session.get_file_count() == 0

    def test_add_file(self, temp_base_workspace):
        """파일 추가 - 성공"""
        workspace = Path(temp_base_workspace) / "test-session"
        workspace.mkdir()

        session = ClientSession(
            session_id="test-123",
            workspace_path=workspace
        )

        session.add_file("test.py", "print('hello')")

        assert session.get_file_count() == 1
        assert session.get_file("test.py") == "print('hello')"

    def test_update_file(self, temp_base_workspace):
        """파일 업데이트 - 성공"""
        workspace = Path(temp_base_workspace) / "test-session"
        workspace.mkdir()

        session = ClientSession(
            session_id="test-123",
            workspace_path=workspace
        )

        session.add_file("test.py", "version 1")
        session.add_file("test.py", "version 2")

        assert session.get_file_count() == 1
        assert session.get_file("test.py") == "version 2"

    def test_get_nonexistent_file(self, temp_base_workspace):
        """존재하지 않는 파일 조회 - None 반환"""
        workspace = Path(temp_base_workspace) / "test-session"
        workspace.mkdir()

        session = ClientSession(
            session_id="test-123",
            workspace_path=workspace
        )

        assert session.get_file("nonexistent.py") is None

    def test_list_files(self, temp_base_workspace):
        """파일 목록 조회 - 성공"""
        workspace = Path(temp_base_workspace) / "test-session"
        workspace.mkdir()

        session = ClientSession(
            session_id="test-123",
            workspace_path=workspace
        )

        session.add_file("test1.py", "content1")
        session.add_file("test2.py", "content2")
        session.add_file("test3.py", "content3")

        files = session.list_files()

        assert len(files) == 3
        assert "test1.py" in files
        assert "test2.py" in files
        assert "test3.py" in files

    def test_is_expired(self, temp_base_workspace):
        """세션 만료 확인 - 성공"""
        workspace = Path(temp_base_workspace) / "test-session"
        workspace.mkdir()

        session = ClientSession(
            session_id="test-123",
            workspace_path=workspace
        )

        # 새로 생성된 세션은 만료되지 않음
        assert not session.is_expired(timeout_minutes=30)

        # 매우 짧은 타임아웃으로 테스트
        time.sleep(0.1)
        assert session.is_expired(timeout_minutes=0)  # 0분 = 즉시 만료

    def test_update_activity(self, temp_base_workspace):
        """활동 시간 업데이트 - 성공"""
        workspace = Path(temp_base_workspace) / "test-session"
        workspace.mkdir()

        session = ClientSession(
            session_id="test-123",
            workspace_path=workspace
        )

        old_activity = session.last_activity
        time.sleep(0.01)
        session.update_activity()
        new_activity = session.last_activity

        assert new_activity > old_activity


class TestSessionManager:
    """SessionManager 테스트"""

    def test_create_session(self, session_manager):
        """세션 생성 - 성공"""
        session = session_manager.create_session("test-session-1")

        assert session.session_id == "test-session-1"
        assert session.workspace_path.exists()
        assert session.workspace_path.is_dir()

    def test_create_session_auto_id(self, session_manager):
        """세션 생성 (자동 ID) - 성공"""
        session = session_manager.create_session()

        assert session.session_id is not None
        assert len(session.session_id) > 0

    def test_create_duplicate_session(self, session_manager):
        """중복 세션 생성 - 실패"""
        session_manager.create_session("duplicate-id")

        with pytest.raises(ValueError, match="already exists"):
            session_manager.create_session("duplicate-id")

    def test_get_session(self, session_manager):
        """세션 조회 - 성공"""
        created_session = session_manager.create_session("test-get")
        retrieved_session = session_manager.get_session("test-get")

        assert retrieved_session is not None
        assert retrieved_session.session_id == created_session.session_id

    def test_get_nonexistent_session(self, session_manager):
        """존재하지 않는 세션 조회 - None 반환"""
        session = session_manager.get_session("nonexistent")

        assert session is None

    def test_delete_session(self, session_manager):
        """세션 삭제 - 성공"""
        session = session_manager.create_session("test-delete")
        workspace_path = session.workspace_path

        assert workspace_path.exists()

        result = session_manager.delete_session("test-delete")

        assert result is True
        assert not workspace_path.exists()
        assert session_manager.get_session("test-delete") is None

    def test_delete_nonexistent_session(self, session_manager):
        """존재하지 않는 세션 삭제 - False 반환"""
        result = session_manager.delete_session("nonexistent")

        assert result is False

    def test_add_file_to_session(self, session_manager):
        """세션에 파일 추가 - 성공"""
        session_manager.create_session("test-file")

        result = session_manager.add_file_to_session(
            "test-file",
            "test.py",
            "print('hello')"
        )

        assert result is True

        content = session_manager.get_file_from_session("test-file", "test.py")
        assert content == "print('hello')"

    def test_add_file_to_nonexistent_session(self, session_manager):
        """존재하지 않는 세션에 파일 추가 - 실패"""
        result = session_manager.add_file_to_session(
            "nonexistent",
            "test.py",
            "content"
        )

        assert result is False

    def test_get_file_from_session(self, session_manager):
        """세션에서 파일 조회 - 성공"""
        session_manager.create_session("test-file-get")
        session_manager.add_file_to_session("test-file-get", "test.py", "content")

        content = session_manager.get_file_from_session("test-file-get", "test.py")

        assert content == "content"

    def test_get_file_from_nonexistent_session(self, session_manager):
        """존재하지 않는 세션에서 파일 조회 - None 반환"""
        content = session_manager.get_file_from_session("nonexistent", "test.py")

        assert content is None

    def test_cleanup_expired_sessions(self, session_manager):
        """만료된 세션 정리 - 성공"""
        # 세션 3개 생성
        session_manager.create_session("session-1")
        session_manager.create_session("session-2")
        session_manager.create_session("session-3")

        # 짧은 시간 대기
        time.sleep(0.1)

        # 타임아웃 0분으로 정리 (모두 만료됨)
        cleaned = session_manager.cleanup_expired_sessions(timeout_minutes=0)

        assert cleaned == 3
        assert len(session_manager.list_sessions()) == 0

    def test_list_sessions(self, session_manager):
        """세션 목록 조회 - 성공"""
        session_manager.create_session("session-1")
        session_manager.create_session("session-2")

        sessions = session_manager.list_sessions()

        assert len(sessions) == 2

    def test_get_stats(self, session_manager):
        """세션 통계 조회 - 성공"""
        session_manager.create_session("session-1")
        session_manager.add_file_to_session("session-1", "file1.py", "content1")
        session_manager.add_file_to_session("session-1", "file2.py", "content2")

        session_manager.create_session("session-2")
        session_manager.add_file_to_session("session-2", "file3.py", "content3")

        stats = session_manager.get_stats()

        assert stats["total_sessions"] == 2
        assert stats["active_sessions"] == 2
        assert stats["total_files"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
