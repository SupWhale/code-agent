"""SessionManager 단위 테스트"""

from datetime import datetime, timedelta

import pytest

from src.agent.session_manager import SessionManager


@pytest.fixture
def manager(tmp_path):
    return SessionManager(base_workspace_path=str(tmp_path / "sessions"))


def test_create_session_generates_id_and_workspace(manager):
    session = manager.create_session()
    assert session.session_id
    assert session.workspace_path.is_dir()


def test_create_duplicate_session_raises(manager):
    manager.create_session("s1")
    with pytest.raises(ValueError):
        manager.create_session("s1")


def test_get_missing_session_returns_none(manager):
    assert manager.get_session("nope") is None


def test_add_and_get_file(manager):
    manager.create_session("s1")
    assert manager.add_file_to_session("s1", "src/a.py", "print(1)") is True
    assert manager.get_file_from_session("s1", "src/a.py") == "print(1)"
    # 디스크에도 기록되어야 함
    session = manager.get_session("s1")
    assert (session.workspace_path / "src" / "a.py").read_text(encoding="utf-8") == "print(1)"


def test_session_restored_from_disk(manager):
    """다른 워커가 만든 세션(메모리에 없음)을 디스크에서 복원"""
    session = manager.create_session("s1")
    manager.add_file_to_session("s1", "a.py", "x = 1")

    # 메모리에서만 제거 (디스크 workspace는 유지)
    del manager.sessions["s1"]

    restored = manager.get_session("s1")
    assert restored is not None
    assert restored.get_file("a.py") == "x = 1"


def test_delete_session(manager):
    session = manager.create_session("s1")
    workspace = session.workspace_path
    assert manager.delete_session("s1") is True
    assert not workspace.exists()
    assert manager.get_session("s1") is None


def test_delete_disk_only_session(manager):
    """메모리에 없는(디스크에만 있는) 세션도 삭제되어야 함"""
    session = manager.create_session("s1")
    workspace = session.workspace_path
    del manager.sessions["s1"]

    assert manager.delete_session("s1") is True
    assert not workspace.exists()


def test_delete_missing_session_returns_false(manager):
    assert manager.delete_session("nope") is False


def test_cleanup_expired_sessions(manager):
    session = manager.create_session("old")
    manager.create_session("fresh")
    session.last_activity = datetime.now() - timedelta(hours=1)

    deleted = manager.cleanup_expired_sessions(timeout_minutes=30)

    assert deleted == 1
    assert "old" not in manager.sessions
    assert "fresh" in manager.sessions


def test_list_sessions_includes_disk_sessions(manager):
    manager.create_session("s1")
    manager.create_session("s2")
    del manager.sessions["s2"]

    sessions = manager.list_sessions()
    ids = {s.session_id for s in sessions}
    assert ids == {"s1", "s2"}
