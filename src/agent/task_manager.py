"""
Task Manager

Manages multiple agent tasks and their lifecycle.
"""

from typing import Dict, Optional, AsyncIterator
import asyncio
import logging
from datetime import datetime

from .orchestrator import AgentOrchestrator
from .memory.task_state import TaskState, TaskStatus

logger = logging.getLogger(__name__)


class TaskManager:
    """
    작업 관리자

    여러 에이전트 작업을 동시에 관리하고 상태를 추적합니다.
    """

    def __init__(self, orchestrator: AgentOrchestrator):
        """
        Args:
            orchestrator: AgentOrchestrator 인스턴스
        """
        self.orchestrator = orchestrator
        self.tasks: Dict[str, TaskState] = {}
        self._task_locks: Dict[str, asyncio.Lock] = {}
        logger.info("TaskManager initialized")

    def create_task(
        self,
        task_id: str,
        user_request: str,
        workspace_path: str
    ) -> TaskState:
        """
        새 작업 생성

        Args:
            task_id: 작업 ID (UUID 권장)
            user_request: 사용자 요청 내용
            workspace_path: 작업 디렉토리 경로

        Returns:
            생성된 TaskState

        Raises:
            ValueError: task_id가 이미 존재하는 경우
        """
        if task_id in self.tasks:
            raise ValueError(f"Task {task_id} already exists")

        task = TaskState(
            task_id=task_id,
            user_request=user_request,
            workspace_path=workspace_path
        )

        self.tasks[task_id] = task
        self._task_locks[task_id] = asyncio.Lock()

        logger.info(f"Task created: {task_id}")
        return task

    def get_task(self, task_id: str) -> Optional[TaskState]:
        """
        작업 조회

        Args:
            task_id: 작업 ID

        Returns:
            TaskState 또는 None
        """
        return self.tasks.get(task_id)

    def list_tasks(self) -> list[TaskState]:
        """
        모든 작업 목록 조회

        Returns:
            TaskState 목록
        """
        return list(self.tasks.values())

    def list_tasks_by_status(self, status: TaskStatus) -> list[TaskState]:
        """
        상태별 작업 목록 조회

        Args:
            status: 필터링할 작업 상태

        Returns:
            해당 상태의 TaskState 목록
        """
        return [
            task for task in self.tasks.values()
            if task.status == status
        ]

    async def execute_task(
        self,
        task_id: str
    ) -> AsyncIterator[Dict]:
        """
        작업 실행 (비동기 제너레이터)

        Args:
            task_id: 작업 ID

        Yields:
            실행 이벤트 딕셔너리

        Raises:
            ValueError: task_id를 찾을 수 없는 경우
        """
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # 동시 실행 방지
        async with self._task_locks[task_id]:
            if task.status == TaskStatus.RUNNING:
                raise ValueError(f"Task {task_id} is already running")

            logger.info(f"Starting task execution: {task_id}")

            # 오케스트레이터에게 작업 위임
            try:
                async for event in self.orchestrator.execute_task(
                    task_id=task_id,
                    user_request=task.user_request,
                    workspace_path=task.workspace_path
                ):
                    # 이벤트를 그대로 전달
                    yield event

                    # task_completed/failed 이벤트로 상태 동기화
                    if event["type"] == "task_completed":
                        task.complete(event.get("result", {}))
                    elif event["type"] == "task_failed":
                        task.fail(event["error"])

            except Exception as e:
                logger.error(f"Task execution failed: {task_id}, error: {e}")
                task.fail(str(e))
                yield {
                    "type": "task_failed",
                    "task_id": task_id,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }

    def delete_task(self, task_id: str) -> bool:
        """
        작업 삭제

        Args:
            task_id: 작업 ID

        Returns:
            삭제 성공 여부
        """
        if task_id in self.tasks:
            # 실행 중인 작업은 삭제 불가
            task = self.tasks[task_id]
            if task.status == TaskStatus.RUNNING:
                logger.warning(f"Cannot delete running task: {task_id}")
                return False

            del self.tasks[task_id]
            if task_id in self._task_locks:
                del self._task_locks[task_id]

            logger.info(f"Task deleted: {task_id}")
            return True

        return False

    def get_stats(self) -> Dict:
        """
        작업 통계 조회

        Returns:
            통계 딕셔너리
        """
        return {
            "total": len(self.tasks),
            "pending": len(self.list_tasks_by_status(TaskStatus.PENDING)),
            "running": len(self.list_tasks_by_status(TaskStatus.RUNNING)),
            "completed": len(self.list_tasks_by_status(TaskStatus.COMPLETED)),
            "failed": len(self.list_tasks_by_status(TaskStatus.FAILED))
        }

    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"<TaskManager total={stats['total']} "
            f"running={stats['running']} "
            f"completed={stats['completed']}>"
        )
