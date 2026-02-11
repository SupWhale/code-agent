# 코딩 에이전트 구현 설계 문서

## 📁 디렉토리 구조

```
coding-agent-project/
├── src/
│   ├── main.py                      # 기존 FastAPI 앱
│   ├── agent/                       # 🆕 에이전트 모듈
│   │   ├── __init__.py
│   │   ├── orchestrator.py          # 메인 오케스트레이터
│   │   ├── llm/                     # LLM 통합
│   │   │   ├── __init__.py
│   │   │   ├── ollama_client.py     # Ollama 클라이언트
│   │   │   └── prompt_builder.py    # 프롬프트 구성
│   │   ├── tools/                   # 도구 구현
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # 도구 베이스 클래스
│   │   │   ├── file_tools.py        # read_file, edit_file, create_file, delete_file
│   │   │   ├── search_tools.py      # list_files, search_code
│   │   │   ├── test_tools.py        # run_tests, run_command
│   │   │   └── interaction_tools.py # ask_user, finish, report_error
│   │   ├── security/                # 보안
│   │   │   ├── __init__.py
│   │   │   ├── validator.py         # 경로/명령 검증
│   │   │   └── sandbox.py           # 샌드박스 환경 (선택)
│   │   ├── memory/                  # 메모리/상태 관리
│   │   │   ├── __init__.py
│   │   │   ├── conversation.py      # 대화 히스토리
│   │   │   └── task_state.py        # 태스크 상태
│   │   └── executor.py              # 도구 실행 엔진
│   ├── routes/
│   │   ├── __init__.py
│   │   └── agent.py                 # 🆕 에이전트 API 라우트
│   └── models/
│       └── agent.py                 # 🆕 에이전트 데이터 모델
├── tests/
│   └── agent/                       # 🆕 에이전트 테스트
│       ├── test_tools.py
│       ├── test_security.py
│       ├── test_executor.py
│       └── test_integration.py
├── prompts/
│   └── system_prompt.txt            # 시스템 프롬프트 (AGENT_SYSTEM_PROMPT_V2.md 기반)
└── .env
```

---

## 🎯 핵심 컴포넌트 설계

### 1. Agent Orchestrator (오케스트레이터)

**역할**: 전체 에이전트 워크플로우 관리

```python
# src/agent/orchestrator.py

from typing import Dict, List, Optional, AsyncIterator
from dataclasses import dataclass
import asyncio
import logging

from .llm.ollama_client import OllamaAgentClient
from .executor import ToolExecutor
from .memory.conversation import ConversationMemory
from .memory.task_state import TaskState, TaskStatus
from .security.validator import SecurityValidator

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """에이전트 응답"""
    reasoning: Optional[str]
    actions: List[Dict]
    raw_response: str


class AgentOrchestrator:
    """에이전트 메인 오케스트레이터"""

    def __init__(
        self,
        llm_client: OllamaAgentClient,
        executor: ToolExecutor,
        security: SecurityValidator,
        max_iterations: int = 20,  # 무한 루프 방지
        max_failures: int = 3       # 연속 실패 허용 횟수
    ):
        self.llm = llm_client
        self.executor = executor
        self.security = security
        self.max_iterations = max_iterations
        self.max_failures = max_failures

    async def execute_task(
        self,
        task_id: str,
        user_request: str,
        workspace_path: str
    ) -> AsyncIterator[Dict]:
        """
        태스크 실행 (스트리밍)

        Args:
            task_id: 태스크 ID
            user_request: 사용자 요청
            workspace_path: 작업 디렉토리

        Yields:
            상태 업데이트 딕셔너리
        """
        # 초기화
        memory = ConversationMemory(max_history=20)
        state = TaskState(
            task_id=task_id,
            user_request=user_request,
            workspace_path=workspace_path,
            status=TaskStatus.RUNNING
        )

        # 초기 사용자 메시지
        memory.add_user_message(user_request)

        consecutive_failures = 0

        try:
            for iteration in range(self.max_iterations):
                logger.info(f"[Task {task_id}] Iteration {iteration + 1}/{self.max_iterations}")

                # 1. LLM에게 다음 액션 요청
                yield {
                    "type": "iteration_start",
                    "iteration": iteration + 1,
                    "message": "Thinking..."
                }

                agent_response = await self.llm.get_next_actions(
                    conversation_history=memory.get_history(),
                    workspace_path=workspace_path
                )

                # 추론 과정 전송 (디버깅용)
                if agent_response.reasoning:
                    yield {
                        "type": "reasoning",
                        "content": agent_response.reasoning
                    }
                    logger.info(f"[Task {task_id}] Reasoning: {agent_response.reasoning}")

                # 2. 각 액션 실행
                action_results = []

                for action_idx, action in enumerate(agent_response.actions):
                    tool_name = action.get("tool")
                    params = action.get("params", {})

                    logger.info(f"[Task {task_id}] Executing tool: {tool_name}")

                    yield {
                        "type": "action_start",
                        "tool": tool_name,
                        "params": params
                    }

                    try:
                        # 보안 검증
                        self.security.validate_action(tool_name, params, workspace_path)

                        # 도구 실행
                        result = await self.executor.execute(tool_name, params)

                        action_results.append({
                            "tool": tool_name,
                            "success": True,
                            "result": result
                        })

                        # 성공 시 카운터 리셋
                        consecutive_failures = 0

                        yield {
                            "type": "action_success",
                            "tool": tool_name,
                            "result": result
                        }

                        # finish 도구면 종료
                        if tool_name == "finish":
                            state.status = TaskStatus.COMPLETED
                            state.result = result

                            yield {
                                "type": "task_completed",
                                "success": result.get("success", True),
                                "message": result.get("message", "Task completed"),
                                "summary": result.get("summary", {})
                            }

                            return

                    except Exception as e:
                        logger.error(f"[Task {task_id}] Tool execution failed: {e}")

                        action_results.append({
                            "tool": tool_name,
                            "success": False,
                            "error": str(e),
                            "error_type": type(e).__name__
                        })

                        consecutive_failures += 1

                        yield {
                            "type": "action_failed",
                            "tool": tool_name,
                            "error": str(e)
                        }

                        # 연속 실패 체크
                        if consecutive_failures >= self.max_failures:
                            raise RuntimeError(
                                f"Too many consecutive failures ({consecutive_failures}). Aborting."
                            )

                # 3. 결과를 메모리에 추가
                memory.add_assistant_response(agent_response.raw_response)
                memory.add_system_message(
                    f"Tool execution results:\n{self._format_results(action_results)}"
                )

                # 4. 상태 업데이트
                state.iterations.append({
                    "iteration": iteration + 1,
                    "reasoning": agent_response.reasoning,
                    "actions": agent_response.actions,
                    "results": action_results
                })

            # 최대 반복 도달
            raise RuntimeError(f"Max iterations ({self.max_iterations}) reached without completion")

        except Exception as e:
            logger.error(f"[Task {task_id}] Task failed: {e}")

            state.status = TaskStatus.FAILED
            state.error = str(e)

            yield {
                "type": "task_failed",
                "error": str(e)
            }

    def _format_results(self, results: List[Dict]) -> str:
        """도구 실행 결과를 LLM이 이해할 수 있는 형식으로 변환"""
        formatted = []

        for result in results:
            tool = result["tool"]

            if result["success"]:
                formatted.append(f"✅ {tool}: {result['result']}")
            else:
                formatted.append(f"❌ {tool}: {result['error']} ({result['error_type']})")

        return "\n".join(formatted)
```

---

### 2. LLM Client (Ollama 통합)

**역할**: LLM과 통신하여 JSON 액션 생성

```python
# src/agent/llm/ollama_client.py

import json
import re
from typing import List, Dict
import ollama
from pathlib import Path

from ..orchestrator import AgentResponse


class OllamaAgentClient:
    """Ollama를 사용한 에이전트 LLM 클라이언트"""

    def __init__(
        self,
        host: str,
        model: str = "qwen2.5-coder:14b",
        temperature: float = 0.1,
        system_prompt_path: str = "prompts/system_prompt.txt"
    ):
        self.client = ollama.Client(host=host)
        self.model = model
        self.temperature = temperature

        # 시스템 프롬프트 로드
        with open(system_prompt_path, "r", encoding="utf-8") as f:
            self.system_prompt = f.read()

    async def get_next_actions(
        self,
        conversation_history: List[Dict[str, str]],
        workspace_path: str
    ) -> AgentResponse:
        """
        다음 액션 생성

        Args:
            conversation_history: 대화 히스토리 [{"role": "user", "content": "..."}]
            workspace_path: 작업 디렉토리 경로

        Returns:
            AgentResponse (reasoning, actions)
        """
        # 시스템 프롬프트에 workspace 정보 추가
        full_system_prompt = f"{self.system_prompt}\n\n**Current workspace**: {workspace_path}"

        # 메시지 구성
        messages = [
            {"role": "system", "content": full_system_prompt}
        ] + conversation_history

        # Ollama 호출
        response = self.client.chat(
            model=self.model,
            messages=messages,
            options={"temperature": self.temperature},
            stream=False
        )

        raw_response = response["message"]["content"]

        # JSON 파싱
        try:
            parsed = self._parse_json_response(raw_response)

            return AgentResponse(
                reasoning=parsed.get("reasoning"),
                actions=parsed.get("actions", []),
                raw_response=raw_response
            )

        except Exception as e:
            raise ValueError(f"Failed to parse LLM response as JSON: {e}\n\nResponse:\n{raw_response}")

    def _parse_json_response(self, response: str) -> Dict:
        """
        LLM 응답에서 JSON 추출

        LLM은 종종 ```json ... ``` 같은 코드 블록으로 감싸므로 제거
        """
        # 코드 블록 제거
        cleaned = re.sub(r'```json\s*', '', response)
        cleaned = re.sub(r'```\s*', '', cleaned)
        cleaned = cleaned.strip()

        # JSON 파싱 시도
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # {} 패턴 찾기 시도
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise
```

---

### 3. Tool Executor (도구 실행 엔진)

**역할**: 각 도구를 실행하고 결과 반환

```python
# src/agent/executor.py

from typing import Dict, Any
from .tools.base import BaseTool
from .tools.file_tools import ReadFileTool, EditFileTool, CreateFileTool, DeleteFileTool
from .tools.search_tools import ListFilesTool, SearchCodeTool
from .tools.test_tools import RunTestsTool, RunCommandTool
from .tools.interaction_tools import AskUserTool, FinishTool, ReportErrorTool


class ToolExecutor:
    """도구 실행 엔진"""

    def __init__(self, workspace_path: str):
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
            "ask_user": AskUserTool(),
            "finish": FinishTool(),
            "report_error": ReportErrorTool()
        }

    async def execute(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """
        도구 실행

        Args:
            tool_name: 도구 이름
            params: 파라미터

        Returns:
            도구 실행 결과

        Raises:
            ValueError: 도구가 없는 경우
        """
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")

        tool = self.tools[tool_name]

        return await tool.execute(params)
```

---

### 4. Tool Base Class (도구 베이스)

**역할**: 모든 도구의 인터페이스 정의

```python
# src/agent/tools/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any
from pathlib import Path


class BaseTool(ABC):
    """도구 베이스 클래스"""

    def __init__(self, workspace_path: str = None):
        self.workspace_path = Path(workspace_path) if workspace_path else None

    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> Any:
        """
        도구 실행

        Args:
            params: 파라미터 딕셔너리

        Returns:
            도구 실행 결과

        Raises:
            도구별 예외
        """
        pass

    def _resolve_path(self, path: str) -> Path:
        """
        경로 해석 (workspace 기준)

        Args:
            path: 상대/절대 경로

        Returns:
            절대 경로
        """
        p = Path(path)

        if p.is_absolute():
            return p
        else:
            return (self.workspace_path / path).resolve()
```

---

### 5. File Tools 구현 예시

**역할**: 파일 읽기, 수정, 생성, 삭제

```python
# src/agent/tools/file_tools.py

import aiofiles
from pathlib import Path
from typing import Dict, Any

from .base import BaseTool


class ReadFileTool(BaseTool):
    """파일 읽기 도구"""

    async def execute(self, params: Dict[str, Any]) -> str:
        """
        파일 읽기

        Params:
            path: 파일 경로

        Returns:
            파일 내용
        """
        file_path = self._resolve_path(params["path"])

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {params['path']}")

        if not file_path.is_file():
            raise ValueError(f"Not a file: {params['path']}")

        # 파일 크기 체크 (1MB 제한)
        if file_path.stat().st_size > 1024 * 1024:
            raise ValueError(f"File too large (max 1MB): {params['path']}")

        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()

        return content


class EditFileTool(BaseTool):
    """파일 수정 도구 (문자열 치환)"""

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        파일 수정

        Params:
            path: 파일 경로
            old_string: 기존 문자열
            new_string: 새 문자열

        Returns:
            수정 결과 {"success": True, "changes": 1}
        """
        file_path = self._resolve_path(params["path"])
        old_string = params["old_string"]
        new_string = params["new_string"]

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {params['path']}")

        # 파일 읽기
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()

        # 문자열 존재 확인
        if old_string not in content:
            raise ValueError(
                f"String not found in file. Make sure old_string matches exactly (including whitespace).\n\n"
                f"Old string:\n{old_string}"
            )

        # 중복 확인 (정확한 매칭을 위해)
        count = content.count(old_string)
        if count > 1:
            raise ValueError(
                f"String appears {count} times in file. Add more context to make it unique.\n\n"
                f"Old string:\n{old_string}"
            )

        # 치환
        new_content = content.replace(old_string, new_string, 1)

        # 백업 (선택)
        backup_path = file_path.with_suffix(file_path.suffix + ".backup")
        async with aiofiles.open(backup_path, "w", encoding="utf-8") as f:
            await f.write(content)

        # 파일 쓰기
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(new_content)

        return {
            "success": True,
            "changes": 1,
            "backup": str(backup_path)
        }


class CreateFileTool(BaseTool):
    """새 파일 생성 도구"""

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        파일 생성

        Params:
            path: 파일 경로
            content: 파일 내용

        Returns:
            생성 결과
        """
        file_path = self._resolve_path(params["path"])
        content = params["content"]

        if file_path.exists():
            raise FileExistsError(f"File already exists: {params['path']}")

        # 디렉토리 생성
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # 파일 쓰기
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(content)

        return {
            "success": True,
            "path": str(file_path),
            "size": len(content)
        }


class DeleteFileTool(BaseTool):
    """파일 삭제 도구"""

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        파일 삭제

        Params:
            path: 파일 경로
            confirm: 확인 (True여야 함)

        Returns:
            삭제 결과
        """
        file_path = self._resolve_path(params["path"])
        confirm = params.get("confirm", False)

        if not confirm:
            raise ValueError("Must set confirm=true to delete file")

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {params['path']}")

        # 백업
        backup_path = file_path.with_suffix(file_path.suffix + ".deleted")
        file_path.rename(backup_path)

        return {
            "success": True,
            "deleted": str(file_path),
            "backup": str(backup_path)
        }
```

---

### 6. Security Validator (보안 검증)

**역할**: 모든 액션의 보안 검증

```python
# src/agent/security/validator.py

from pathlib import Path
from typing import Dict, Any, List


class SecurityError(Exception):
    """보안 위반 예외"""
    pass


class SecurityValidator:
    """보안 검증기"""

    # 허용된 경로 (상대 경로, workspace 기준)
    ALLOWED_PATHS = [
        "src",
        "tests"
    ]

    # 차단된 경로
    BLOCKED_PATHS = [
        ".env",
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv"
    ]

    # 허용된 명령어
    ALLOWED_COMMANDS = [
        "pytest",
        "python",
        "pip",
        "black",
        "ruff",
        "mypy"
    ]

    # 파일 크기 제한
    MAX_FILE_SIZE = 1024 * 1024  # 1MB
    MAX_CREATE_SIZE = 500 * 1024  # 500KB

    def __init__(self, workspace_path: str):
        self.workspace_path = Path(workspace_path).resolve()

    def validate_action(self, tool_name: str, params: Dict[str, Any], workspace_path: str):
        """
        액션 보안 검증

        Args:
            tool_name: 도구 이름
            params: 파라미터
            workspace_path: 작업 디렉토리

        Raises:
            SecurityError: 보안 위반 시
        """
        # 파일 관련 도구
        if tool_name in ["read_file", "edit_file", "create_file", "delete_file"]:
            self.validate_file_path(params.get("path"), workspace_path)

        # 검색 도구
        elif tool_name in ["list_files", "search_code"]:
            self.validate_file_path(params.get("path", "."), workspace_path)

        # 명령 실행
        elif tool_name == "run_command":
            self.validate_command(params.get("command"))

        # 테스트
        elif tool_name == "run_tests":
            if "path" in params:
                self.validate_file_path(params["path"], workspace_path)

    def validate_file_path(self, path: str, workspace_path: str):
        """
        파일 경로 검증

        Args:
            path: 파일 경로
            workspace_path: 작업 디렉토리

        Raises:
            SecurityError: 보안 위반 시
        """
        if not path:
            raise SecurityError("Path cannot be empty")

        # 절대 경로 해석
        workspace = Path(workspace_path).resolve()

        if Path(path).is_absolute():
            target = Path(path).resolve()
        else:
            target = (workspace / path).resolve()

        # Workspace 밖으로 나가는지 체크
        try:
            target.relative_to(workspace)
        except ValueError:
            raise SecurityError(f"Path outside workspace: {path}")

        # 차단 경로 체크
        path_str = str(target.relative_to(workspace))

        for blocked in self.BLOCKED_PATHS:
            if blocked in path_str or path_str.startswith(blocked):
                raise SecurityError(f"Access denied to blocked path: {path}")

        # 허용 경로 체크 (엄격 모드)
        is_allowed = False

        for allowed in self.ALLOWED_PATHS:
            allowed_full = (workspace / allowed).resolve()
            try:
                target.relative_to(allowed_full)
                is_allowed = True
                break
            except ValueError:
                continue

        if not is_allowed and target != workspace:
            raise SecurityError(
                f"Path not in allowed directories ({', '.join(self.ALLOWED_PATHS)}): {path}"
            )

    def validate_command(self, command: str):
        """
        명령어 검증

        Args:
            command: 실행할 명령어

        Raises:
            SecurityError: 보안 위반 시
        """
        if not command:
            raise SecurityError("Command cannot be empty")

        # 첫 단어 (명령어) 추출
        cmd = command.split()[0]

        if cmd not in self.ALLOWED_COMMANDS:
            raise SecurityError(
                f"Command not allowed: {cmd}. "
                f"Allowed: {', '.join(self.ALLOWED_COMMANDS)}"
            )

        # 위험한 패턴 체크
        dangerous_patterns = [
            "rm -rf",
            "sudo",
            "chmod",
            ">",  # 리다이렉션
            "|",  # 파이프 (제한적 허용 가능)
            "&&",
            ";",
            "`",  # 명령 치환
            "$("
        ]

        for pattern in dangerous_patterns:
            if pattern in command:
                raise SecurityError(f"Dangerous pattern in command: {pattern}")
```

---

### 7. API 엔드포인트 (FastAPI)

**역할**: 사용자가 에이전트와 상호작용하는 인터페이스

```python
# src/routes/agent.py

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from typing import Optional
import asyncio
import uuid
import logging

from ..agent.orchestrator import AgentOrchestrator
from ..agent.llm.ollama_client import OllamaAgentClient
from ..agent.executor import ToolExecutor
from ..agent.security.validator import SecurityValidator

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])
logger = logging.getLogger(__name__)


class AgentTaskRequest(BaseModel):
    """에이전트 태스크 요청"""
    request: str = Field(..., description="사용자 요청")
    workspace_path: str = Field(default="/workspace", description="작업 디렉토리")


class AgentTaskResponse(BaseModel):
    """에이전트 태스크 응답"""
    task_id: str
    status: str
    message: str


# 활성 태스크 저장소 (프로덕션에서는 Redis 등 사용)
active_tasks = {}


@router.post("/task", response_model=AgentTaskResponse)
async def create_agent_task(request: AgentTaskRequest):
    """
    에이전트 태스크 생성

    WebSocket을 통해 실시간 진행 상황을 받을 수 있습니다.
    """
    task_id = str(uuid.uuid4())

    active_tasks[task_id] = {
        "status": "pending",
        "request": request.request,
        "workspace_path": request.workspace_path
    }

    return AgentTaskResponse(
        task_id=task_id,
        status="pending",
        message="Task created. Connect to WebSocket for real-time updates."
    )


@router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """태스크 상태 조회"""
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    return active_tasks[task_id]


@router.websocket("/ws/{task_id}")
async def agent_websocket(websocket: WebSocket, task_id: str):
    """
    에이전트 실시간 WebSocket

    태스크 진행 상황을 실시간으로 스트리밍합니다.
    """
    await websocket.accept()

    if task_id not in active_tasks:
        await websocket.send_json({"type": "error", "message": "Task not found"})
        await websocket.close()
        return

    task = active_tasks[task_id]

    try:
        # 오케스트레이터 초기화
        llm_client = OllamaAgentClient(
            host="http://ollama:11434",
            model="qwen2.5-coder:14b"
        )

        executor = ToolExecutor(workspace_path=task["workspace_path"])

        security = SecurityValidator(workspace_path=task["workspace_path"])

        orchestrator = AgentOrchestrator(
            llm_client=llm_client,
            executor=executor,
            security=security
        )

        # 태스크 실행 (스트리밍)
        async for event in orchestrator.execute_task(
            task_id=task_id,
            user_request=task["request"],
            workspace_path=task["workspace_path"]
        ):
            # WebSocket으로 이벤트 전송
            await websocket.send_json(event)

            # 태스크 상태 업데이트
            if event["type"] == "task_completed":
                active_tasks[task_id]["status"] = "completed"
                active_tasks[task_id]["result"] = event

            elif event["type"] == "task_failed":
                active_tasks[task_id]["status"] = "failed"
                active_tasks[task_id]["error"] = event.get("error")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {task_id}")

    except Exception as e:
        logger.error(f"Agent execution error: {e}")
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })

    finally:
        await websocket.close()
```

---

## 📊 데이터 흐름

```
1. 사용자 요청
   POST /api/v1/agent/task
   {"request": "User API에 타입 힌트 추가해줘"}

   → task_id 생성

2. WebSocket 연결
   WS /api/v1/agent/ws/{task_id}

3. 오케스트레이터 시작
   ┌─────────────────────────────────────┐
   │ Iteration 1                         │
   │  LLM → {"actions": [               │
   │    {"tool": "search_code",          │
   │     "params": {"pattern": "User"}}  │
   │  ]}                                 │
   │  Executor → search_code 실행        │
   │  Result → "Found in src/api/user.py"│
   └─────────────────────────────────────┘

   ┌─────────────────────────────────────┐
   │ Iteration 2                         │
   │  LLM → {"actions": [               │
   │    {"tool": "read_file",            │
   │     "params": {"path": "..."}}      │
   │  ]}                                 │
   │  Executor → read_file 실행          │
   │  Result → 파일 내용                 │
   └─────────────────────────────────────┘

   ┌─────────────────────────────────────┐
   │ Iteration 3                         │
   │  LLM → {"actions": [               │
   │    {"tool": "edit_file", ...}       │
   │  ]}                                 │
   │  Executor → edit_file 실행          │
   │  Result → 수정 완료                 │
   └─────────────────────────────────────┘

   ┌─────────────────────────────────────┐
   │ Iteration 4                         │
   │  LLM → {"actions": [               │
   │    {"tool": "run_tests", ...}       │
   │  ]}                                 │
   │  Executor → pytest 실행             │
   │  Result → All tests passed          │
   └─────────────────────────────────────┘

   ┌─────────────────────────────────────┐
   │ Iteration 5                         │
   │  LLM → {"actions": [               │
   │    {"tool": "finish",               │
   │     "params": {"success": true}}    │
   │  ]}                                 │
   │  → 태스크 완료                      │
   └─────────────────────────────────────┘

4. WebSocket 이벤트 스트림
   → {type: "iteration_start", ...}
   → {type: "reasoning", content: "..."}
   → {type: "action_start", tool: "search_code"}
   → {type: "action_success", result: {...}}
   → {type: "task_completed", success: true}
```

---

## 🚀 구현 단계

### Phase 1: 기초 인프라 (1-2일)
- [ ] 디렉토리 구조 생성
- [ ] BaseTool 인터페이스 구현
- [ ] SecurityValidator 구현 + 테스트
- [ ] 시스템 프롬프트 파일 작성

### Phase 2: 핵심 도구 (2-3일)
- [ ] ReadFileTool 구현
- [ ] EditFileTool 구현
- [ ] CreateFileTool 구현
- [ ] DeleteFileTool 구현
- [ ] 단위 테스트 작성

### Phase 3: 검색 & 테스트 도구 (1-2일)
- [ ] ListFilesTool 구현
- [ ] SearchCodeTool 구현 (grep/ripgrep)
- [ ] RunTestsTool 구현 (pytest)
- [ ] RunCommandTool 구현
- [ ] 단위 테스트 작성

### Phase 4: LLM 통합 (2-3일)
- [ ] OllamaAgentClient 구현
- [ ] JSON 파싱 로직 구현
- [ ] 프롬프트 빌더 구현
- [ ] 대화 히스토리 관리
- [ ] 통합 테스트

### Phase 5: 오케스트레이터 (2-3일)
- [ ] AgentOrchestrator 구현
- [ ] 반복 루프 로직
- [ ] 에러 처리
- [ ] 상태 관리
- [ ] 통합 테스트

### Phase 6: API 엔드포인트 (1-2일)
- [ ] FastAPI 라우트 구현
- [ ] WebSocket 스트리밍
- [ ] 태스크 상태 관리
- [ ] API 문서화

### Phase 7: 상호작용 도구 (1일)
- [ ] AskUserTool (WebSocket 양방향 통신)
- [ ] FinishTool
- [ ] ReportErrorTool

### Phase 8: 테스트 & 디버깅 (2-3일)
- [ ] End-to-End 테스트
- [ ] 실제 코딩 시나리오 테스트
- [ ] 버그 수정
- [ ] 성능 최적화

### Phase 9: 문서화 & 배포 (1-2일)
- [ ] 사용자 가이드 작성
- [ ] API 문서 작성
- [ ] Docker 이미지 업데이트
- [ ] README 업데이트

**총 예상 기간: 13-21일 (2-3주)**

---

## 🔒 보안 고려사항

### 1. Path Traversal 방지
```python
# ❌ 위험
path = "../../../etc/passwd"

# ✅ 안전 (SecurityValidator가 차단)
→ SecurityError: Path outside workspace
```

### 2. 명령 인젝션 방지
```python
# ❌ 위험
command = "pytest; rm -rf /"

# ✅ 안전 (SecurityValidator가 차단)
→ SecurityError: Dangerous pattern in command: ;
```

### 3. 파일 크기 제한
```python
# ❌ 위험 (대용량 파일 읽기 → DoS)
read_file("large_file.bin")  # 5GB

# ✅ 안전
→ ValueError: File too large (max 1MB)
```

### 4. 샌드박스 (선택)
Docker 컨테이너 내부에서 실행하여 호스트 시스템 보호

```yaml
# docker-compose.yml
coding-agent:
  security_opt:
    - no-new-privileges:true
  read_only: true
  tmpfs:
    - /tmp
  volumes:
    - ./workspace:/workspace  # 제한된 볼륨만
```

---

## 📈 성능 최적화

### 1. 도구 병렬 실행
독립적인 액션은 병렬로 실행:

```python
# LLM 응답
{
  "actions": [
    {"tool": "read_file", "params": {"path": "src/api/user.py"}},
    {"tool": "read_file", "params": {"path": "tests/test_user.py"}},
    {"tool": "read_file", "params": {"path": "src/models/user.py"}}
  ]
}

# Executor에서 병렬 실행
results = await asyncio.gather(
    tool1.execute(),
    tool2.execute(),
    tool3.execute()
)
```

### 2. LLM 응답 캐싱
동일한 요청에 대한 캐싱:

```python
import hashlib
from functools import lru_cache

@lru_cache(maxsize=100)
def get_cached_response(request_hash):
    # ...
```

### 3. 점진적 스트리밍
LLM 응답을 스트리밍으로 받아 즉시 처리:

```python
response = client.chat(model=MODEL, messages=messages, stream=True)

for chunk in response:
    # 청크 단위로 처리
```

---

## 🎨 UI/UX 개선 (선택)

### Web UI (React + TailwindCSS)
```
┌─────────────────────────────────────────┐
│  AI Coding Agent                        │
├─────────────────────────────────────────┤
│  Request: [User API에 타입 힌트 추가]   │
│  [Start]                                │
├─────────────────────────────────────────┤
│  Progress:                              │
│  ✅ Iteration 1: Searching for files    │
│  ✅ Iteration 2: Reading user.py        │
│  🔄 Iteration 3: Editing file...        │
│                                         │
│  Console:                               │
│  > Reasoning: 타입 힌트가 없어서...     │
│  > Executing: edit_file                 │
│  > Result: Success                      │
└─────────────────────────────────────────┘
```

---

## 🧪 테스트 전략

### 1. 단위 테스트
각 도구를 독립적으로 테스트:

```python
# tests/agent/test_tools.py

async def test_read_file_tool():
    tool = ReadFileTool("/workspace")

    # 성공 케이스
    result = await tool.execute({"path": "src/test.py"})
    assert "def test" in result

    # 실패 케이스 - 파일 없음
    with pytest.raises(FileNotFoundError):
        await tool.execute({"path": "nonexistent.py"})
```

### 2. 통합 테스트
전체 워크플로우 테스트:

```python
# tests/agent/test_integration.py

async def test_full_agent_workflow():
    orchestrator = create_test_orchestrator()

    events = []
    async for event in orchestrator.execute_task(
        task_id="test",
        user_request="src/example.py 파일에 주석 추가",
        workspace_path="/workspace"
    ):
        events.append(event)

    # 검증
    assert any(e["type"] == "task_completed" for e in events)
```

### 3. 보안 테스트
보안 검증 테스트:

```python
async def test_path_traversal_blocked():
    validator = SecurityValidator("/workspace")

    with pytest.raises(SecurityError):
        validator.validate_file_path("../../etc/passwd", "/workspace")
```

---

## 📝 사용 예시

### CLI에서 사용
```bash
curl -X POST http://localhost:8000/api/v1/agent/task \
  -H "Content-Type: application/json" \
  -d '{
    "request": "src/api/user.py의 모든 함수에 타입 힌트 추가해줘"
  }'

# 응답: {"task_id": "abc-123", ...}

# WebSocket으로 실시간 확인
wscat -c ws://localhost:8000/api/v1/agent/ws/abc-123
```

### Python SDK에서 사용
```python
import asyncio
import websockets
import json

async def run_agent_task(request: str):
    # 태스크 생성
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:8000/api/v1/agent/task",
            json={"request": request}
        ) as resp:
            data = await resp.json()
            task_id = data["task_id"]

    # WebSocket 연결
    uri = f"ws://localhost:8000/api/v1/agent/ws/{task_id}"

    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            event = json.loads(message)

            if event["type"] == "reasoning":
                print(f"💭 {event['content']}")

            elif event["type"] == "action_start":
                print(f"🔧 {event['tool']}")

            elif event["type"] == "task_completed":
                print(f"✅ {event['message']}")
                break

asyncio.run(run_agent_task("User API 리팩토링"))
```

---

## 🔮 향후 개선 방향

### 1. 멀티 에이전트
여러 에이전트가 협업:
- Code Agent (코드 작성)
- Test Agent (테스트 작성)
- Review Agent (코드 리뷰)

### 2. 학습 및 개선
- 성공/실패 케이스 로깅
- Fine-tuning 데이터 수집
- RAG (검색 증강 생성)

### 3. IDE 통합
- VS Code Extension
- JetBrains Plugin
- GitHub Copilot 스타일 UI

### 4. 고급 기능
- Git 통합 (자동 커밋)
- PR 생성
- 코드 리뷰 자동화
- 리팩토링 제안

---

이 설계를 바탕으로 구현하시면, Claude Code / Cursor / GitHub Copilot과 유사한 코딩 에이전트를 만들 수 있습니다! 🚀
