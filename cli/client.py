"""
FastAPI 백엔드 HTTP + WebSocket 클라이언트
"""

import json
from typing import AsyncIterator, Optional

import httpx
import websockets
import websockets.exceptions

from . import config


class AgentClient:
    def __init__(self, server_url: Optional[str] = None):
        self.server_url = (server_url or config.get("server_url") or "http://localhost:8000").rstrip("/")
        self.ws_url = self.server_url.replace("http://", "ws://").replace("https://", "wss://")

    # ── Health ──────────────────────────────────────────────────────────────

    def health(self) -> dict:
        resp = httpx.get(f"{self.server_url}/health", timeout=5)
        resp.raise_for_status()
        return resp.json()

    # ── Session ─────────────────────────────────────────────────────────────

    def create_session(self, session_id: Optional[str] = None) -> dict:
        body = {"session_id": session_id} if session_id else {}
        resp = httpx.post(f"{self.server_url}/api/v1/vscode/session", json=body, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def list_sessions(self) -> list[dict]:
        resp = httpx.get(f"{self.server_url}/api/v1/vscode/sessions", timeout=5)
        resp.raise_for_status()
        return resp.json().get("sessions", [])

    def get_session(self, session_id: str) -> Optional[dict]:
        resp = httpx.get(f"{self.server_url}/api/v1/vscode/session/{session_id}", timeout=5)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def delete_session(self, session_id: str) -> None:
        resp = httpx.delete(f"{self.server_url}/api/v1/vscode/session/{session_id}", timeout=5)
        resp.raise_for_status()

    # ── Files ────────────────────────────────────────────────────────────────

    def list_files(self, session_id: str) -> list[dict]:
        resp = httpx.get(f"{self.server_url}/api/v1/vscode/session/{session_id}/files", timeout=5)
        resp.raise_for_status()
        return resp.json().get("files", [])

    def get_file(self, session_id: str, path: str) -> Optional[str]:
        resp = httpx.get(
            f"{self.server_url}/api/v1/vscode/session/{session_id}/file",
            params={"path": path},
            timeout=5,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("content")

    def upload_files(self, session_id: str, files: list[dict]) -> dict:
        """files: [{"path": "...", "content": "..."}]"""
        resp = httpx.post(
            f"{self.server_url}/api/v1/vscode/session/{session_id}/files",
            json={"files": files},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Agent (WebSocket streaming) ──────────────────────────────────────────

    async def run_agent(self, session_id: str, user_request: str) -> AsyncIterator[dict]:
        """
        WebSocket으로 에이전트 실행 — 이벤트를 비동기 yield
        """
        uri = f"{self.ws_url}/api/v1/vscode/ws/{session_id}"
        async with websockets.connect(uri, ping_interval=20, ping_timeout=30) as ws:
            # 연결 확인 메시지 수신
            raw = await ws.recv()
            msg = json.loads(raw)
            if msg.get("type") in ("connected", "session_created"):
                pass  # 정상

            # 작업 요청 전송
            await ws.send(json.dumps({
                "type": "agent_request",
                "user_request": user_request,
            }))

            # 스트림 수신
            async for raw in ws:
                msg = json.loads(raw)
                yield msg
                # 작업 종료 감지
                if msg.get("type") == "agent_event":
                    event = msg.get("event", {})
                    if event.get("type") in ("task_completed", "task_failed", "finish"):
                        break
