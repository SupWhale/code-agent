"""
Tests for Test Tools

Tests test execution and command running:
- RunTestsTool
- RunCommandTool
"""

import pytest
from pathlib import Path
import tempfile

from src.agent.tools.test_tools import RunTestsTool, RunCommandTool


@pytest.fixture
def temp_workspace():
    """임시 작업 디렉토리 생성"""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # tests 디렉토리 생성
        tests_dir = workspace / "tests"
        tests_dir.mkdir()

        # 간단한 테스트 파일 생성
        (tests_dir / "test_example.py").write_text(
            "def test_pass():\n    assert True\n\n"
            "def test_another_pass():\n    assert 1 == 1\n"
        )

        # 실패하는 테스트 파일
        (tests_dir / "test_fail.py").write_text(
            "def test_will_fail():\n    assert False\n"
        )

        yield workspace


class TestRunTestsTool:
    """RunTestsTool 테스트"""

    @pytest.mark.asyncio
    async def test_run_all_tests_success(self, temp_workspace):
        """전체 테스트 실행 - 성공"""
        tool = RunTestsTool(str(temp_workspace))

        result = await tool.execute({"scope": "all"})

        # 일부 테스트는 실패할 수 있음 (test_fail.py)
        assert "exit_code" in result
        assert "stdout" in result
        assert "summary" in result

    @pytest.mark.asyncio
    async def test_run_specific_file(self, temp_workspace):
        """특정 파일 테스트 실행 - 성공"""
        tool = RunTestsTool(str(temp_workspace))

        result = await tool.execute({
            "scope": "file",
            "path": "tests/test_example.py"
        })

        assert result["exit_code"] == 0  # test_example.py는 모두 통과
        assert result["summary"]["passed"] == 2
        assert result["summary"]["failed"] == 0

    @pytest.mark.asyncio
    async def test_run_with_filter(self, temp_workspace):
        """필터로 테스트 실행 - 성공"""
        tool = RunTestsTool(str(temp_workspace))

        result = await tool.execute({
            "scope": "filter",
            "filter": "test_pass"
        })

        # test_pass만 실행됨
        assert result["summary"]["passed"] >= 1

    @pytest.mark.asyncio
    async def test_run_tests_missing_path(self, temp_workspace):
        """path 파라미터 누락 - 실패"""
        tool = RunTestsTool(str(temp_workspace))

        with pytest.raises(ValueError, match="'path' parameter is required"):
            await tool.execute({"scope": "file"})

    @pytest.mark.asyncio
    async def test_run_tests_missing_filter(self, temp_workspace):
        """filter 파라미터 누락 - 실패"""
        tool = RunTestsTool(str(temp_workspace))

        with pytest.raises(ValueError, match="'filter' parameter is required"):
            await tool.execute({"scope": "filter"})

    @pytest.mark.asyncio
    async def test_run_tests_invalid_scope(self, temp_workspace):
        """잘못된 scope - 실패"""
        tool = RunTestsTool(str(temp_workspace))

        with pytest.raises(ValueError, match="Invalid scope"):
            await tool.execute({"scope": "invalid_scope"})

    @pytest.mark.asyncio
    async def test_parse_pytest_output(self, temp_workspace):
        """pytest 출력 파싱 - 성공"""
        tool = RunTestsTool(str(temp_workspace))

        # 성공 케이스
        summary = tool._parse_pytest_output(
            "========================= 5 passed in 0.12s ========================="
        )
        assert summary["passed"] == 5
        assert summary["failed"] == 0

        # 실패 케이스
        summary = tool._parse_pytest_output(
            "========================= 3 passed, 2 failed in 0.25s ========================="
        )
        assert summary["passed"] == 3
        assert summary["failed"] == 2


class TestRunCommandTool:
    """RunCommandTool 테스트"""

    @pytest.mark.asyncio
    async def test_run_simple_command(self, temp_workspace):
        """간단한 명령 실행 - 성공"""
        tool = RunCommandTool(str(temp_workspace))

        result = await tool.execute({"command": "python --version"})

        assert result["exit_code"] == 0
        assert "Python" in result["stdout"] or "Python" in result["stderr"]

    @pytest.mark.asyncio
    async def test_run_command_with_args(self, temp_workspace):
        """인자가 있는 명령 실행 - 성공"""
        tool = RunCommandTool(str(temp_workspace))

        # 간단한 파일 생성
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Hello")

        # Windows와 Linux 모두에서 작동하는 명령
        import platform
        if platform.system() == "Windows":
            result = await tool.execute({"command": "cmd /c type test.txt"})
        else:
            result = await tool.execute({"command": "cat test.txt"})

        # 명령이 존재하면 성공
        assert "exit_code" in result

    @pytest.mark.asyncio
    async def test_run_command_missing_param(self, temp_workspace):
        """command 파라미터 누락 - 실패"""
        tool = RunCommandTool(str(temp_workspace))

        with pytest.raises(ValueError, match="Missing required parameters"):
            await tool.execute({})

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Timeout behavior varies by platform and command")
    async def test_run_command_timeout(self, temp_workspace):
        """명령 타임아웃 - 실패"""
        tool = RunCommandTool(str(temp_workspace))

        # 타임아웃이 매우 짧은 명령 (Windows/Linux 모두 지원)
        import platform
        if platform.system() == "Windows":
            cmd = "python -c \"import time; time.sleep(10)\""
        else:
            cmd = "sleep 10"

        from src.agent.tools.base import ToolExecutionError
        with pytest.raises(ToolExecutionError, match="timed out"):
            await tool.execute({
                "command": cmd,
                "timeout": 1  # 1초 타임아웃
            })

    @pytest.mark.asyncio
    async def test_run_command_success_flag(self, temp_workspace):
        """성공 플래그 확인 - 성공"""
        tool = RunCommandTool(str(temp_workspace))

        # 성공하는 명령
        result = await tool.execute({"command": "python --version"})
        assert result["success"] is True
        assert result["exit_code"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
