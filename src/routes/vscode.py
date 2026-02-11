"""
VS Code Extension API Routes

VS Code Extension을 위한 WebSocket 및 HTTP 엔드포인트
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import json
import logging
from datetime import datetime

from ..agent.session_manager import SessionManager
from ..agent.task_manager import TaskManager
from ..agent.orchestrator import AgentOrchestrator

logger = logging.getLogger(__name__)

# 전역 SessionManager (나중에 의존성 주입으로 변경 가능)
_session_manager: Optional[SessionManager] = None


def init_vscode_router(
    session_manager: SessionManager,
    task_manager: TaskManager,
    orchestrator: AgentOrchestrator
) -> APIRouter:
    """
    VS Code 라우터 초기화

    Args:
        session_manager: SessionManager 인스턴스
        task_manager: TaskManager 인스턴스
        orchestrator: AgentOrchestrator 인스턴스

    Returns:
        설정된 APIRouter
    """
    global _session_manager
    _session_manager = session_manager

    router = APIRouter(prefix="/api/v1/vscode", tags=["vscode"])

    # Request/Response 모델
    class CreateSessionRequest(BaseModel):
        """세션 생성 요청"""
        session_id: Optional[str] = Field(None, description="세션 ID (생략 시 자동 생성)")

    class SessionResponse(BaseModel):
        """세션 응답"""
        session_id: str
        workspace_path: str
        file_count: int
        created_at: str
        last_activity: str

    class UploadFileRequest(BaseModel):
        """파일 업로드 요청"""
        path: str = Field(..., description="파일 경로")
        content: str = Field(..., description="파일 내용")

    class UploadFilesRequest(BaseModel):
        """여러 파일 업로드 요청"""
        files: List[UploadFileRequest]

    class AgentRequest(BaseModel):
        """Agent 작업 요청"""
        user_request: str = Field(..., description="사용자 요청")
        context: Optional[Dict[str, Any]] = Field(None, description="컨텍스트 정보")

    # HTTP 엔드포인트
    @router.post("/session", response_model=SessionResponse, status_code=201)
    async def create_session(request: CreateSessionRequest):
        """
        새 세션 생성

        클라이언트별 격리된 workspace를 생성합니다.
        """
        try:
            session = _session_manager.create_session(request.session_id)

            logger.info(f"Session created via API: {session.session_id}")

            return SessionResponse(
                session_id=session.session_id,
                workspace_path=str(session.workspace_path),
                file_count=session.get_file_count(),
                created_at=session.created_at.isoformat(),
                last_activity=session.last_activity.isoformat()
            )

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/session/{session_id}", response_model=SessionResponse)
    async def get_session(session_id: str):
        """
        세션 정보 조회
        """
        session = _session_manager.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        return SessionResponse(
            session_id=session.session_id,
            workspace_path=str(session.workspace_path),
            file_count=session.get_file_count(),
            created_at=session.created_at.isoformat(),
            last_activity=session.last_activity.isoformat()
        )

    @router.delete("/session/{session_id}", status_code=204)
    async def delete_session(session_id: str):
        """
        세션 삭제

        세션과 관련된 모든 파일이 삭제됩니다.
        """
        result = _session_manager.delete_session(session_id)

        if not result:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        return None

    @router.post("/session/{session_id}/files", status_code=201)
    async def upload_files(session_id: str, request: UploadFilesRequest):
        """
        여러 파일 업로드

        세션에 여러 파일을 한 번에 업로드합니다.
        """
        session = _session_manager.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        uploaded_count = 0
        for file_req in request.files:
            success = _session_manager.add_file_to_session(
                session_id,
                file_req.path,
                file_req.content
            )
            if success:
                uploaded_count += 1

        logger.info(f"Session {session_id}: Uploaded {uploaded_count} files")

        return {
            "session_id": session_id,
            "uploaded_count": uploaded_count,
            "total_files": session.get_file_count()
        }

    @router.get("/session/{session_id}/files")
    async def list_files(session_id: str):
        """
        파일 목록 조회

        세션의 모든 파일 목록을 반환합니다.
        """
        session = _session_manager.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        files = session.list_files()

        return {
            "session_id": session_id,
            "files": files,
            "count": len(files)
        }

    @router.get("/session/{session_id}/file")
    async def get_file(session_id: str, path: str):
        """
        파일 내용 조회

        특정 파일의 내용을 반환합니다.
        """
        content = _session_manager.get_file_from_session(session_id, path)

        if content is None:
            raise HTTPException(
                status_code=404,
                detail=f"File {path} not found in session {session_id}"
            )

        return {
            "session_id": session_id,
            "path": path,
            "content": content,
            "size": len(content)
        }

    @router.get("/sessions/stats")
    async def get_stats():
        """
        세션 통계 조회
        """
        return _session_manager.get_stats()

    # WebSocket 엔드포인트
    @router.websocket("/ws/{session_id}")
    async def vscode_websocket(websocket: WebSocket, session_id: str):
        """
        VS Code Extension용 WebSocket

        실시간 양방향 통신을 위한 WebSocket 엔드포인트
        """
        await websocket.accept()
        logger.info(f"WebSocket connection established for session: {session_id}")

        try:
            # 세션 확인 (없으면 자동 생성)
            session = _session_manager.get_session(session_id)
            if not session:
                session = _session_manager.create_session(session_id)
                await websocket.send_json({
                    "type": "session_created",
                    "session_id": session_id,
                    "workspace_path": str(session.workspace_path)
                })

            # 연결 성공 메시지
            await websocket.send_json({
                "type": "connected",
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
            })

            # 메시지 수신 루프
            while True:
                message = await websocket.receive_json()
                message_type = message.get("type")

                # 메시지 타입별 처리
                if message_type == "file_upload":
                    # 파일 업로드
                    files = message.get("files", [])
                    for file_info in files:
                        _session_manager.add_file_to_session(
                            session_id,
                            file_info["path"],
                            file_info["content"]
                        )

                    await websocket.send_json({
                        "type": "files_uploaded",
                        "count": len(files),
                        "total_files": session.get_file_count()
                    })

                elif message_type == "agent_request":
                    # Agent 작업 요청
                    user_request = message.get("user_request")
                    context = message.get("context", {})

                    # TaskManager를 통해 작업 생성
                    task = task_manager.create_task(
                        task_id=f"{session_id}-{datetime.now().timestamp()}",
                        user_request=user_request,
                        workspace_path=str(session.workspace_path)
                    )

                    await websocket.send_json({
                        "type": "task_created",
                        "task_id": task.task_id
                    })

                    # 작업 실행 및 이벤트 스트리밍
                    async for event in task_manager.execute_task(task.task_id):
                        await websocket.send_json({
                            "type": "agent_event",
                            "event": event
                        })

                        # 파일 변경 이벤트 처리
                        if event.get("type") == "action_success":
                            action_type = event.get("action", {}).get("tool")
                            if action_type == "edit_file":
                                file_path = event.get("action", {}).get("params", {}).get("path")
                                if file_path:
                                    # 변경된 파일 내용 전송
                                    new_content = session.get_file(file_path)
                                    if new_content:
                                        await websocket.send_json({
                                            "type": "file_changed",
                                            "path": file_path,
                                            "content": new_content
                                        })

                elif message_type == "ping":
                    # 연결 유지용 ping
                    session.update_activity()
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    })

                else:
                    # 알 수 없는 메시지 타입
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Unknown message type: {message_type}"
                    })

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for session: {session_id}")
        except Exception as e:
            logger.error(f"WebSocket error for session {session_id}: {e}")
            try:
                await websocket.send_json({
                    "type": "error",
                    "error": str(e)
                })
            except:
                pass
        finally:
            try:
                await websocket.close()
            except:
                pass

    return router
