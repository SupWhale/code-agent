"""
Agent API Routes

FastAPI endpoints for AI agent task management.
"""

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import uuid
import logging
from datetime import datetime
import json

from ..agent.task_manager import TaskManager
from ..agent.memory.task_state import TaskStatus

logger = logging.getLogger(__name__)

# 전역 TaskManager 인스턴스 (나중에 의존성 주입으로 변경 가능)
_task_manager: Optional[TaskManager] = None


def init_agent_router(task_manager: TaskManager) -> APIRouter:
    """
    Agent 라우터 초기화

    Args:
        task_manager: TaskManager 인스턴스

    Returns:
        설정된 APIRouter
    """
    global _task_manager
    _task_manager = task_manager

    router = APIRouter(prefix="/api/v1/agent", tags=["agent"])

    # Request/Response 모델
    class CreateTaskRequest(BaseModel):
        """작업 생성 요청"""
        user_request: str = Field(..., description="사용자 요청 내용", min_length=1)
        workspace_path: str = Field(..., description="작업 디렉토리 경로")
        task_id: Optional[str] = Field(None, description="작업 ID (생략 시 자동 생성)")

    class TaskResponse(BaseModel):
        """작업 응답"""
        task_id: str
        status: str
        user_request: str
        workspace_path: str
        result: Optional[Dict[str, Any]] = None
        error: Optional[str] = None
        started_at: Optional[str] = None
        completed_at: Optional[str] = None
        duration_seconds: Optional[float] = None
        iteration_count: int = 0

    class TaskListResponse(BaseModel):
        """작업 목록 응답"""
        tasks: list[TaskResponse]
        total: int
        stats: Dict[str, int]

    class ErrorResponse(BaseModel):
        """에러 응답"""
        error: str
        detail: Optional[str] = None

    # 엔드포인트
    @router.post("/task", response_model=TaskResponse, status_code=201)
    async def create_task(request: CreateTaskRequest):
        """
        새 에이전트 작업 생성

        작업을 생성만 하고 즉시 반환합니다.
        실제 실행은 /task/{task_id}/execute 또는 WebSocket으로 시작합니다.
        """
        task_id = request.task_id or str(uuid.uuid4())

        try:
            task = _task_manager.create_task(
                task_id=task_id,
                user_request=request.user_request,
                workspace_path=request.workspace_path
            )

            logger.info(f"Task created via API: {task_id}")

            return TaskResponse(
                task_id=task.task_id,
                status=task.status.value,
                user_request=task.user_request,
                workspace_path=task.workspace_path,
                iteration_count=task.get_iteration_count()
            )

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/task/{task_id}", response_model=TaskResponse)
    async def get_task(task_id: str):
        """
        작업 상태 조회

        특정 작업의 현재 상태와 결과를 조회합니다.
        """
        task = _task_manager.get_task(task_id)

        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        return TaskResponse(
            task_id=task.task_id,
            status=task.status.value,
            user_request=task.user_request,
            workspace_path=task.workspace_path,
            result=task.result,
            error=task.error,
            started_at=task.started_at.isoformat() if task.started_at else None,
            completed_at=task.completed_at.isoformat() if task.completed_at else None,
            duration_seconds=task.get_duration(),
            iteration_count=task.get_iteration_count()
        )

    @router.get("/tasks", response_model=TaskListResponse)
    async def list_tasks(status: Optional[str] = None):
        """
        작업 목록 조회

        모든 작업 또는 특정 상태의 작업 목록을 조회합니다.
        """
        if status:
            try:
                task_status = TaskStatus(status)
                tasks = _task_manager.list_tasks_by_status(task_status)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {status}. "
                           f"Valid values: pending, running, completed, failed"
                )
        else:
            tasks = _task_manager.list_tasks()

        stats = _task_manager.get_stats()

        return TaskListResponse(
            tasks=[
                TaskResponse(
                    task_id=task.task_id,
                    status=task.status.value,
                    user_request=task.user_request,
                    workspace_path=task.workspace_path,
                    result=task.result,
                    error=task.error,
                    started_at=task.started_at.isoformat() if task.started_at else None,
                    completed_at=task.completed_at.isoformat() if task.completed_at else None,
                    duration_seconds=task.get_duration(),
                    iteration_count=task.get_iteration_count()
                )
                for task in tasks
            ],
            total=len(tasks),
            stats=stats
        )

    @router.delete("/task/{task_id}", status_code=204)
    async def delete_task(task_id: str):
        """
        작업 삭제

        완료되거나 실패한 작업을 삭제합니다.
        실행 중인 작업은 삭제할 수 없습니다.
        """
        result = _task_manager.delete_task(task_id)

        if not result:
            task = _task_manager.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
            elif task.status == TaskStatus.RUNNING:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot delete running task"
                )

        return None

    @router.post("/task/{task_id}/execute")
    async def execute_task(task_id: str):
        """
        작업 실행 (Server-Sent Events)

        작업을 실행하고 실시간 이벤트를 SSE로 스트리밍합니다.
        """
        task = _task_manager.get_task(task_id)

        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        if task.status == TaskStatus.RUNNING:
            raise HTTPException(status_code=400, detail="Task is already running")

        async def event_stream():
            """SSE 이벤트 스트림"""
            try:
                async for event in _task_manager.execute_task(task_id):
                    # SSE 형식: data: {json}\n\n
                    yield f"data: {json.dumps(event)}\n\n"

            except Exception as e:
                logger.error(f"Task execution error: {e}")
                error_event = {
                    "type": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
                yield f"data: {json.dumps(error_event)}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Nginx 버퍼링 비활성화
            }
        )

    @router.websocket("/ws/{task_id}")
    async def websocket_endpoint(websocket: WebSocket, task_id: str):
        """
        WebSocket 엔드포인트

        작업 실행 이벤트를 WebSocket으로 실시간 전송합니다.
        """
        await websocket.accept()
        logger.info(f"WebSocket connection established for task: {task_id}")

        try:
            task = _task_manager.get_task(task_id)

            if not task:
                await websocket.send_json({
                    "type": "error",
                    "error": f"Task {task_id} not found"
                })
                await websocket.close()
                return

            if task.status == TaskStatus.RUNNING:
                await websocket.send_json({
                    "type": "error",
                    "error": "Task is already running"
                })
                await websocket.close()
                return

            # 작업 실행 및 이벤트 전송
            async for event in _task_manager.execute_task(task_id):
                await websocket.send_json(event)

            logger.info(f"Task {task_id} completed, closing WebSocket")

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for task: {task_id}")
        except Exception as e:
            logger.error(f"WebSocket error for task {task_id}: {e}")
            try:
                await websocket.send_json({
                    "type": "error",
                    "error": str(e)
                })
            except:
                pass
        finally:
            try:
                await websocket.close()
            except:
                pass

    return router
