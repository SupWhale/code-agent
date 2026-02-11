"""
Tests for Interaction Tools

Tests tools for agent-user interaction: finish, ask_user, report_error.
"""

import pytest
from src.agent.tools.interaction_tools import FinishTool, AskUserTool, ReportErrorTool


class TestFinishTool:
    """FinishTool 테스트"""

    @pytest.mark.asyncio
    async def test_finish_success(self):
        """작업 성공 완료 - 성공"""
        tool = FinishTool()

        result = await tool.execute({
            "success": True,
            "message": "Task completed successfully"
        })

        assert result["finished"] is True
        assert result["success"] is True
        assert result["message"] == "Task completed successfully"

    @pytest.mark.asyncio
    async def test_finish_failure(self):
        """작업 실패 완료 - 성공"""
        tool = FinishTool()

        result = await tool.execute({
            "success": False,
            "message": "Task failed"
        })

        assert result["finished"] is True
        assert result["success"] is False
        assert result["message"] == "Task failed"

    @pytest.mark.asyncio
    async def test_finish_with_result(self):
        """결과 데이터 포함 완료 - 성공"""
        tool = FinishTool()

        result = await tool.execute({
            "success": True,
            "message": "Done",
            "result": {"files_modified": 3, "tests_passed": True}
        })

        assert result["finished"] is True
        assert result["result"]["files_modified"] == 3
        assert result["result"]["tests_passed"] is True

    @pytest.mark.asyncio
    async def test_finish_default_values(self):
        """기본값으로 완료 - 성공"""
        tool = FinishTool()

        result = await tool.execute({})

        assert result["finished"] is True
        assert result["success"] is True  # 기본값
        assert result["message"] == "Task completed"  # 기본값


class TestAskUserTool:
    """AskUserTool 테스트"""

    @pytest.mark.asyncio
    async def test_ask_simple_question(self):
        """간단한 질문 - 성공"""
        tool = AskUserTool()

        result = await tool.execute({
            "question": "Should I proceed with the changes?"
        })

        assert result["asked"] is True
        assert result["question"] == "Should I proceed with the changes?"
        assert result["awaiting_response"] is True

    @pytest.mark.asyncio
    async def test_ask_with_options(self):
        """선택지 포함 질문 - 성공"""
        tool = AskUserTool()

        result = await tool.execute({
            "question": "Which approach should I use?",
            "options": ["Approach A", "Approach B", "Approach C"]
        })

        assert result["asked"] is True
        assert result["options"] == ["Approach A", "Approach B", "Approach C"]

    @pytest.mark.asyncio
    async def test_ask_with_default(self):
        """기본값 포함 질문 - 성공"""
        tool = AskUserTool()

        result = await tool.execute({
            "question": "Use default settings?",
            "default": "yes"
        })

        assert result["asked"] is True
        assert result["default"] == "yes"

    @pytest.mark.asyncio
    async def test_ask_missing_question(self):
        """질문 누락 - 실패"""
        tool = AskUserTool()

        with pytest.raises(ValueError, match="Missing required parameters"):
            await tool.execute({})


class TestReportErrorTool:
    """ReportErrorTool 테스트"""

    @pytest.mark.asyncio
    async def test_report_simple_error(self):
        """간단한 에러 보고 - 성공"""
        tool = ReportErrorTool()

        result = await tool.execute({
            "error": "File not found"
        })

        assert result["error_reported"] is True
        assert result["error"] == "File not found"

    @pytest.mark.asyncio
    async def test_report_error_with_details(self):
        """상세 정보 포함 에러 보고 - 성공"""
        tool = ReportErrorTool()

        result = await tool.execute({
            "error": "Import failed",
            "details": "Module 'xyz' not found in sys.path"
        })

        assert result["error_reported"] is True
        assert result["error"] == "Import failed"
        assert result["details"] == "Module 'xyz' not found in sys.path"

    @pytest.mark.asyncio
    async def test_report_recoverable_error(self):
        """복구 가능 에러 보고 - 성공"""
        tool = ReportErrorTool()

        result = await tool.execute({
            "error": "Network timeout",
            "recoverable": True
        })

        assert result["error_reported"] is True
        assert result["recoverable"] is True

    @pytest.mark.asyncio
    async def test_report_error_missing_param(self):
        """에러 메시지 누락 - 실패"""
        tool = ReportErrorTool()

        with pytest.raises(ValueError, match="Missing required parameters"):
            await tool.execute({})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
