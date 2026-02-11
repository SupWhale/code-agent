"""
Tool Executor

Manages and executes all available tools for the agent.
"""

from typing import Dict, Any
import logging

from .tools.base import BaseTool
from .tools.file_tools import ReadFileTool, EditFileTool, CreateFileTool, DeleteFileTool
from .tools.search_tools import ListFilesTool, SearchCodeTool
from .tools.test_tools import RunTestsTool, RunCommandTool
from .tools.interaction_tools import FinishTool, AskUserTool, ReportErrorTool

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    도구 실행 엔진

    모든 도구를 등록하고 실행을 관리합니다.
    """

    def __init__(self, workspace_path: str):
        """
        Args:
            workspace_path: 작업 디렉토리 절대 경로
        """
        self.workspace_path = workspace_path

        # 도구 등록
        self.tools: Dict[str, BaseTool] = {
            # 파일 도구
            "read_file": ReadFileTool(workspace_path),
            "edit_file": EditFileTool(workspace_path),
            "create_file": CreateFileTool(workspace_path),
            "delete_file": DeleteFileTool(workspace_path),

            # 검색 도구
            "list_files": ListFilesTool(workspace_path),
            "search_code": SearchCodeTool(workspace_path),

            # 테스트 도구
            "run_tests": RunTestsTool(workspace_path),
            "run_command": RunCommandTool(workspace_path),

            # 상호작용 도구
            "finish": FinishTool(),
            "ask_user": AskUserTool(),
            "report_error": ReportErrorTool()
        }

        logger.info(f"ToolExecutor initialized with {len(self.tools)} tools")

    async def execute(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """
        도구 실행

        Args:
            tool_name: 도구 이름
            params: 파라미터 딕셔너리

        Returns:
            도구 실행 결과

        Raises:
            ValueError: 도구를 찾을 수 없음
            Exception: 도구 실행 실패
        """
        if tool_name not in self.tools:
            available_tools = ", ".join(self.tools.keys())
            raise ValueError(
                f"Unknown tool: '{tool_name}'. "
                f"Available tools: {available_tools}"
            )

        tool = self.tools[tool_name]

        logger.info(f"Executing tool: {tool_name}")
        logger.debug(f"Tool params: {params}")

        try:
            result = await tool.execute(params)
            logger.info(f"Tool '{tool_name}' executed successfully")
            return result

        except Exception as e:
            logger.error(f"Tool '{tool_name}' execution failed: {e}")
            raise

    def get_available_tools(self) -> list:
        """사용 가능한 도구 목록 반환"""
        return list(self.tools.keys())

    def has_tool(self, tool_name: str) -> bool:
        """도구 존재 여부 확인"""
        return tool_name in self.tools

    def __repr__(self) -> str:
        return f"<ToolExecutor tools={len(self.tools)}>"
