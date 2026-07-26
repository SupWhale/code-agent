"""
Chat WebSocket Route

/ws/chat(순수 LLM 채팅, 툴 실행 없음) 엔드포인트와 연결·대화 기록 관리자.

에이전트 툴 실행이 필요한 워크스페이스 세션은 이것과 별개로
agent/session_manager.py의 SessionManager가 담당한다 — 여기 ConnectionManager는
디스크에 아무것도 쓰지 않는 순수 인메모리 채팅 히스토리다.
"""

import json
import logging
from typing import Dict, List

import ollama
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from prometheus_client import Gauge

from ..auth import authenticate_websocket
from ..logging_setup import bind_new_request_id
from ..rate_limit import check_ws_rate_limit

logger = logging.getLogger(__name__)

active_websockets = Gauge('active_websockets', 'Number of active WebSocket connections')


class ConnectionManager:
    """/ws/chat 전용 연결·대화 기록 관리자."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.conversation_history: Dict[str, List[Dict]] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections.append(websocket)
        active_websockets.inc()

        # 대화 히스토리 초기화
        if client_id not in self.conversation_history:
            self.conversation_history[client_id] = []

        logger.info(f"WebSocket 연결: {client_id}, 총 연결: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket, client_id: str):
        # 예외 경로에서 중복 호출될 수 있으므로 멱등하게 처리
        if websocket not in self.active_connections:
            return
        self.active_connections.remove(websocket)
        active_websockets.dec()
        logger.info(f"WebSocket 연결 종료: {client_id}, 총 연결: {len(self.active_connections)}")

    async def send_message(self, message: dict, websocket: WebSocket):
        await websocket.send_text(json.dumps(message, ensure_ascii=False))

    def add_to_history(self, client_id: str, role: str, content: str):
        self.conversation_history[client_id].append({
            "role": role,
            "content": content
        })

        # 히스토리 크기 제한 (최대 20개)
        if len(self.conversation_history[client_id]) > 20:
            self.conversation_history[client_id] = self.conversation_history[client_id][-20:]


def init_chat_router(async_client: ollama.AsyncClient, model_name: str) -> APIRouter:
    """
    Chat 라우터 초기화

    Args:
        async_client: Ollama 비동기 클라이언트
        model_name: 사용할 모델 이름

    Returns:
        설정된 APIRouter

    Note:
        WebSocket 인증은 다른 WebSocket 엔드포인트들과 동일하게 수동으로 처리한다 —
        accept() 호출 전에 authenticate_websocket()으로 먼저 검증한다. 라우터 레벨
        dependencies=[Depends(require_api_key)]를 절대 추가하지 말 것: require_api_key가
        의존하는 HTTPBearer는 HTTP Request 객체를 요구하는데, FastAPI가 WebSocket 연결에
        대해 이를 resolve하려 하면 TypeError가 발생해 WebSocket 핸드셰이크가 HTTP 500으로
        깨진다 — 실제로 이 문제로 프로덕션에서 이 라우트가 장애를 일으킨 적이 있다.
    """
    router = APIRouter(tags=["chat"])
    manager = ConnectionManager()

    @router.websocket("/ws/chat")
    async def websocket_chat(websocket: WebSocket, client_id: str = Query(default="default")):
        """WebSocket 채팅"""
        bind_new_request_id()
        identity = await authenticate_websocket(websocket)
        if identity is None:
            await websocket.close(code=1008)
            return
        if not check_ws_rate_limit(identity.key):
            await websocket.close(code=1013)
            return

        await manager.connect(websocket, client_id)

        try:
            while True:
                # 메시지 수신
                data = await websocket.receive_text()
                message_data = json.loads(data)

                user_message = message_data.get("message", "")

                if not user_message:
                    await manager.send_message({"type": "error", "data": "메시지가 비어있습니다"}, websocket)
                    continue

                # 히스토리에 추가
                manager.add_to_history(client_id, "user", user_message)

                # Ollama로 응답 생성 (스트리밍)
                try:
                    response = await async_client.chat(
                        model=model_name,
                        messages=manager.conversation_history[client_id],
                        stream=True
                    )

                    full_response = ""
                    buffer = ""

                    async for chunk in response:
                        content = chunk.get("message", {}).get("content", "")
                        buffer += content
                        full_response += content

                        # 버퍼링 (10글자 단위 또는 줄바꿈)
                        if len(buffer) >= 10 or "\n" in buffer:
                            await manager.send_message({"type": "content", "data": buffer}, websocket)
                            buffer = ""

                    # 남은 버퍼 전송
                    if buffer:
                        await manager.send_message({"type": "content", "data": buffer}, websocket)

                    # 완료 신호
                    await manager.send_message({"type": "done"}, websocket)

                    # 히스토리에 추가
                    manager.add_to_history(client_id, "assistant", full_response)

                except Exception as e:
                    logger.error(f"응답 생성 실패: {e}")
                    await manager.send_message({"type": "error", "data": str(e)}, websocket)

        except WebSocketDisconnect:
            manager.disconnect(websocket, client_id)
        except Exception as e:
            logger.error(f"WebSocket 에러: {e}")
            manager.disconnect(websocket, client_id)

    return router
