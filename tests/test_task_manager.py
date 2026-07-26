"""TaskManager.execute_task()가 asyncio.CancelledError 발생 시 태스크 상태를
FAILED로 정리하고 예외를 그대로 전파하는지 검증한다."""

import asyncio

import pytest

from src.agent.memory.task_state import TaskStatus
from src.agent.task_manager import TaskManager


class _CancellingOrchestrator:
    """실행 도중 asyncio.CancelledError를 던지는 가짜 오케스트레이터."""

    async def execute_task(self, task_id, user_request, workspace_path, llm_client=None):
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


class _FakeDefaultLLM:
    model = "default-model"


class _RecordingOrchestrator:
    """넘겨받은 llm_client를 기록만 하고 바로 finish하는 가짜 오케스트레이터."""

    def __init__(self):
        self.llm = _FakeDefaultLLM()
        self.received_llm_clients = []

    async def execute_task(self, task_id, user_request, workspace_path, llm_client=None):
        self.received_llm_clients.append(llm_client)
        yield {
            "type": "task_completed",
            "success": True,
            "message": "done",
            "verification": {"suspicious": False},
            "summary": {"result": {}},
        }


@pytest.mark.asyncio
async def test_execute_task_uses_override_model_via_factory():
    orchestrator = _RecordingOrchestrator()

    created_for = []

    def fake_factory(model_name):
        created_for.append(model_name)
        return object()  # 실제 LLMClient일 필요 없음 — 뭐가 넘어가는지만 확인

    task_manager = TaskManager(orchestrator=orchestrator, llm_client_factory=fake_factory)
    task_manager.create_task(
        task_id="t1", user_request="x", workspace_path="/workspace", model="other-model"
    )

    async for _event in task_manager.execute_task("t1"):
        pass

    assert created_for == ["other-model"]
    assert orchestrator.received_llm_clients[0] is not None
    assert task_manager.get_task("t1").model == "other-model"


@pytest.mark.asyncio
async def test_execute_task_fills_in_default_model_when_unspecified():
    orchestrator = _RecordingOrchestrator()
    task_manager = TaskManager(orchestrator=orchestrator, llm_client_factory=None)
    task_manager.create_task(task_id="t1", user_request="x", workspace_path="/workspace")

    async for _event in task_manager.execute_task("t1"):
        pass

    # factory가 없거나 오버라이드가 없으면 execute_task에는 override를 안 넘긴다
    assert orchestrator.received_llm_clients[0] is None
    # 대신 API 응답용으로 실제 실행된 기본 모델 이름을 채워 넣는다
    assert task_manager.get_task("t1").model == "default-model"
