"""
MCP Server for Code Agent

기존 에이전트 도구들을 Model Context Protocol(MCP)로 노출합니다.
stdio 전송 방식을 사용하므로 Claude Code / Claude Desktop에서 직접 연결 가능합니다.

실행 방법:
    WORKSPACE_PATH=/path/to/workspace python -m src.mcp_server
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from .agent.tools.file_tools import ReadFileTool, EditFileTool, CreateFileTool, DeleteFileTool
from .agent.tools.search_tools import ListFilesTool, SearchCodeTool
from .agent.tools.test_tools import RunTestsTool, RunCommandTool
from .agent.tools.interaction_tools import FinishTool, AskUserTool, ReportErrorTool

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

WORKSPACE_PATH = os.getenv("WORKSPACE_PATH", str(Path.cwd()))

server = Server("code-agent")

_tools = {
    "read_file": ReadFileTool(WORKSPACE_PATH),
    "edit_file": EditFileTool(WORKSPACE_PATH),
    "create_file": CreateFileTool(WORKSPACE_PATH),
    "delete_file": DeleteFileTool(WORKSPACE_PATH),
    "list_files": ListFilesTool(WORKSPACE_PATH),
    "search_code": SearchCodeTool(WORKSPACE_PATH),
    "run_tests": RunTestsTool(WORKSPACE_PATH),
    "run_command": RunCommandTool(WORKSPACE_PATH),
    "finish": FinishTool(),
    "ask_user": AskUserTool(),
    "report_error": ReportErrorTool(),
}

_TOOL_DEFINITIONS = [
    types.Tool(
        name="read_file",
        description="파일 내용을 읽어 반환합니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "읽을 파일 경로 (워크스페이스 기준 상대경로)"}
            },
            "required": ["path"]
        }
    ),
    types.Tool(
        name="edit_file",
        description="파일의 특정 문자열을 new_string으로 치환합니다. old_string은 파일 내에서 유일해야 합니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "수정할 파일 경로"},
                "old_string": {"type": "string", "description": "기존 문자열 (공백·들여쓰기 포함 정확히 일치)"},
                "new_string": {"type": "string", "description": "새 문자열"}
            },
            "required": ["path", "old_string", "new_string"]
        }
    ),
    types.Tool(
        name="create_file",
        description="새 파일을 생성합니다. 파일이 이미 존재하면 에러가 발생합니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "생성할 파일 경로"},
                "content": {"type": "string", "description": "파일 내용"}
            },
            "required": ["path", "content"]
        }
    ),
    types.Tool(
        name="delete_file",
        description="파일을 삭제합니다. 실제로는 .deleted 확장자로 백업 후 이동합니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "삭제할 파일 경로"},
                "confirm": {"type": "boolean", "description": "삭제 확인 플래그 (반드시 true)"}
            },
            "required": ["path", "confirm"]
        }
    ),
    types.Tool(
        name="list_files",
        description="디렉토리의 파일 및 하위 디렉토리 목록을 반환합니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "조회할 디렉토리 경로 (기본값: .)"},
                "pattern": {"type": "string", "description": "파일 패턴 (예: *.py)"},
                "recursive": {"type": "boolean", "description": "재귀 탐색 여부 (기본값: false)"}
            }
        }
    ),
    types.Tool(
        name="search_code",
        description="파일 내용에서 패턴을 검색합니다 (grep 유사). 최대 100개 결과를 반환합니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "검색 패턴"},
                "path": {"type": "string", "description": "검색 경로 (기본값: .)"},
                "regex": {"type": "boolean", "description": "정규식 사용 여부 (기본값: false)"},
                "file_pattern": {"type": "string", "description": "검색 대상 파일 패턴 (예: *.py)"},
                "ignore_case": {"type": "boolean", "description": "대소문자 무시 여부 (기본값: false)"}
            },
            "required": ["pattern"]
        }
    ),
    types.Tool(
        name="run_tests",
        description="pytest를 사용하여 테스트를 실행합니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["all", "directory", "file", "filter"],
                    "description": "테스트 범위 (기본값: all)"
                },
                "path": {"type": "string", "description": "테스트 경로 (scope=directory 또는 file일 때 필수)"},
                "filter": {"type": "string", "description": "테스트 필터 키워드 (scope=filter일 때 필수, pytest -k)"},
                "timeout": {"type": "integer", "description": "타임아웃(초) (기본값: 60)"}
            }
        }
    ),
    types.Tool(
        name="run_command",
        description="셸 명령을 실행합니다. SecurityValidator의 화이트리스트 제한을 받습니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "실행할 명령어"},
                "timeout": {"type": "integer", "description": "타임아웃(초) (기본값: 30)"}
            },
            "required": ["command"]
        }
    ),
    types.Tool(
        name="finish",
        description="에이전트 작업 완료를 표시합니다. 모든 작업이 끝났을 때 호출합니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "success": {"type": "boolean", "description": "작업 성공 여부 (기본값: true)"},
                "message": {"type": "string", "description": "완료 메시지"},
                "result": {"type": "object", "description": "추가 결과 데이터"}
            }
        }
    ),
    types.Tool(
        name="ask_user",
        description="사용자에게 질문하거나 추가 입력을 요청합니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "질문 내용"},
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "선택지 목록 (선택사항)"
                },
                "default": {"type": "string", "description": "기본값 (선택사항)"}
            },
            "required": ["question"]
        }
    ),
    types.Tool(
        name="report_error",
        description="에이전트가 처리할 수 없는 치명적 에러를 보고합니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "error": {"type": "string", "description": "에러 메시지"},
                "details": {"type": "string", "description": "상세 정보 (선택사항)"},
                "recoverable": {"type": "boolean", "description": "복구 가능 여부 (기본값: false)"}
            },
            "required": ["error"]
        }
    ),
]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return _TOOL_DEFINITIONS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    if name not in _tools:
        raise ValueError(f"Unknown tool: '{name}'. Available: {', '.join(_tools)}")

    try:
        result = await _tools[name].execute(arguments)
        text = (
            result
            if isinstance(result, str)
            else json.dumps(result, ensure_ascii=False, indent=2)
        )
        return [types.TextContent(type="text", text=text)]
    except Exception as e:
        logger.error(f"Tool '{name}' failed: {e}")
        return [types.TextContent(type="text", text=f"Error: {e}")]


async def main():
    logger.info(f"Starting MCP server (workspace: {WORKSPACE_PATH})")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
