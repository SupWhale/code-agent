"""
AI Coding Agent - Main Application
FastAPI-based coding assistant powered by Ollama and Qwen2.5-Coder
"""

import os
import asyncio
import functools
import logging
from datetime import datetime
from pathlib import Path

import ollama
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

# Agent imports
from .config import get_settings
from .logging_setup import configure_logging, RequestIDMiddleware
from .rate_limit import limiter
from .agent.executor import ToolExecutor
from .agent.orchestrator import AgentOrchestrator
from .agent.task_manager import TaskManager
from .agent.session_manager import SessionManager, periodic_session_cleanup
from .agent.security.validator import SecurityValidator
from .agent.llm.factory import create_llm_client
from .routes.agent import init_agent_router
from .routes.vscode import init_vscode_router
from .routes.files import init_files_router
from .routes.generate import init_generate_router
from .routes.chat import init_chat_router
from .utils.responses import UnicodeJSONResponse

settings = get_settings()

# 구조화(JSON) 로깅 — 모든 레코드에 request_id가 자동으로 포함된다
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

# Settings (fail-fast validated in src/config.py)
OLLAMA_HOST = settings.ollama_host
MODEL_NAME = settings.model_name
WORKSPACE_PATH = settings.workspace_path
MAX_FILE_SIZE = settings.max_file_size

# 만료된 세션 정리 주기 (초) — SessionManager.cleanup_expired_sessions()를 이 간격으로 호출한다
SESSION_CLEANUP_INTERVAL_SECONDS = 300

# 시스템 프롬프트 경로 — 명시적으로 안 정해져 있으면 저장소에 포함된
# prompts/system_prompt.txt를 기본으로 쓴다. (이게 없으면 OllamaAgentClient가
# 자체 내장된 훨씬 부실한 fallback 프롬프트로 조용히 넘어가므로, 여기서 항상 확실한
# 경로를 넘겨준다.)
SYSTEM_PROMPT_PATH = str(
    settings.system_prompt_path
    or (Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.txt")
)

# FastAPI app
app = FastAPI(
    title="AI Coding Agent",
    description="AI-powered coding assistant using Ollama and Qwen2.5-Coder",
    version="1.0.0"
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware — 명시적 origin 화이트리스트만 허용 (와일드카드 + credentials는 스펙 위반)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request ID — CORS 다음에 등록해 가장 바깥쪽(요청 진입 시 가장 먼저 실행)에서 부여
app.add_middleware(RequestIDMiddleware)

# Agent system (initialized on startup)
app.state.task_manager = None
app.state.agent_initialized = False


@app.on_event("startup")
async def startup_event():
    """
    앱 시작 시 agent 시스템 초기화.

    초기화 실패 시 예외를 그대로 전파해 프로세스를 종료시킨다 — 라우터가 일부만
    등록된 채로 "정상" 헬스체크를 반환하는 상태를 방지하기 위함. 컨테이너
    재시작 정책(restart: unless-stopped)이 재시도를 담당한다.
    """
    logger.info("Initializing agent system...")

    # 1. LLM 클라이언트 초기화 (전략 패턴 — provider/모델은 factory가 조립)
    llm_client_factory = functools.partial(
        create_llm_client,
        settings.llm_provider,
        host=OLLAMA_HOST,
        temperature=0.1,
        system_prompt_path=SYSTEM_PROMPT_PATH
    )
    llm_client = llm_client_factory(MODEL_NAME)

    # 2. 보안 검증기 초기화
    security = SecurityValidator(
        workspace_path=str(WORKSPACE_PATH),
        strict_mode=True
    )

    # 3. 도구 실행기 초기화
    executor = ToolExecutor(
        workspace_path=str(WORKSPACE_PATH),
        enable_shell_tool=settings.enable_shell_tool
    )

    # 4. 오케스트레이터 초기화
    orchestrator = AgentOrchestrator(
        llm_client=llm_client,
        executor=executor,
        security=security,
        max_iterations=20
    )

    # 5. 작업 관리자 초기화 (llm_client_factory로 태스크별 모델 오버라이드 지원)
    task_manager = TaskManager(orchestrator=orchestrator, llm_client_factory=llm_client_factory)
    app.state.task_manager = task_manager

    # 6. 세션 관리자 초기화 (VS Code Extension용)
    sessions_path = WORKSPACE_PATH / ".sessions"
    session_manager = SessionManager(base_workspace_path=str(sessions_path))

    # 6-1. 만료된 세션을 주기적으로 정리하는 백그라운드 태스크 시작
    app.state.cleanup_task = asyncio.create_task(
        periodic_session_cleanup(session_manager, SESSION_CLEANUP_INTERVAL_SECONDS)
    )

    # 7. Agent API 라우터 등록
    agent_router = init_agent_router(task_manager)
    app.include_router(agent_router)

    # 8. VS Code API 라우터 등록
    vscode_router = init_vscode_router(session_manager, task_manager, orchestrator)
    app.include_router(vscode_router)

    # 9. Files API 라우터 등록
    files_router = init_files_router(WORKSPACE_PATH, MAX_FILE_SIZE)
    app.include_router(files_router)

    # 10. Generate/Analyze API 라우터 등록
    generate_router = init_generate_router(async_client, MODEL_NAME, WORKSPACE_PATH)
    app.include_router(generate_router)

    # 11. Chat WebSocket 라우터 등록
    chat_router = init_chat_router(async_client, MODEL_NAME)
    app.include_router(chat_router)

    app.state.agent_initialized = True
    logger.info("Agent system initialized successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """
    SIGTERM 수신 시 uvicorn이 진행 중인 요청/WebSocket 연결에 유예 시간을 준 뒤 이 핸들러를 호출한다.
    실제 대기는 uvicorn --timeout-graceful-shutdown(+ docker stop_grace_period)이 담당한다.
    """
    logger.info("Application shutdown initiated")

    cleanup_task = getattr(app.state, "cleanup_task", None)
    if cleanup_task is not None:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


# Ollama client
client = ollama.Client(host=OLLAMA_HOST)
async_client = ollama.AsyncClient(host=OLLAMA_HOST)


@app.get("/")
async def root():
    """서비스 정보"""
    return UnicodeJSONResponse({
        "service": "AI Coding Agent",
        "version": "1.0.0",
        "model": MODEL_NAME,
        "status": "running",
        "timestamp": datetime.now().isoformat()
    })


@app.get("/health")
async def health_check():
    """헬스체크 - Ollama 연결, 워크스페이스 쓰기 가능 여부, 에이전트 초기화 상태 확인"""
    workspace_writable = os.access(WORKSPACE_PATH, os.W_OK)
    task_stats = app.state.task_manager.get_stats() if app.state.task_manager else None

    try:
        # Ollama 서버 연결 확인 (이벤트 루프 블로킹 방지)
        models = await asyncio.to_thread(client.list)

        # 모델이 다운로드되어 있는지 확인
        model_available = any(MODEL_NAME in model.get("name", "") for model in models.get("models", []))

        return UnicodeJSONResponse({
            "status": "healthy",
            "ollama": "connected",
            "model": MODEL_NAME,
            "model_available": model_available,
            "agent_initialized": app.state.agent_initialized,
            "workspace_writable": workspace_writable,
            "tasks": task_stats,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"헬스체크 실패: {e}")
        raise HTTPException(status_code=503, detail=f"Ollama 서버 연결 실패: {str(e)}")


@app.get("/metrics")
async def metrics():
    """Prometheus 메트릭"""
    return StreamingResponse(
        iter([generate_latest()]),
        media_type=CONTENT_TYPE_LATEST
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("API_PORT", "8000")),
        reload=True
    )
