"""TaskManager.execute_task()가 asyncio.CancelledError 발생 시 태스크 상태를
FAILED로 정리하고 예외를 그대로 전파하는지 검증한다."""

import asyncio

import pytest

from src.agent.memory.task_state import TaskStatus
from src.agent.task_manager import TaskManager


class _CancellingOrchestrator:
    """실행 도중 asyncio.CancelledError를 던지는 가짜 오케스트레이터."""

    async def execute_task(self, task_id, user_request, workspace_path):
        yield {"type": "iteration_start", "iteration": 1}
        raise asyncio.CancelledError()


@pytest.mark.asyncio
async def test_execute_task_marks_failed_on_cancelled_error():
    task_manager = TaskManager(orchestrator=_CancellingOrchestrator())
    task_manager.create_task(
        task_id="t1",
        user_request="do something",
        workspace_path="/workspace",
    )

    with pytest.raises(asyncio.CancelledError):
        async for _event in task_manager.execute_task("t1"):
            pass

    task = task_manager.get_task("t1")
    assert task.status == TaskStatus.FAILED
