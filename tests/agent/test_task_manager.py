"""
Tests for Task Manager

Tests the TaskManager that manages multiple agent tasks.
"""

import pytest
from unittest.mock import Mock, AsyncMock

from src.agent.task_manager import TaskManager
from src.agent.orchestrator import AgentOrchestrator
from src.agent.memory.task_state import TaskStatus
from src.agent.llm.ollama_client import AgentResponse


@pytest.fixture
def mock_orchestrator():
    """Mock AgentOrchestrator"""
    orchestrator = Mock(spec=AgentOrchestrator)
    return orchestrator


@pytest.fixture
def task_manager(mock_orchestrator):
    """TaskManager 인스턴스"""
    return TaskManager(orchestrator=mock_orchestrator)


class TestTaskManagerBasics:
    """TaskManager 기본 기능 테스트"""

    def test_create_task(self, task_manager):
        """작업 생성 - 성공"""
        task = task_manager.create_task(
            task_id="test-1",
            user_request="Test request",
            workspace_path="/workspace"
        )

        assert task.task_id == "test-1"
        assert task.status == TaskStatus.PENDING
        assert task_manager.get_task("test-1") == task

    def test_create_duplicate_task(self, task_manager):
        """중복 작업 생성 - 실패"""
        task_manager.create_task(
            task_id="test-1",
            user_request="Test",
            workspace_path="/workspace"
        )

        with pytest.raises(ValueError, match="already exists"):
            task_manager.create_task(
                task_id="test-1",
                user_request="Test",
                workspace_path="/workspace"
            )

    def test_get_task(self, task_manager):
        """작업 조회 - 성공"""
        task_manager.create_task(
            task_id="test-1",
            user_request="Test",
            workspace_path="/workspace"
        )

        task = task_manager.get_task("test-1")
        assert task is not None
        assert task.task_id == "test-1"

    def test_get_nonexistent_task(self, task_manager):
        """존재하지 않는 작업 조회 - None 반환"""
        task = task_manager.get_task("nonexistent")
        assert task is None

    def test_list_tasks(self, task_manager):
        """작업 목록 조회 - 성공"""
        task_manager.create_task("test-1", "Request 1", "/workspace")
        task_manager.create_task("test-2", "Request 2", "/workspace")
        task_manager.create_task("test-3", "Request 3", "/workspace")

        tasks = task_manager.list_tasks()
        assert len(tasks) == 3

    def test_list_tasks_by_status(self, task_manager):
        """상태별 작업 목록 조회 - 성공"""
        task1 = task_manager.create_task("test-1", "Request 1", "/workspace")
        task2 = task_manager.create_task("test-2", "Request 2", "/workspace")
        task3 = task_manager.create_task("test-3", "Request 3", "/workspace")

        # 상태 변경
        task1.start()
        task2.start()
        task2.complete({"message": "Done"})

        pending = task_manager.list_tasks_by_status(TaskStatus.PENDING)
        running = task_manager.list_tasks_by_status(TaskStatus.RUNNING)
        completed = task_manager.list_tasks_by_status(TaskStatus.COMPLETED)

        assert len(pending) == 1
        assert len(running) == 1
        assert len(completed) == 1

    def test_delete_task(self, task_manager):
        """작업 삭제 - 성공"""
        task_manager.create_task("test-1", "Test", "/workspace")

        result = task_manager.delete_task("test-1")
        assert result is True
        assert task_manager.get_task("test-1") is None

    def test_delete_nonexistent_task(self, task_manager):
        """존재하지 않는 작업 삭제 - 실패"""
        result = task_manager.delete_task("nonexistent")
        assert result is False

    def test_delete_running_task(self, task_manager):
        """실행 중인 작업 삭제 - 실패"""
        task = task_manager.create_task("test-1", "Test", "/workspace")
        task.start()

        result = task_manager.delete_task("test-1")
        assert result is False
        assert task_manager.get_task("test-1") is not None

    def test_get_stats(self, task_manager):
        """통계 조회 - 성공"""
        task1 = task_manager.create_task("test-1", "Request 1", "/workspace")
        task2 = task_manager.create_task("test-2", "Request 2", "/workspace")
        task3 = task_manager.create_task("test-3", "Request 3", "/workspace")
        task4 = task_manager.create_task("test-4", "Request 4", "/workspace")

        # 상태 변경
        task1.start()
        task2.start()
        task2.complete({"message": "Done"})
        task3.start()
        task3.fail("Error")

        stats = task_manager.get_stats()

        assert stats["total"] == 4
        assert stats["pending"] == 1
        assert stats["running"] == 1
        assert stats["completed"] == 1
        assert stats["failed"] == 1


class TestTaskExecution:
    """TaskManager 작업 실행 테스트"""

    @pytest.mark.asyncio
    async def test_execute_task(self, task_manager, mock_orchestrator):
        """작업 실행 - 성공"""
        task_manager.create_task(
            task_id="test-1",
            user_request="Test request",
            workspace_path="/workspace"
        )

        # Mock orchestrator가 이벤트 스트림 반환하도록 설정
        async def mock_execute(*args, **kwargs):
            yield {"type": "iteration_start", "iteration": 1}
            yield {"type": "reasoning", "content": "Test"}
            yield {"type": "task_completed", "result": {"message": "Done"}}

        mock_orchestrator.execute_task = mock_execute

        events = []
        async for event in task_manager.execute_task("test-1"):
            events.append(event)

        assert len(events) == 3
        assert events[0]["type"] == "iteration_start"
        assert events[-1]["type"] == "task_completed"

        # 작업 상태가 완료로 변경되었는지 확인
        task = task_manager.get_task("test-1")
        assert task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_nonexistent_task(self, task_manager):
        """존재하지 않는 작업 실행 - 실패"""
        with pytest.raises(ValueError, match="not found"):
            async for _ in task_manager.execute_task("nonexistent"):
                pass

    @pytest.mark.asyncio
    async def test_execute_already_running_task(self, task_manager, mock_orchestrator):
        """이미 실행 중인 작업 재실행 - 실패"""
        task = task_manager.create_task(
            task_id="test-1",
            user_request="Test",
            workspace_path="/workspace"
        )
        task.start()

        with pytest.raises(ValueError, match="already running"):
            async for _ in task_manager.execute_task("test-1"):
                pass

    @pytest.mark.asyncio
    async def test_execute_task_failure(self, task_manager, mock_orchestrator):
        """작업 실행 실패 - 성공적으로 처리"""
        task_manager.create_task(
            task_id="test-1",
            user_request="Test",
            workspace_path="/workspace"
        )

        # Mock orchestrator가 실패 이벤트 반환
        async def mock_execute(*args, **kwargs):
            yield {"type": "iteration_start", "iteration": 1}
            yield {"type": "task_failed", "error": "Something went wrong"}

        mock_orchestrator.execute_task = mock_execute

        events = []
        async for event in task_manager.execute_task("test-1"):
            events.append(event)

        assert events[-1]["type"] == "task_failed"

        # 작업 상태가 실패로 변경되었는지 확인
        task = task_manager.get_task("test-1")
        assert task.status == TaskStatus.FAILED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
