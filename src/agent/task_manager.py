"""
Task Manager

Manages multiple agent tasks and their lifecycle.
"""

from typing import Callable, Dict, Optional, AsyncIterator
import asyncio
import logging
from datetime import datetime

from .llm.base import LLMClient
from .orchestrator import AgentOrchestrator
from .memory.task_state import TaskState, TaskStatus

logger = logging.getLogger(__name__)


class TaskManager:
    """
    작업 관리자

    여러 에이전트 작업을 동시에 관리하고 상태를 추적합니다.
    """

    def __init__(
        self,
        orchestrator: AgentOrchestrator,
        llm_client_factory: Optional[Callable[[str], LLMClient]] = None,
    ):
        """
        Args:
            orchestrator: AgentOrchestrator 인스턴스
            llm_client_factory: 모델 이름 하나를 받아 그 모델을 쓰는 LLMClient를
                만들어주는 팩토리. 태스크가 기본 모델과 다른 model을 지정했을 때
                execute_task()가 이걸로 오버라이드 클라이언트를 만든다. 생략하면
                모든 태스크가 orchestrator에 주입된 기본 모델로만 실행된다.
        """
        self.orchestrator = orchestrator
        self.llm_client_factory = llm_client_factory
        self.tasks: Dict[str, TaskState] = {}
        self._task_locks: Dict[str, asyncio.Lock] = {}
        logger.info("TaskManager initialized")

    def create_task(
        self,
        task_id: str,
        user_request: str,
        workspace_path: str,
        model: Optional[str] = None
    ) -> TaskState:
        """
        새 작업 생성

        Args:
            task_id: 작업 ID (UUID 권장)
            user_request: 사용자 요청 내용
            workspace_path: 작업 디렉토리 경로
            model: 이 태스크에 쓸 모델. 생략하면 기본 모델을 쓴다.

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
            workspace_path=workspace_path,
            model=model
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

            task.start()
            logger.info(f"Starting task execution: {task_id}")

            # 태스크가 기본 모델과 다른 model을 지정했으면 그 모델로 오버라이드 클라이언트를
            # 만든다. factory가 없거나 모델 지정이 없으면 orchestrator의 기본 모델을 그대로 씀.
            override_llm_client: Optional[LLMClient] = None
            if task.model and self.llm_client_factory is not None:
                override_llm_client = self.llm_client_factory(task.model)
            elif not task.model:
                # 명시적으로 지정 안 한 태스크도 API 응답에서 실제로 어떤 모델로
                # 실행됐는지 항상 드러나도록 기본 모델 이름을 채워 넣는다. orchestrator가
                # (테스트 더블 등으로) llm을 안 갖고 있을 수도 있으니 안전하게 조회.
                default_llm = getattr(self.orchestrator, "llm", None)
                if default_llm is not None:
                    task.model = getattr(default_llm, "model", None)

            # 오케스트레이터에게 작업 위임
            try:
                async for event in self.orchestrator.execute_task(
                    task_id=task_id,
                    user_request=task.user_request,
                    workspace_path=task.workspace_path,
                    llm_client=override_llm_client
                ):
                    # 이벤트를 그대로 전달
                    yield event

                    # task_completed/failed 이벤트로 상태 동기화
                    # (orchestrator 이벤트는 result를 summary.result에 담아 보냄)
                    if event["type"] == "task_completed":
                        task.complete(
                            event.get("summary", {}).get("result") or {},
                            verification=event.get("verification")
                        )
                    elif event["type"] == "task_failed":
                        task.fail(event.get("error", "Unknown error"))

            except Exception as e:
                logger.error(f"Task execution failed: {task_id}, error: {e}")
                task.fail(str(e))
                yield {
                    "type": "task_failed",
                    "task_id": task_id,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
            finally:
                # SSE/WebSocket 클라이언트가 실행 도중 연결을 끊으면 asyncio.CancelledError가
                # 발생한다. Python 3.8+에서 CancelledError는 BaseException 계열이라 위
                # except Exception에는 잡히지 않고 그대로 전파되는데, 그 경우에도 태스크가
                # 영구 RUNNING으로 남지 않도록 여기서 한 번 더 상태를 확인해 정리한다.
                # CancelledError 자체는 삼키면 안 되므로 여기서 catch하거나 raise/return하지
                # 않는다 — finally를 그냥 통과시키면 원래 예외가 알아서 계속 전파된다.
                if task.status == TaskStatus.RUNNING:
                    task.fail("Task execution was interrupted")

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
