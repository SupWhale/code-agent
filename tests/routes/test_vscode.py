"""
Tests for VS Code Extension API Routes

VS Code Extension을 위한 HTTP 및 WebSocket 엔드포인트 테스트
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import tempfile
import json
import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.agent.session_manager import SessionManager
from src.agent.task_manager import TaskManager
from src.agent.orchestrator import AgentOrchestrator
from src.routes.vscode import init_vscode_router


@pytest.fixture
def temp_workspace():
    """임시 workspace"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def session_manager(temp_workspace):
    """SessionManager 인스턴스"""
    return SessionManager(temp_workspace)


@pytest.fixture
def test_client(session_manager, temp_workspace):
    """TestClient with VS Code router"""
    # 테스트용 FastAPI 앱 생성
    app = FastAPI()

    # TaskManager와 Orchestrator는 None으로 설정
    # (실제 agent 요청 테스트는 제외하고, 세션 관리 기능만 테스트)
    task_manager = None
    orchestrator = None

    # VS Code 라우터 초기화 및 추가
    vscode_router = init_vscode_router(session_manager, task_manager, orchestrator)
    app.include_router(vscode_router)

    return TestClient(app)


class TestSessionEndpoints:
    """세션 관리 엔드포인트 테스트"""

    def test_create_session_with_id(self, test_client):
        """세션 생성 - ID 지정"""
        response = test_client.post(
            "/api/v1/vscode/session",
            json={"session_id": "my-session"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["session_id"] == "my-session"
        assert data["file_count"] == 0
        assert "workspace_path" in data
        assert "created_at" in data

    def test_create_session_auto_id(self, test_client):
        """세션 생성 - ID 자동 생성"""
        response = test_client.post(
            "/api/v1/vscode/session",
            json={}
        )

        assert response.status_code == 201
        data = response.json()
        assert len(data["session_id"]) > 0
        assert data["file_count"] == 0

    def test_create_duplicate_session(self, test_client):
        """세션 생성 - 중복 ID"""
        # 첫 번째 세션 생성
        test_client.post(
            "/api/v1/vscode/session",
            json={"session_id": "duplicate"}
        )

        # 동일한 ID로 재시도
        response = test_client.post(
            "/api/v1/vscode/session",
            json={"session_id": "duplicate"}
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_get_session(self, test_client):
        """세션 조회 - 성공"""
        # 세션 생성
        test_client.post(
            "/api/v1/vscode/session",
            json={"session_id": "test-get"}
        )

        # 세션 조회
        response = test_client.get("/api/v1/vscode/session/test-get")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-get"

    def test_get_nonexistent_session(self, test_client):
        """세션 조회 - 존재하지 않음"""
        response = test_client.get("/api/v1/vscode/session/nonexistent")

        assert response.status_code == 404

    def test_delete_session(self, test_client):
        """세션 삭제 - 성공"""
        # 세션 생성
        test_client.post(
            "/api/v1/vscode/session",
            json={"session_id": "test-delete"}
        )

        # 세션 삭제
        response = test_client.delete("/api/v1/vscode/session/test-delete")

        assert response.status_code == 204

        # 삭제 확인
        response = test_client.get("/api/v1/vscode/session/test-delete")
        assert response.status_code == 404

    def test_delete_nonexistent_session(self, test_client):
        """세션 삭제 - 존재하지 않음"""
        response = test_client.delete("/api/v1/vscode/session/nonexistent")

        assert response.status_code == 404


class TestFileEndpoints:
    """파일 관리 엔드포인트 테스트"""

    def test_upload_files(self, test_client):
        """파일 업로드 - 성공"""
        # 세션 생성
        test_client.post(
            "/api/v1/vscode/session",
            json={"session_id": "test-upload"}
        )

        # 파일 업로드
        response = test_client.post(
            "/api/v1/vscode/session/test-upload/files",
            json={
                "files": [
                    {"path": "test1.py", "content": "print('hello')"},
                    {"path": "test2.py", "content": "print('world')"}
                ]
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["session_id"] == "test-upload"
        assert data["uploaded_count"] == 2
        assert data["total_files"] == 2

    def test_upload_files_to_nonexistent_session(self, test_client):
        """파일 업로드 - 세션 없음"""
        response = test_client.post(
            "/api/v1/vscode/session/nonexistent/files",
            json={
                "files": [
                    {"path": "test.py", "content": "content"}
                ]
            }
        )

        assert response.status_code == 404

    def test_list_files(self, test_client):
        """파일 목록 조회 - 성공"""
        # 세션 생성 및 파일 업로드
        test_client.post(
            "/api/v1/vscode/session",
            json={"session_id": "test-list"}
        )
        test_client.post(
            "/api/v1/vscode/session/test-list/files",
            json={
                "files": [
                    {"path": "file1.py", "content": "content1"},
                    {"path": "file2.py", "content": "content2"}
                ]
            }
        )

        # 파일 목록 조회
        response = test_client.get("/api/v1/vscode/session/test-list/files")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-list"
        assert data["count"] == 2
        assert "file1.py" in data["files"]
        assert "file2.py" in data["files"]

    def test_list_files_nonexistent_session(self, test_client):
        """파일 목록 조회 - 세션 없음"""
        response = test_client.get("/api/v1/vscode/session/nonexistent/files")

        assert response.status_code == 404

    def test_get_file(self, test_client):
        """파일 조회 - 성공"""
        # 세션 생성 및 파일 업로드
        test_client.post(
            "/api/v1/vscode/session",
            json={"session_id": "test-file"}
        )
        test_client.post(
            "/api/v1/vscode/session/test-file/files",
            json={
                "files": [
                    {"path": "myfile.py", "content": "test content"}
                ]
            }
        )

        # 파일 조회
        response = test_client.get(
            "/api/v1/vscode/session/test-file/file",
            params={"path": "myfile.py"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-file"
        assert data["path"] == "myfile.py"
        assert data["content"] == "test content"
        assert data["size"] == len("test content")

    def test_get_nonexistent_file(self, test_client):
        """파일 조회 - 파일 없음"""
        # 세션 생성
        test_client.post(
            "/api/v1/vscode/session",
            json={"session_id": "test-file"}
        )

        # 존재하지 않는 파일 조회
        response = test_client.get(
            "/api/v1/vscode/session/test-file/file",
            params={"path": "nonexistent.py"}
        )

        assert response.status_code == 404


class TestStatsEndpoint:
    """통계 엔드포인트 테스트"""

    def test_get_stats(self, test_client):
        """통계 조회 - 성공"""
        # 여러 세션 생성 및 파일 업로드
        for i in range(3):
            session_id = f"session-{i}"
            test_client.post(
                "/api/v1/vscode/session",
                json={"session_id": session_id}
            )
            test_client.post(
                f"/api/v1/vscode/session/{session_id}/files",
                json={
                    "files": [
                        {"path": f"file{j}.py", "content": f"content{j}"}
                        for j in range(2)
                    ]
                }
            )

        # 통계 조회
        response = test_client.get("/api/v1/vscode/sessions/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_sessions"] >= 3
        assert data["active_sessions"] >= 3
        assert data["total_files"] >= 6


class TestWebSocket:
    """WebSocket 엔드포인트 테스트"""

    def test_websocket_connection(self, test_client):
        """WebSocket 연결 - 성공"""
        with test_client.websocket_connect("/api/v1/vscode/ws/ws-test") as websocket:
            # 연결 성공 메시지 수신
            data = websocket.receive_json()
            assert data["type"] == "session_created"
            assert data["session_id"] == "ws-test"

            # 두 번째 메시지 (connected)
            data = websocket.receive_json()
            assert data["type"] == "connected"
            assert data["session_id"] == "ws-test"

    def test_websocket_file_upload(self, test_client):
        """WebSocket 파일 업로드"""
        with test_client.websocket_connect("/api/v1/vscode/ws/ws-upload") as websocket:
            # 연결 메시지 수신
            websocket.receive_json()  # session_created
            websocket.receive_json()  # connected

            # 파일 업로드
            websocket.send_json({
                "type": "file_upload",
                "files": [
                    {"path": "test.py", "content": "print('hello')"}
                ]
            })

            # 업로드 완료 메시지 수신
            data = websocket.receive_json()
            assert data["type"] == "files_uploaded"
            assert data["count"] == 1

    def test_websocket_ping_pong(self, test_client):
        """WebSocket ping/pong"""
        with test_client.websocket_connect("/api/v1/vscode/ws/ws-ping") as websocket:
            # 연결 메시지 수신
            websocket.receive_json()  # session_created
            websocket.receive_json()  # connected

            # Ping 전송
            websocket.send_json({"type": "ping"})

            # Pong 수신
            data = websocket.receive_json()
            assert data["type"] == "pong"
            assert "timestamp" in data

    def test_websocket_unknown_message(self, test_client):
        """WebSocket 알 수 없는 메시지"""
        with test_client.websocket_connect("/api/v1/vscode/ws/ws-unknown") as websocket:
            # 연결 메시지 수신
            websocket.receive_json()  # session_created
            websocket.receive_json()  # connected

            # 알 수 없는 메시지 타입 전송
            websocket.send_json({"type": "unknown_type"})

            # 에러 메시지 수신
            data = websocket.receive_json()
            assert data["type"] == "error"
            assert "Unknown message type" in data["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
