"""
Tests for Search Tools

Tests search capabilities:
- ListFilesTool
- SearchCodeTool
"""

import pytest
from pathlib import Path
import tempfile

from src.agent.tools.search_tools import ListFilesTool, SearchCodeTool


@pytest.fixture
def temp_workspace():
    """임시 작업 디렉토리 생성"""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # 디렉토리 구조 생성
        (workspace / "src").mkdir()
        (workspace / "src" / "api").mkdir()
        (workspace / "tests").mkdir()

        # 파일 생성
        (workspace / "src" / "main.py").write_text(
            "def main():\n    print('Hello')\n\nif __name__ == '__main__':\n    main()\n"
        )
        (workspace / "src" / "api" / "user.py").write_text(
            "def get_user(id):\n    return User.find(id)\n"
        )
        (workspace / "tests" / "test_main.py").write_text(
            "def test_main():\n    assert True\n"
        )
        (workspace / "README.md").write_text("# Project\n\nThis is a test project.\n")

        yield workspace


class TestListFilesTool:
    """ListFilesTool 테스트"""

    @pytest.mark.asyncio
    async def test_list_files_in_directory(self, temp_workspace):
        """디렉토리의 파일 목록 - 성공"""
        tool = ListFilesTool(str(temp_workspace))

        result = await tool.execute({"path": "src"})

        assert len(result) == 2  # main.py, api/
        names = [f["name"] for f in result]
        assert "main.py" in names
        assert "api" in names

    @pytest.mark.asyncio
    async def test_list_files_recursive(self, temp_workspace):
        """재귀적 파일 목록 - 성공"""
        tool = ListFilesTool(str(temp_workspace))

        result = await tool.execute({
            "path": "src",
            "recursive": True
        })

        assert len(result) >= 3  # main.py, api/, api/user.py
        paths = [f["path"] for f in result]
        assert any("user.py" in p for p in paths)

    @pytest.mark.asyncio
    async def test_list_files_with_pattern(self, temp_workspace):
        """패턴으로 파일 필터링 - 성공"""
        tool = ListFilesTool(str(temp_workspace))

        result = await tool.execute({
            "path": ".",
            "pattern": "*.py",
            "recursive": True
        })

        # .py 파일만
        for item in result:
            assert item["name"].endswith(".py")

    @pytest.mark.asyncio
    async def test_list_files_default_path(self, temp_workspace):
        """path 기본값 (현재 디렉토리) - 성공"""
        tool = ListFilesTool(str(temp_workspace))

        result = await tool.execute({})

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_list_files_nonexistent_dir(self, temp_workspace):
        """존재하지 않는 디렉토리 - 실패"""
        tool = ListFilesTool(str(temp_workspace))

        with pytest.raises(FileNotFoundError):
            await tool.execute({"path": "nonexistent"})

    @pytest.mark.asyncio
    async def test_list_files_type_distinction(self, temp_workspace):
        """파일과 디렉토리 구분 - 성공"""
        tool = ListFilesTool(str(temp_workspace))

        result = await tool.execute({"path": "."})

        # 타입 확인
        types = {f["type"] for f in result}
        assert "file" in types
        assert "directory" in types

        # 파일은 size가 있고, 디렉토리는 없음
        for item in result:
            if item["type"] == "file":
                assert "size" in item
                assert item["size"] >= 0


class TestSearchCodeTool:
    """SearchCodeTool 테스트"""

    @pytest.mark.asyncio
    async def test_search_simple_string(self, temp_workspace):
        """단순 문자열 검색 - 성공"""
        tool = SearchCodeTool(str(temp_workspace))

        result = await tool.execute({
            "pattern": "def main",
            "path": "src"
        })

        assert len(result) == 1
        assert result[0]["match"] == "def main"
        assert "main.py" in result[0]["file"]
        assert result[0]["line"] == 1

    @pytest.mark.asyncio
    async def test_search_regex(self, temp_workspace):
        """정규식 검색 - 성공"""
        tool = SearchCodeTool(str(temp_workspace))

        result = await tool.execute({
            "pattern": r"def \w+\(",
            "path": "src",
            "regex": True
        })

        assert len(result) >= 2  # main(), get_user()
        matches = [r["match"] for r in result]
        assert any("def main(" in m for m in matches)
        assert any("def get_user(" in m for m in matches)

    @pytest.mark.asyncio
    async def test_search_with_file_pattern(self, temp_workspace):
        """파일 패턴으로 제한 - 성공"""
        tool = SearchCodeTool(str(temp_workspace))

        result = await tool.execute({
            "pattern": "def",
            "path": ".",
            "file_pattern": "*.py"
        })

        # .py 파일에서만 검색
        for item in result:
            assert item["file"].endswith(".py")

    @pytest.mark.asyncio
    async def test_search_ignore_case(self, temp_workspace):
        """대소문자 무시 검색 - 성공"""
        tool = SearchCodeTool(str(temp_workspace))

        result = await tool.execute({
            "pattern": "HELLO",
            "path": "src",
            "ignore_case": True
        })

        assert len(result) == 1
        assert "Hello" in result[0]["content"]

    @pytest.mark.asyncio
    async def test_search_no_match(self, temp_workspace):
        """매칭 없음 - 성공 (빈 결과)"""
        tool = SearchCodeTool(str(temp_workspace))

        result = await tool.execute({
            "pattern": "nonexistent_pattern_xyz",
            "path": "src"
        })

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_search_single_file(self, temp_workspace):
        """단일 파일 검색 - 성공"""
        tool = SearchCodeTool(str(temp_workspace))

        result = await tool.execute({
            "pattern": "def",
            "path": "src/main.py"
        })

        assert len(result) == 1
        assert "main.py" in result[0]["file"]

    @pytest.mark.asyncio
    async def test_search_invalid_regex(self, temp_workspace):
        """잘못된 정규식 - 실패"""
        tool = SearchCodeTool(str(temp_workspace))

        with pytest.raises(ValueError, match="Invalid regex"):
            await tool.execute({
                "pattern": "[invalid(regex",
                "path": "src",
                "regex": True
            })

    @pytest.mark.asyncio
    async def test_search_result_limit(self, temp_workspace):
        """결과 개수 제한 (100개) - 성공"""
        # 많은 파일 생성
        for i in range(150):
            (temp_workspace / "src" / f"file{i}.py").write_text("def test(): pass\n")

        tool = SearchCodeTool(str(temp_workspace))

        result = await tool.execute({
            "pattern": "def",
            "path": "src"
        })

        # 최대 100개로 제한됨
        assert len(result) <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
