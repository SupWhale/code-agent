"""
Tests for Sync Tools

VS Code Extension용 동기화 도구 테스트
"""

import pytest
from pathlib import Path
import tempfile

from src.agent.session_manager import SessionManager
from src.agent.tools.sync_tools import (
    SessionReadFileTool,
    SessionWriteFileTool,
    DiffTool,
    SessionListFilesTool
)


@pytest.fixture
def temp_base_workspace():
    """임시 base workspace"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def session_manager(temp_base_workspace):
    """SessionManager 인스턴스"""
    return SessionManager(temp_base_workspace)


@pytest.fixture
def session_with_files(session_manager):
    """파일이 있는 세션"""
    session = session_manager.create_session("test-session")
    session_manager.add_file_to_session("test-session", "test1.py", "print('hello')")
    session_manager.add_file_to_session("test-session", "test2.py", "print('world')")
    return session


class TestSessionReadFileTool:
    """SessionReadFileTool 테스트"""

    @pytest.mark.asyncio
    async def test_read_file_success(self, session_manager, session_with_files):
        """파일 읽기 - 성공"""
        tool = SessionReadFileTool(session_manager)

        content = await tool.execute({
            "session_id": "test-session",
            "path": "test1.py"
        })

        assert content == "print('hello')"

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, session_manager, session_with_files):
        """파일 읽기 - 파일 없음"""
        tool = SessionReadFileTool(session_manager)

        with pytest.raises(ValueError, match="File not found"):
            await tool.execute({
                "session_id": "test-session",
                "path": "nonexistent.py"
            })

    @pytest.mark.asyncio
    async def test_read_file_session_not_found(self, session_manager):
        """파일 읽기 - 세션 없음"""
        tool = SessionReadFileTool(session_manager)

        with pytest.raises(ValueError, match="File not found"):
            await tool.execute({
                "session_id": "nonexistent-session",
                "path": "test.py"
            })

    @pytest.mark.asyncio
    async def test_read_file_missing_params(self, session_manager):
        """파일 읽기 - 파라미터 누락"""
        tool = SessionReadFileTool(session_manager)

        with pytest.raises(ValueError, match="Missing required parameter"):
            await tool.execute({"session_id": "test-session"})


class TestSessionWriteFileTool:
    """SessionWriteFileTool 테스트"""

    @pytest.mark.asyncio
    async def test_write_file_success(self, session_manager, session_with_files):
        """파일 쓰기 - 성공"""
        tool = SessionWriteFileTool(session_manager)

        result = await tool.execute({
            "session_id": "test-session",
            "path": "new_file.py",
            "content": "print('new content')"
        })

        assert result["success"] is True
        assert result["path"] == "new_file.py"
        assert result["size"] == len("print('new content')")

        # 파일 확인
        content = session_manager.get_file_from_session("test-session", "new_file.py")
        assert content == "print('new content')"

    @pytest.mark.asyncio
    async def test_write_file_update_existing(self, session_manager, session_with_files):
        """파일 쓰기 - 기존 파일 업데이트"""
        tool = SessionWriteFileTool(session_manager)

        result = await tool.execute({
            "session_id": "test-session",
            "path": "test1.py",
            "content": "print('updated')"
        })

        assert result["success"] is True

        # 업데이트 확인
        content = session_manager.get_file_from_session("test-session", "test1.py")
        assert content == "print('updated')"

    @pytest.mark.asyncio
    async def test_write_file_session_not_found(self, session_manager):
        """파일 쓰기 - 세션 없음"""
        tool = SessionWriteFileTool(session_manager)

        with pytest.raises(ValueError, match="Failed to write file"):
            await tool.execute({
                "session_id": "nonexistent-session",
                "path": "test.py",
                "content": "content"
            })

    @pytest.mark.asyncio
    async def test_write_file_missing_params(self, session_manager):
        """파일 쓰기 - 파라미터 누락"""
        tool = SessionWriteFileTool(session_manager)

        with pytest.raises(ValueError, match="Missing required parameter"):
            await tool.execute({
                "session_id": "test-session",
                "path": "test.py"
            })


class TestDiffTool:
    """DiffTool 테스트"""

    @pytest.mark.asyncio
    async def test_diff_with_changes(self):
        """Diff 생성 - 변경사항 있음"""
        tool = DiffTool()

        old_content = "line 1\nline 2\nline 3\n"
        new_content = "line 1\nline 2 modified\nline 3\nline 4\n"

        result = await tool.execute({
            "old_content": old_content,
            "new_content": new_content,
            "file_path": "test.py"
        })

        assert result["has_changes"] is True
        assert result["file_path"] == "test.py"
        assert result["added_lines"] == 2  # "line 2 modified", "line 4"
        assert result["removed_lines"] == 1  # "line 2"
        assert "--- a/test.py" in result["diff"]
        assert "+++ b/test.py" in result["diff"]

    @pytest.mark.asyncio
    async def test_diff_no_changes(self):
        """Diff 생성 - 변경사항 없음"""
        tool = DiffTool()

        content = "line 1\nline 2\nline 3\n"

        result = await tool.execute({
            "old_content": content,
            "new_content": content,
            "file_path": "test.py"
        })

        assert result["has_changes"] is False
        assert result["added_lines"] == 0
        assert result["removed_lines"] == 0
        assert result["diff"] == ""

    @pytest.mark.asyncio
    async def test_diff_addition_only(self):
        """Diff 생성 - 추가만"""
        tool = DiffTool()

        old_content = "line 1\n"
        new_content = "line 1\nline 2\nline 3\n"

        result = await tool.execute({
            "old_content": old_content,
            "new_content": new_content,
            "file_path": "test.py"
        })

        assert result["has_changes"] is True
        assert result["added_lines"] == 2
        assert result["removed_lines"] == 0

    @pytest.mark.asyncio
    async def test_diff_deletion_only(self):
        """Diff 생성 - 삭제만"""
        tool = DiffTool()

        old_content = "line 1\nline 2\nline 3\n"
        new_content = "line 1\n"

        result = await tool.execute({
            "old_content": old_content,
            "new_content": new_content,
            "file_path": "test.py"
        })

        assert result["has_changes"] is True
        assert result["added_lines"] == 0
        assert result["removed_lines"] == 2

    @pytest.mark.asyncio
    async def test_diff_default_file_path(self):
        """Diff 생성 - 기본 파일 경로"""
        tool = DiffTool()

        result = await tool.execute({
            "old_content": "old",
            "new_content": "new"
        })

        assert result["file_path"] == "file"  # 기본값
        assert "--- a/file" in result["diff"]

    @pytest.mark.asyncio
    async def test_diff_missing_params(self):
        """Diff 생성 - 파라미터 누락"""
        tool = DiffTool()

        with pytest.raises(ValueError, match="Missing required parameter"):
            await tool.execute({"old_content": "old"})


class TestSessionListFilesTool:
    """SessionListFilesTool 테스트"""

    @pytest.mark.asyncio
    async def test_list_files_success(self, session_manager, session_with_files):
        """파일 목록 조회 - 성공"""
        tool = SessionListFilesTool(session_manager)

        result = await tool.execute({
            "session_id": "test-session"
        })

        assert result["session_id"] == "test-session"
        assert result["count"] == 2
        assert "test1.py" in result["files"]
        assert "test2.py" in result["files"]

    @pytest.mark.asyncio
    async def test_list_files_empty_session(self, session_manager):
        """파일 목록 조회 - 빈 세션"""
        session_manager.create_session("empty-session")
        tool = SessionListFilesTool(session_manager)

        result = await tool.execute({
            "session_id": "empty-session"
        })

        assert result["count"] == 0
        assert result["files"] == []

    @pytest.mark.asyncio
    async def test_list_files_session_not_found(self, session_manager):
        """파일 목록 조회 - 세션 없음"""
        tool = SessionListFilesTool(session_manager)

        with pytest.raises(ValueError, match="Session not found"):
            await tool.execute({
                "session_id": "nonexistent-session"
            })

    @pytest.mark.asyncio
    async def test_list_files_missing_params(self, session_manager):
        """파일 목록 조회 - 파라미터 누락"""
        tool = SessionListFilesTool(session_manager)

        with pytest.raises(ValueError, match="Missing required parameter"):
            await tool.execute({})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
