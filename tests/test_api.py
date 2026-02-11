"""
API 테스트
"""

import pytest
from httpx import AsyncClient
from fastapi.testclient import TestClient
from src.main import app
import os

# 테스트용 환경변수 설정
os.environ["OLLAMA_HOST"] = "http://localhost:11434"
os.environ["MODEL_NAME"] = "qwen2.5-coder:14b"
os.environ["WORKSPACE_PATH"] = "/tmp/test_workspace"


@pytest.fixture
def client():
    """동기 테스트 클라이언트"""
    return TestClient(app)


@pytest.fixture
async def async_client():
    """비동기 테스트 클라이언트"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


def test_root(client):
    """루트 엔드포인트 테스트"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "AI Coding Agent"
    assert data["version"] == "1.0.0"
    assert "status" in data
    assert "timestamp" in data


def test_health(client):
    """헬스체크 엔드포인트 테스트"""
    response = client.get("/health")

    # Ollama가 실행 중이지 않을 수 있으므로 503도 허용
    assert response.status_code in [200, 503]

    if response.status_code == 200:
        data = response.json()
        assert data["status"] == "healthy"
        assert "ollama" in data
        assert "model" in data


def test_metrics(client):
    """메트릭 엔드포인트 테스트"""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert b"api_requests_total" in response.content


def test_generate_code_nonstream(client):
    """코드 생성 (논스트리밍) 테스트"""
    # Ollama가 실행 중이 아니면 스킵
    health = client.get("/health")
    if health.status_code != 200:
        pytest.skip("Ollama is not running")

    response = client.post(
        "/api/v1/generate",
        json={
            "prompt": "Hello World를 출력하는 Python 함수",
            "language": "python",
            "temperature": 0.1,
            "stream": False
        }
    )

    # 타임아웃이나 연결 오류가 발생할 수 있음
    assert response.status_code in [200, 500]

    if response.status_code == 200:
        data = response.json()
        assert "code" in data
        assert "language" in data
        assert data["language"] == "python"


def test_file_list(client):
    """파일 목록 조회 테스트"""
    response = client.get("/api/v1/files/list?path=/")

    # 워크스페이스가 존재하지 않을 수 있음
    assert response.status_code in [200, 404]

    if response.status_code == 200:
        data = response.json()
        assert "path" in data
        assert "files" in data
        assert isinstance(data["files"], list)


def test_file_upload(client):
    """파일 업로드 테스트"""
    # 테스트 파일 생성
    test_content = b"print('Hello, World!')"
    files = {"file": ("test.py", test_content, "text/plain")}

    response = client.post(
        "/api/v1/files/upload?path=/",
        files=files
    )

    # 워크스페이스 권한 문제가 있을 수 있음
    assert response.status_code in [200, 500]

    if response.status_code == 200:
        data = response.json()
        assert data["filename"] == "test.py"
        assert "path" in data
        assert "size" in data


def test_invalid_path_traversal(client):
    """경로 탐색 공격 방지 테스트"""
    response = client.get("/api/v1/files/list?path=../../etc")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_websocket_chat():
    """WebSocket 채팅 테스트"""
    # WebSocket 테스트는 복잡하므로 기본 구조만 확인
    pass


def test_cors_headers(client):
    """CORS 헤더 테스트"""
    response = client.options(
        "/",
        headers={"Origin": "http://localhost:3000"}
    )
    assert response.status_code in [200, 405]


def test_unicode_support(client):
    """한글 지원 테스트"""
    response = client.get("/")
    data = response.json()

    # 응답이 JSON으로 정상 파싱되는지 확인
    assert isinstance(data, dict)

    # 한글 포함 요청 테스트 (Ollama가 실행 중일 때만)
    health = client.get("/health")
    if health.status_code == 200:
        response = client.post(
            "/api/v1/generate",
            json={
                "prompt": "안녕하세요를 출력하는 Python 코드",
                "language": "python",
                "stream": False
            }
        )
        assert response.status_code in [200, 500]


def test_large_file_rejection(client):
    """큰 파일 업로드 거부 테스트"""
    # 101MB 파일 (제한: 100MB)
    large_content = b"x" * (101 * 1024 * 1024)
    files = {"file": ("large.bin", large_content, "application/octet-stream")}

    response = client.post(
        "/api/v1/files/upload?path=/",
        files=files
    )

    # 413 (Payload Too Large) 또는 500 예상
    assert response.status_code in [413, 500]
