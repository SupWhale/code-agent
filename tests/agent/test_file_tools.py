"""
Tests for File Tools

Tests file manipulation tools:
- ReadFileTool
- EditFileTool
- CreateFileTool
- DeleteFileTool
"""

import pytest
from pathlib import Path
import tempfile
import asyncio

from src.agent.tools.file_tools import (
    ReadFileTool,
    EditFileTool,
    CreateFileTool,
    DeleteFileTool
)
from src.agent.tools.base import ToolExecutionError


@pytest.fixture
def temp_workspace():
    """임시 작업 디렉토리 생성"""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # src 디렉토리 생성
        (workspace / "src").mkdir()

        # 테스트 파일 생성
        test_file = workspace / "src" / "example.py"
        test_file.write_text("def hello():\n    print('Hello, World!')\n")

        yield workspace


class TestReadFileTool:
    """ReadFileTool 테스트"""

    @pytest.mark.asyncio
    async def test_read_existing_file(self, temp_workspace):
        """존재하는 파일 읽기 - 성공"""
        tool = ReadFileTool(str(temp_workspace))

        content = await tool.execute({"path": "src/example.py"})

        assert "def hello():" in content
        assert "Hello, World!" in content

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, temp_workspace):
        """존재하지 않는 파일 읽기 - 실패"""
        tool = ReadFileTool(str(temp_workspace))

        with pytest.raises(FileNotFoundError):
            await tool.execute({"path": "src/nonexistent.py"})

    @pytest.mark.asyncio
    async def test_read_directory_fails(self, temp_workspace):
        """디렉토리 읽기 - 실패"""
        tool = ReadFileTool(str(temp_workspace))

        with pytest.raises(ValueError, match="Not a file"):
            await tool.execute({"path": "src"})

    @pytest.mark.asyncio
    async def test_read_missing_path_param(self, temp_workspace):
        """path 파라미터 누락 - 실패"""
        tool = ReadFileTool(str(temp_workspace))

        with pytest.raises(ValueError, match="Missing required parameters"):
            await tool.execute({})


class TestEditFileTool:
    """EditFileTool 테스트"""

    @pytest.mark.asyncio
    async def test_edit_file_simple(self, temp_workspace):
        """간단한 파일 수정 - 성공"""
        tool = EditFileTool(str(temp_workspace))

        result = await tool.execute({
            "path": "src/example.py",
            "old_string": "def hello():",
            "new_string": "def hello() -> None:"
        })

        assert result["success"] is True
        assert result["changes"] == 1
        assert "backup" in result

        # 파일 내용 확인
        file_path = temp_workspace / "src" / "example.py"
        content = file_path.read_text()
        assert "def hello() -> None:" in content

    @pytest.mark.asyncio
    async def test_edit_file_with_whitespace(self, temp_workspace):
        """공백/들여쓰기 포함 수정 - 성공"""
        tool = EditFileTool(str(temp_workspace))

        result = await tool.execute({
            "path": "src/example.py",
            "old_string": "    print('Hello, World!')",
            "new_string": "    print('Hello, Agent!')"
        })

        assert result["success"] is True

        # 파일 내용 확인
        file_path = temp_workspace / "src" / "example.py"
        content = file_path.read_text()
        assert "Hello, Agent!" in content

    @pytest.mark.asyncio
    async def test_edit_file_string_not_found(self, temp_workspace):
        """존재하지 않는 문자열 수정 - 실패"""
        tool = EditFileTool(str(temp_workspace))

        with pytest.raises(ValueError, match="String not found"):
            await tool.execute({
                "path": "src/example.py",
                "old_string": "def goodbye():",
                "new_string": "def goodbye() -> None:"
            })

    @pytest.mark.asyncio
    async def test_edit_file_duplicate_string(self, temp_workspace):
        """중복 문자열 수정 - 실패"""
        # 중복 문자열이 있는 파일 생성
        file_path = temp_workspace / "src" / "duplicate.py"
        file_path.write_text("def func1():\n    pass\n\ndef func2():\n    pass\n")

        tool = EditFileTool(str(temp_workspace))

        with pytest.raises(ValueError, match="appears 2 times"):
            await tool.execute({
                "path": "src/duplicate.py",
                "old_string": "    pass",
                "new_string": "    return None"
            })

    @pytest.mark.asyncio
    async def test_edit_file_same_strings(self, temp_workspace):
        """old_string과 new_string이 동일 - 실패"""
        tool = EditFileTool(str(temp_workspace))

        with pytest.raises(ValueError, match="identical"):
            await tool.execute({
                "path": "src/example.py",
                "old_string": "def hello():",
                "new_string": "def hello():"
            })

    @pytest.mark.asyncio
    async def test_edit_creates_backup(self, temp_workspace):
        """백업 파일 생성 확인"""
        tool = EditFileTool(str(temp_workspace))

        result = await tool.execute({
            "path": "src/example.py",
            "old_string": "Hello, World!",
            "new_string": "Hello, Backup!"
        })

        backup_path = Path(result["backup"])
        assert backup_path.exists()

        # 백업 파일에 원본 내용 확인
        backup_content = backup_path.read_text()
        assert "Hello, World!" in backup_content


class TestCreateFileTool:
    """CreateFileTool 테스트"""

    @pytest.mark.asyncio
    async def test_create_new_file(self, temp_workspace):
        """새 파일 생성 - 성공"""
        tool = CreateFileTool(str(temp_workspace))

        result = await tool.execute({
            "path": "src/new_file.py",
            "content": "# New file\nprint('Hello')\n"
        })

        assert result["success"] is True
        assert result["size"] > 0

        # 파일 존재 확인
        file_path = temp_workspace / "src" / "new_file.py"
        assert file_path.exists()
        assert "New file" in file_path.read_text()

    @pytest.mark.asyncio
    async def test_create_file_with_nested_dir(self, temp_workspace):
        """중첩 디렉토리에 파일 생성 - 성공"""
        tool = CreateFileTool(str(temp_workspace))

        result = await tool.execute({
            "path": "src/api/user.py",
            "content": "def get_user():\n    pass\n"
        })

        assert result["success"] is True

        # 디렉토리와 파일 모두 생성되었는지 확인
        file_path = temp_workspace / "src" / "api" / "user.py"
        assert file_path.exists()
        assert file_path.parent.is_dir()

    @pytest.mark.asyncio
    async def test_create_existing_file_fails(self, temp_workspace):
        """이미 존재하는 파일 생성 - 실패"""
        tool = CreateFileTool(str(temp_workspace))

        with pytest.raises(FileExistsError):
            await tool.execute({
                "path": "src/example.py",
                "content": "# This should fail"
            })


class TestDeleteFileTool:
    """DeleteFileTool 테스트"""

    @pytest.mark.asyncio
    async def test_delete_file_with_confirm(self, temp_workspace):
        """confirm=True로 파일 삭제 - 성공"""
        tool = DeleteFileTool(str(temp_workspace))

        result = await tool.execute({
            "path": "src/example.py",
            "confirm": True
        })

        assert result["success"] is True
        assert "backup" in result

        # 원본 파일 삭제 확인
        file_path = temp_workspace / "src" / "example.py"
        assert not file_path.exists()

        # 백업 파일 존재 확인
        backup_path = Path(result["backup"])
        assert backup_path.exists()

    @pytest.mark.asyncio
    async def test_delete_without_confirm_fails(self, temp_workspace):
        """confirm 없이 삭제 - 실패"""
        tool = DeleteFileTool(str(temp_workspace))

        with pytest.raises(ValueError, match="confirm=true"):
            await tool.execute({
                "path": "src/example.py",
                "confirm": False
            })

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file(self, temp_workspace):
        """존재하지 않는 파일 삭제 - 실패"""
        tool = DeleteFileTool(str(temp_workspace))

        with pytest.raises(FileNotFoundError):
            await tool.execute({
                "path": "src/nonexistent.py",
                "confirm": True
            })

    @pytest.mark.asyncio
    async def test_delete_backup_preserves_content(self, temp_workspace):
        """백업 파일에 원본 내용 보존 확인"""
        # 원본 내용 읽기
        original_content = (temp_workspace / "src" / "example.py").read_text()

        tool = DeleteFileTool(str(temp_workspace))

        result = await tool.execute({
            "path": "src/example.py",
            "confirm": True
        })

        # 백업 파일 내용 확인
        backup_path = Path(result["backup"])
        backup_content = backup_path.read_text()

        assert backup_content == original_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
