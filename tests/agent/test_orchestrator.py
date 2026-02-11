"""
Tests for Agent Orchestrator

Tests the main orchestrator that connects LLM and tools.
"""

import pytest
from pathlib import Path
import tempfile
from unittest.mock import Mock, AsyncMock, MagicMock

from src.agent.orchestrator import AgentOrchestrator
from src.agent.executor import ToolExecutor
from src.agent.security.validator import SecurityValidator
from src.agent.llm.ollama_client import AgentResponse
from src.agent.memory.task_state import TaskStatus


@pytest.fixture
def temp_workspace():
    """임시 작업 디렉토리"""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "src").mkdir()
        (workspace / "src" / "test.py").write_text("def test(): pass")
        yield str(workspace)


@pytest.fixture
def mock_llm_client():
    """Mock LLM 클라이언트"""
    client = Mock()

    # finish 도구를 호출하도록 응답 설정
    client.get_next_actions = Mock(return_value=AgentResponse(
        reasoning="Task completed",
        actions=[{"tool": "finish", "params": {"success": True, "message": "Done"}}],
        raw_response='{"reasoning": "Task completed", "actions": [{"tool": "finish"}]}'
    ))

    return client


@pytest.fixture
def executor(temp_workspace):
    """ToolExecutor 인스턴스"""
    return ToolExecutor(temp_workspace)


@pytest.fixture
def security(temp_workspace):
    """SecurityValidator 인스턴스"""
    return SecurityValidator(temp_workspace, strict_mode=True)


class TestToolExecutor:
    """ToolExecutor 테스트"""

    @pytest.mark.asyncio
    async def test_execute_read_file(self, temp_workspace):
        """read_file 도구 실행 - 성공"""
        executor = ToolExecutor(temp_workspace)

        result = await executor.execute("read_file", {"path": "src/test.py"})

        assert "def test()" in result

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, temp_workspace):
        """존재하지 않는 도구 실행 - 실패"""
        executor = ToolExecutor(temp_workspace)

        with pytest.raises(ValueError, match="Unknown tool"):
            await executor.execute("nonexistent_tool", {})

    def test_get_available_tools(self, temp_workspace):
        """사용 가능한 도구 목록 - 성공"""
        executor = ToolExecutor(temp_workspace)

        tools = executor.get_available_tools()

        assert "read_file" in tools
        assert "edit_file" in tools
        assert "list_files" in tools
        assert "finish" in tools
        assert "ask_user" in tools
        assert len(tools) >= 11

    def test_has_tool(self, temp_workspace):
        """도구 존재 확인 - 성공"""
        executor = ToolExecutor(temp_workspace)

        assert executor.has_tool("read_file") is True
        assert executor.has_tool("nonexistent") is False


class TestAgentOrchestrator:
    """AgentOrchestrator 테스트"""

    @pytest.mark.asyncio
    async def test_orchestrator_simple_task(self, mock_llm_client, executor, security):
        """간단한 태스크 실행 - 성공"""
        orchestrator = AgentOrchestrator(
            llm_client=mock_llm_client,
            executor=executor,
            security=security,
            max_iterations=5
        )

        events = []
        async for event in orchestrator.execute_task(
            task_id="test-123",
            user_request="Complete the task",
            workspace_path=executor.workspace_path
        ):
            events.append(event)

        # 이벤트 확인
        event_types = [e["type"] for e in events]

        assert "iteration_start" in event_types
        assert "action_start" in event_types
        # finish 도구는 특별한 도구이므로 action_success가 아닐 수 있음
        assert "task_completed" in event_types or "task_failed" in event_types

    @pytest.mark.asyncio
    async def test_orchestrator_max_iterations(self, executor, security):
        """최대 반복 도달 - 실패"""
        # LLM이 finish를 호출하지 않도록 설정
        mock_llm = Mock()
        mock_llm.get_next_actions = Mock(return_value=AgentResponse(
            reasoning="Continue working",
            actions=[{"tool": "list_files", "params": {"path": "src"}}],
            raw_response='{"reasoning": "Continue", "actions": [{"tool": "list_files"}]}'
        ))

        orchestrator = AgentOrchestrator(
            llm_client=mock_llm,
            executor=executor,
            security=security,
            max_iterations=2  # 매우 작은 값
        )

        events = []
        async for event in orchestrator.execute_task(
            task_id="test-max",
            user_request="Never ending task",
            workspace_path=executor.workspace_path
        ):
            events.append(event)

        # 마지막 이벤트가 task_failed여야 함
        assert events[-1]["type"] == "task_failed"
        assert "Max iterations" in events[-1]["error"]

    @pytest.mark.asyncio
    async def test_orchestrator_security_violation(self, executor, security):
        """보안 위반 - 실패"""
        # 보안 위반 액션 반환하는 LLM
        mock_llm = Mock()
        mock_llm.get_next_actions = Mock(return_value=AgentResponse(
            reasoning="Try to access .env",
            actions=[{"tool": "read_file", "params": {"path": ".env"}}],
            raw_response='{"reasoning": "Access .env", "actions": [{"tool": "read_file"}]}'
        ))

        orchestrator = AgentOrchestrator(
            llm_client=mock_llm,
            executor=executor,
            security=security
        )

        events = []
        async for event in orchestrator.execute_task(
            task_id="test-security",
            user_request="Read .env file",
            workspace_path=executor.workspace_path
        ):
            events.append(event)

        # 보안 위반 이벤트 확인
        event_types = [e["type"] for e in events]
        assert "security_violation" in event_types or "task_failed" in event_types

    @pytest.mark.asyncio
    async def test_orchestrator_tool_failure(self, executor, security):
        """도구 실행 실패 - 재시도"""
        # 존재하지 않는 파일 읽기 시도 후 finish
        call_count = 0

        def mock_get_actions(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # 첫 번째: 실패할 액션
                return AgentResponse(
                    reasoning="Read nonexistent file",
                    actions=[{"tool": "read_file", "params": {"path": "src/nonexistent.py"}}],
                    raw_response='{"actions": [{"tool": "read_file"}]}'
                )
            else:
                # 두 번째: 완료
                return AgentResponse(
                    reasoning="Finish",
                    actions=[{"tool": "finish", "params": {"success": False}}],
                    raw_response='{"actions": [{"tool": "finish"}]}'
                )

        mock_llm = Mock()
        mock_llm.get_next_actions = Mock(side_effect=mock_get_actions)

        orchestrator = AgentOrchestrator(
            llm_client=mock_llm,
            executor=executor,
            security=security
        )

        events = []
        async for event in orchestrator.execute_task(
            task_id="test-failure",
            user_request="Read and finish",
            workspace_path=executor.workspace_path
        ):
            events.append(event)

        # action_failed 이벤트가 있어야 함
        event_types = [e["type"] for e in events]
        assert "action_failed" in event_types


class TestTaskState:
    """TaskState 테스트"""

    def test_task_state_creation(self):
        """TaskState 생성 - 성공"""
        from src.agent.memory.task_state import TaskState, TaskStatus

        state = TaskState(
            task_id="test-1",
            user_request="Test request",
            workspace_path="/workspace"
        )

        assert state.task_id == "test-1"
        assert state.status == TaskStatus.PENDING
        assert state.result is None

    def test_task_state_lifecycle(self):
        """TaskState 생명주기 - 성공"""
        from src.agent.memory.task_state import TaskState, TaskStatus

        state = TaskState(
            task_id="test-2",
            user_request="Test",
            workspace_path="/workspace"
        )

        # 시작
        state.start()
        assert state.status == TaskStatus.RUNNING
        assert state.started_at is not None

        # 반복 추가
        state.add_iteration(
            iteration=1,
            reasoning="Test reasoning",
            actions=[{"tool": "read_file"}],
            results=[{"success": True}]
        )
        assert state.get_iteration_count() == 1

        # 완료
        state.complete({"message": "Done"})
        assert state.status == TaskStatus.COMPLETED
        assert state.result == {"message": "Done"}
        assert state.completed_at is not None

    def test_task_state_to_dict(self):
        """TaskState 딕셔너리 변환 - 성공"""
        from src.agent.memory.task_state import TaskState

        state = TaskState(
            task_id="test-3",
            user_request="Test",
            workspace_path="/workspace"
        )
        state.start()

        data = state.to_dict()

        assert data["task_id"] == "test-3"
        assert data["status"] == "running"
        assert "started_at" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
