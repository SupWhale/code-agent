"""
Tests for Agent API

Tests FastAPI endpoints for agent task management.
"""

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from unittest.mock import Mock, AsyncMock
from pathlib import Path
import tempfile

from src.agent.task_manager import TaskManager
from src.agent.orchestrator import AgentOrchestrator
from src.agent.executor import ToolExecutor
from src.agent.security.validator import SecurityValidator
from src.agent.llm.ollama_client import AgentResponse
from src.routes.agent import init_agent_router


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
    client.get_next_actions = Mock(return_value=AgentResponse(
        reasoning="Task completed",
        actions=[{"tool": "finish", "params": {"success": True, "message": "Done"}}],
        raw_response='{"reasoning": "Task completed", "actions": [{"tool": "finish"}]}'
    ))
    return client


@pytest.fixture
def test_app(temp_workspace, mock_llm_client):
    """테스트용 FastAPI 앱"""
    # Agent 시스템 초기화
    security = SecurityValidator(temp_workspace, strict_mode=True)
    executor = ToolExecutor(temp_workspace)
    orchestrator = AgentOrchestrator(
        llm_client=mock_llm_client,
        executor=executor,
        security=security
    )
    task_manager = TaskManager(orchestrator=orchestrator)

    # FastAPI 앱 생성
    app = FastAPI()
    agent_router = init_agent_router(task_manager)
    app.include_router(agent_router)

    return app


@pytest.fixture
def client(test_app):
    """TestClient 인스턴스"""
    return TestClient(test_app)


class TestTaskCreation:
    """작업 생성 API 테스트"""

    def test_create_task(self, client, temp_workspace):
        """작업 생성 - 성공"""
        response = client.post("/api/v1/agent/task", json={
            "user_request": "Add type hints to test.py",
            "workspace_path": temp_workspace
        })

        assert response.status_code == 201
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        assert data["user_request"] == "Add type hints to test.py"

    def test_create_task_with_custom_id(self, client, temp_workspace):
        """커스텀 ID로 작업 생성 - 성공"""
        response = client.post("/api/v1/agent/task", json={
            "user_request": "Test request",
            "workspace_path": temp_workspace,
            "task_id": "custom-task-123"
        })

        assert response.status_code == 201
        data = response.json()
        assert data["task_id"] == "custom-task-123"

    def test_create_task_missing_fields(self, client):
        """필수 필드 누락 - 실패"""
        response = client.post("/api/v1/agent/task", json={
            "user_request": "Test"
            # workspace_path 누락
        })

        assert response.status_code == 422  # Validation error

    def test_create_duplicate_task_id(self, client, temp_workspace):
        """중복 task_id - 실패"""
        # 첫 번째 작업 생성
        client.post("/api/v1/agent/task", json={
            "user_request": "Test 1",
            "workspace_path": temp_workspace,
            "task_id": "duplicate-id"
        })

        # 같은 ID로 두 번째 작업 생성 시도
        response = client.post("/api/v1/agent/task", json={
            "user_request": "Test 2",
            "workspace_path": temp_workspace,
            "task_id": "duplicate-id"
        })

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]


class TestTaskRetrieval:
    """작업 조회 API 테스트"""

    def test_get_task(self, client, temp_workspace):
        """작업 조회 - 성공"""
        # 작업 생성
        create_response = client.post("/api/v1/agent/task", json={
            "user_request": "Test request",
            "workspace_path": temp_workspace
        })
        task_id = create_response.json()["task_id"]

        # 작업 조회
        response = client.get(f"/api/v1/agent/task/{task_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["status"] == "pending"

    def test_get_nonexistent_task(self, client):
        """존재하지 않는 작업 조회 - 실패"""
        response = client.get("/api/v1/agent/task/nonexistent-id")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_list_all_tasks(self, client, temp_workspace):
        """모든 작업 목록 조회 - 성공"""
        # 여러 작업 생성
        for i in range(3):
            client.post("/api/v1/agent/task", json={
                "user_request": f"Request {i}",
                "workspace_path": temp_workspace
            })

        # 목록 조회
        response = client.get("/api/v1/agent/tasks")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["tasks"]) == 3
        assert "stats" in data

    def test_list_tasks_by_status(self, client, temp_workspace):
        """상태별 작업 목록 조회 - 성공"""
        # 작업 생성
        client.post("/api/v1/agent/task", json={
            "user_request": "Test",
            "workspace_path": temp_workspace
        })

        # pending 상태 작업 조회
        response = client.get("/api/v1/agent/tasks?status=pending")

        assert response.status_code == 200
        data = response.json()
        assert all(task["status"] == "pending" for task in data["tasks"])

    def test_list_tasks_invalid_status(self, client):
        """잘못된 상태 필터 - 실패"""
        response = client.get("/api/v1/agent/tasks?status=invalid_status")

        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]


class TestTaskDeletion:
    """작업 삭제 API 테스트"""

    def test_delete_task(self, client, temp_workspace):
        """작업 삭제 - 성공"""
        # 작업 생성
        create_response = client.post("/api/v1/agent/task", json={
            "user_request": "Test",
            "workspace_path": temp_workspace
        })
        task_id = create_response.json()["task_id"]

        # 작업 삭제
        response = client.delete(f"/api/v1/agent/task/{task_id}")

        assert response.status_code == 204

        # 삭제 확인
        get_response = client.get(f"/api/v1/agent/task/{task_id}")
        assert get_response.status_code == 404

    def test_delete_nonexistent_task(self, client):
        """존재하지 않는 작업 삭제 - 실패"""
        response = client.delete("/api/v1/agent/task/nonexistent-id")

        assert response.status_code == 404


class TestTaskExecution:
    """작업 실행 API 테스트"""

    def test_execute_task_sse(self, client, temp_workspace):
        """작업 실행 (SSE) - 성공"""
        # 작업 생성
        create_response = client.post("/api/v1/agent/task", json={
            "user_request": "Test request",
            "workspace_path": temp_workspace
        })
        task_id = create_response.json()["task_id"]

        # 작업 실행 (SSE 스트림)
        with client.stream("POST", f"/api/v1/agent/task/{task_id}/execute") as response:
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

            # 첫 번째 이벤트 읽기
            events = []
            for line in response.iter_lines():
                if line.startswith("data: "):
                    import json
                    event_data = json.loads(line[6:])  # "data: " 제거
                    events.append(event_data)
                    if event_data.get("type") in ["task_completed", "task_failed"]:
                        break

            assert len(events) > 0
            assert any(e["type"] == "task_completed" for e in events)

    def test_execute_nonexistent_task(self, client):
        """존재하지 않는 작업 실행 - 실패"""
        response = client.post("/api/v1/agent/task/nonexistent-id/execute")

        assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
