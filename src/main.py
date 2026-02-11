"""
AI Coding Agent - Main Application
FastAPI-based coding assistant powered by Ollama and Qwen2.5-Coder
"""

import os
import json
import asyncio
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime

import aiofiles
import ollama
from fastapi import FastAPI, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Agent imports
from .agent.executor import ToolExecutor
from .agent.orchestrator import AgentOrchestrator
from .agent.task_manager import TaskManager
from .agent.security.validator import SecurityValidator
from .agent.llm.ollama_client import OllamaAgentClient
from .routes.agent import init_agent_router

# Logging configuration
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Environment variables
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen2.5-coder:14b")
WORKSPACE_PATH = Path(os.getenv("WORKSPACE_PATH", ".")).resolve()  # 현재 디렉토리를 기본값으로
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "104857600"))  # 100MB in bytes

# Prometheus metrics
api_requests_total = Counter('api_requests_total', 'Total API requests', ['method', 'endpoint', 'status'])
api_response_time = Histogram('api_response_time_seconds', 'API response time', ['method', 'endpoint'])
active_websockets = Gauge('active_websockets', 'Number of active WebSocket connections')
model_inference_time = Histogram('model_inference_time_seconds', 'Model inference time')
file_operations_total = Counter('file_operations_total', 'Total file operations', ['operation', 'status'])

# FastAPI app
app = FastAPI(
    title="AI Coding Agent",
    description="AI-powered coding assistant using Ollama and Qwen2.5-Coder",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent system (initialized on startup)
task_manager: Optional[TaskManager] = None


@app.on_event("startup")
async def startup_event():
    """앱 시작 시 agent 시스템 초기화"""
    global task_manager

    try:
        logger.info("Initializing agent system...")

        # 1. LLM 클라이언트 초기화
        llm_client = OllamaAgentClient(
            host=OLLAMA_HOST,
            model=MODEL_NAME,
            temperature=0.1
        )

        # 2. 보안 검증기 초기화
        security = SecurityValidator(
            workspace_path=str(WORKSPACE_PATH),
            strict_mode=True
        )

        # 3. 도구 실행기 초기화
        executor = ToolExecutor(workspace_path=str(WORKSPACE_PATH))

        # 4. 오케스트레이터 초기화
        orchestrator = AgentOrchestrator(
            llm_client=llm_client,
            executor=executor,
            security=security,
            max_iterations=20
        )

        # 5. 작업 관리자 초기화
        task_manager = TaskManager(orchestrator=orchestrator)

        # 6. Agent API 라우터 등록
        agent_router = init_agent_router(task_manager)
        app.include_router(agent_router)

        logger.info("Agent system initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize agent system: {e}")
        # Agent 시스템 초기화 실패해도 앱은 계속 실행
        logger.warning("App will continue without agent features")

# Custom JSON Response with UTF-8 support
class UnicodeJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


# Pydantic models
class CodeGenerationRequest(BaseModel):
    prompt: str = Field(..., description="코드 생성 프롬프트")
    language: str = Field(default="python", description="프로그래밍 언어")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0, description="생성 온도")
    stream: bool = Field(default=True, description="스트리밍 응답 여부")


class FileAnalysisRequest(BaseModel):
    file_path: str = Field(..., description="분석할 파일 경로")
    analysis_type: str = Field(default="general", description="분석 유형: general, security, performance, style")


class ProjectAnalysisRequest(BaseModel):
    project_path: str = Field(default="/", description="프로젝트 경로")
    include_patterns: List[str] = Field(default=["**/*.py", "**/*.js", "**/*.ts"], description="포함 패턴")
    exclude_patterns: List[str] = Field(default=["**/node_modules/**", "**/__pycache__/**", "**/venv/**"], description="제외 패턴")


# Ollama client
client = ollama.Client(host=OLLAMA_HOST)


def validate_path(path: str) -> Path:
    """경로 검증 및 정규화 (경로 탐색 공격 방지)"""
    try:
        full_path = (WORKSPACE_PATH / path.lstrip("/")).resolve()
        if not str(full_path).startswith(str(WORKSPACE_PATH)):
            raise ValueError("경로가 워크스페이스 밖을 벗어났습니다")
        return full_path
    except Exception as e:
        logger.error(f"경로 검증 실패: {path}, 에러: {e}")
        raise HTTPException(status_code=400, detail=f"잘못된 경로입니다: {str(e)}")


async def buffer_stream(generator, buffer_size: int = 10):
    """스트림을 버퍼링하여 전송"""
    buffer = ""
    async for chunk in generator:
        if isinstance(chunk, dict):
            content = chunk.get("message", {}).get("content", "")
        else:
            content = chunk

        buffer += content

        # 버퍼가 충분히 차거나 줄바꿈이 있으면 전송
        if len(buffer) >= buffer_size or "\n" in buffer:
            yield buffer
            buffer = ""

    # 남은 버퍼 전송
    if buffer:
        yield buffer


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
    """헬스체크 - Ollama 연결 확인"""
    try:
        # Ollama 서버 연결 확인
        models = client.list()

        # 모델이 다운로드되어 있는지 확인
        model_available = any(MODEL_NAME in model.get("name", "") for model in models.get("models", []))

        return UnicodeJSONResponse({
            "status": "healthy",
            "ollama": "connected",
            "model": MODEL_NAME,
            "model_available": model_available,
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


@app.post("/api/v1/generate")
async def generate_code(request: CodeGenerationRequest):
    """코드 생성 API"""
    start_time = datetime.now()

    try:
        # 프롬프트 구성
        system_prompt = f"당신은 {request.language} 전문 개발자입니다. 사용자의 요청에 따라 고품질 코드를 작성해주세요."
        full_prompt = f"{system_prompt}\n\n사용자 요청: {request.prompt}"

        if request.stream:
            # 스트리밍 응답
            async def generate():
                try:
                    response = client.chat(
                        model=MODEL_NAME,
                        messages=[{"role": "user", "content": full_prompt}],
                        stream=True,
                        options={"temperature": request.temperature}
                    )

                    # 버퍼링된 스트림
                    async def async_response():
                        for chunk in response:
                            yield chunk

                    async for buffered_chunk in buffer_stream(async_response(), buffer_size=10):
                        data = {"type": "content", "data": buffered_chunk}
                        yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

                    # 완료 신호
                    yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

                    # 메트릭 기록
                    inference_time = (datetime.now() - start_time).total_seconds()
                    model_inference_time.observe(inference_time)
                    api_requests_total.labels(method="POST", endpoint="/api/v1/generate", status="200").inc()

                except Exception as e:
                    logger.error(f"스트리밍 생성 실패: {e}")
                    error_data = {"type": "error", "data": str(e)}
                    yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                    api_requests_total.labels(method="POST", endpoint="/api/v1/generate", status="500").inc()

            return StreamingResponse(generate(), media_type="text/event-stream")

        else:
            # 논스트리밍 응답
            response = client.chat(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": full_prompt}],
                stream=False,
                options={"temperature": request.temperature}
            )

            content = response.get("message", {}).get("content", "")

            # 메트릭 기록
            inference_time = (datetime.now() - start_time).total_seconds()
            model_inference_time.observe(inference_time)
            api_requests_total.labels(method="POST", endpoint="/api/v1/generate", status="200").inc()

            return UnicodeJSONResponse({
                "code": content,
                "language": request.language,
                "timestamp": datetime.now().isoformat()
            })

    except Exception as e:
        logger.error(f"코드 생성 실패: {e}")
        api_requests_total.labels(method="POST", endpoint="/api/v1/generate", status="500").inc()
        raise HTTPException(status_code=500, detail=f"코드 생성 실패: {str(e)}")


@app.post("/api/v1/files/upload")
async def upload_file(file: UploadFile = File(...), path: str = Query(default="/")):
    """파일 업로드"""
    try:
        # 경로 검증
        upload_dir = validate_path(path)
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_path = upload_dir / file.filename

        # 파일 크기 확인
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            file_operations_total.labels(operation="upload", status="failed").inc()
            raise HTTPException(status_code=413, detail=f"파일 크기가 {MAX_FILE_SIZE / 1024 / 1024}MB를 초과합니다")

        # 파일 저장
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        file_operations_total.labels(operation="upload", status="success").inc()

        return UnicodeJSONResponse({
            "filename": file.filename,
            "path": str(file_path.relative_to(WORKSPACE_PATH)),
            "size": len(content),
            "timestamp": datetime.now().isoformat()
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"파일 업로드 실패: {e}")
        file_operations_total.labels(operation="upload", status="failed").inc()
        raise HTTPException(status_code=500, detail=f"파일 업로드 실패: {str(e)}")


@app.get("/api/v1/files/list")
async def list_files(path: str = Query(default="/")):
    """파일 목록 조회"""
    try:
        dir_path = validate_path(path)

        if not dir_path.exists():
            raise HTTPException(status_code=404, detail="디렉토리를 찾을 수 없습니다")

        if not dir_path.is_dir():
            raise HTTPException(status_code=400, detail="디렉토리가 아닙니다")

        files = []
        for item in dir_path.iterdir():
            files.append({
                "name": item.name,
                "path": str(item.relative_to(WORKSPACE_PATH)),
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else 0,
                "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat()
            })

        file_operations_total.labels(operation="list", status="success").inc()

        return UnicodeJSONResponse({
            "path": path,
            "files": sorted(files, key=lambda x: (x["type"] != "directory", x["name"]))
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"파일 목록 조회 실패: {e}")
        file_operations_total.labels(operation="list", status="failed").inc()
        raise HTTPException(status_code=500, detail=f"파일 목록 조회 실패: {str(e)}")


@app.get("/api/v1/files/read")
async def read_file(path: str = Query(..., description="읽을 파일 경로")):
    """파일 읽기"""
    try:
        file_path = validate_path(path)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

        if not file_path.is_file():
            raise HTTPException(status_code=400, detail="파일이 아닙니다")

        # 파일 읽기 (텍스트 파일로 가정)
        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()

            file_operations_total.labels(operation="read", status="success").inc()

            return UnicodeJSONResponse({
                "path": path,
                "content": content,
                "size": file_path.stat().st_size,
                "timestamp": datetime.now().isoformat()
            })
        except UnicodeDecodeError:
            # 바이너리 파일인 경우
            raise HTTPException(status_code=400, detail="바이너리 파일은 읽을 수 없습니다. /download를 사용하세요.")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"파일 읽기 실패: {e}")
        file_operations_total.labels(operation="read", status="failed").inc()
        raise HTTPException(status_code=500, detail=f"파일 읽기 실패: {str(e)}")


@app.get("/api/v1/files/download")
async def download_file(path: str = Query(..., description="다운로드할 파일 경로")):
    """파일 다운로드"""
    try:
        file_path = validate_path(path)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

        if not file_path.is_file():
            raise HTTPException(status_code=400, detail="파일이 아닙니다")

        file_operations_total.labels(operation="download", status="success").inc()

        return FileResponse(
            path=file_path,
            filename=file_path.name,
            media_type="application/octet-stream"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"파일 다운로드 실패: {e}")
        file_operations_total.labels(operation="download", status="failed").inc()
        raise HTTPException(status_code=500, detail=f"파일 다운로드 실패: {str(e)}")


@app.delete("/api/v1/files/delete")
async def delete_file(path: str = Query(..., description="삭제할 파일 경로")):
    """파일 삭제"""
    try:
        file_path = validate_path(path)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

        if file_path.is_dir():
            # 디렉토리 삭제 (재귀적)
            import shutil
            shutil.rmtree(file_path)
        else:
            # 파일 삭제
            file_path.unlink()

        file_operations_total.labels(operation="delete", status="success").inc()

        return UnicodeJSONResponse({
            "path": path,
            "deleted": True,
            "timestamp": datetime.now().isoformat()
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"파일 삭제 실패: {e}")
        file_operations_total.labels(operation="delete", status="failed").inc()
        raise HTTPException(status_code=500, detail=f"파일 삭제 실패: {str(e)}")


@app.post("/api/v1/analyze/file")
async def analyze_file(request: FileAnalysisRequest):
    """단일 파일 분석"""
    try:
        file_path = validate_path(request.file_path)

        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

        # 파일 읽기
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()

        # 분석 프롬프트 구성
        analysis_prompts = {
            "general": "다음 코드를 분석하고 개선점을 제안해주세요.",
            "security": "다음 코드의 보안 취약점을 분석해주세요.",
            "performance": "다음 코드의 성능 문제를 분석하고 최적화 방안을 제안해주세요.",
            "style": "다음 코드의 스타일과 가독성을 분석해주세요."
        }

        prompt = analysis_prompts.get(request.analysis_type, analysis_prompts["general"])
        full_prompt = f"{prompt}\n\n```\n{content}\n```"

        # Ollama로 분석
        response = client.chat(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": full_prompt}],
            stream=False
        )

        analysis = response.get("message", {}).get("content", "")

        return UnicodeJSONResponse({
            "file_path": request.file_path,
            "analysis_type": request.analysis_type,
            "analysis": analysis,
            "timestamp": datetime.now().isoformat()
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"파일 분석 실패: {e}")
        raise HTTPException(status_code=500, detail=f"파일 분석 실패: {str(e)}")


@app.post("/api/v1/analyze/project")
async def analyze_project(request: ProjectAnalysisRequest):
    """프로젝트 전체 분석"""
    try:
        project_path = validate_path(request.project_path)

        if not project_path.exists() or not project_path.is_dir():
            raise HTTPException(status_code=404, detail="프로젝트 디렉토리를 찾을 수 없습니다")

        # 파일 수집
        files = []
        for pattern in request.include_patterns:
            for file_path in project_path.rglob(pattern.replace("**/", "")):
                # 제외 패턴 확인
                should_exclude = False
                for exclude_pattern in request.exclude_patterns:
                    if exclude_pattern.replace("**/", "") in str(file_path):
                        should_exclude = True
                        break

                if not should_exclude and file_path.is_file():
                    files.append(file_path)

        # 파일 목록 구성
        file_list = "\n".join([f"- {f.relative_to(project_path)}" for f in files[:50]])  # 최대 50개

        # 분석 프롬프트
        prompt = f"""다음 프로젝트를 분석해주세요:

프로젝트 경로: {request.project_path}
파일 개수: {len(files)}개

주요 파일:
{file_list}

프로젝트 구조, 아키텍처, 개선점을 분석해주세요."""

        # Ollama로 분석
        response = client.chat(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )

        analysis = response.get("message", {}).get("content", "")

        return UnicodeJSONResponse({
            "project_path": request.project_path,
            "file_count": len(files),
            "analysis": analysis,
            "timestamp": datetime.now().isoformat()
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"프로젝트 분석 실패: {e}")
        raise HTTPException(status_code=500, detail=f"프로젝트 분석 실패: {str(e)}")


# WebSocket 연결 관리
class ConnectionManager:
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


manager = ConnectionManager()


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket, client_id: str = Query(default="default")):
    """WebSocket 채팅"""
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
                response = client.chat(
                    model=MODEL_NAME,
                    messages=manager.conversation_history[client_id],
                    stream=True
                )

                full_response = ""
                buffer = ""

                for chunk in response:
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("API_PORT", "8000")),
        reload=True
    )
