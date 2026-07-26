"""
Code Generation & Analysis API Routes

LLM에 직접 프롬프트를 던지는 단발성 코드 생성(/generate)과 파일/프로젝트 분석
(/analyze/*) 엔드포인트. 에이전트 툴 실행을 거치지 않는다.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List

import aiofiles
import ollama
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from prometheus_client import Counter, Histogram
from pydantic import BaseModel, Field

from ..auth import AuthenticatedKey, require_api_key
from ..config import get_settings
from ..rate_limit import limiter
from ..utils.responses import UnicodeJSONResponse
from .files import validate_path

logger = logging.getLogger(__name__)

api_requests_total = Counter('api_requests_total', 'Total API requests', ['method', 'endpoint', 'status'])
model_inference_time = Histogram('model_inference_time_seconds', 'Model inference time')


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


def init_generate_router(async_client: ollama.AsyncClient, model_name: str, workspace_path: Path) -> APIRouter:
    """
    Generate/Analyze 라우터 초기화

    Args:
        async_client: Ollama 비동기 클라이언트
        model_name: 사용할 모델 이름
        workspace_path: 분석 대상 파일이 위치한 워크스페이스 루트

    Returns:
        설정된 APIRouter
    """
    settings = get_settings()
    router = APIRouter(tags=["generate"])

    # Request 모델 — 여기 docstring은 FastAPI가 /docs(Swagger UI)에 그대로 노출한다
    class CodeGenerationRequest(BaseModel):
        """POST /api/v1/generate 요청 본문. 에이전트 툴 실행 없이 LLM에 직접 프롬프트를 던지는 단발성 코드 생성용."""

        prompt: str = Field(..., description="코드 생성 프롬프트")
        language: str = Field(default="python", description="프로그래밍 언어")
        temperature: float = Field(default=0.1, ge=0.0, le=2.0, description="생성 온도")
        stream: bool = Field(default=True, description="스트리밍 응답 여부")

    class FileAnalysisRequest(BaseModel):
        """POST /api/v1/analyze/file 요청 본문."""

        file_path: str = Field(..., description="분석할 파일 경로")
        analysis_type: str = Field(default="general", description="분석 유형: general, security, performance, style")

    class ProjectAnalysisRequest(BaseModel):
        """POST /api/v1/analyze/project 요청 본문."""

        project_path: str = Field(default="/", description="프로젝트 경로")
        include_patterns: List[str] = Field(default=["**/*.py", "**/*.js", "**/*.ts"], description="포함 패턴")
        exclude_patterns: List[str] = Field(default=["**/node_modules/**", "**/__pycache__/**", "**/venv/**"], description="제외 패턴")

    @router.post("/api/v1/generate")
    @limiter.limit(f"{settings.rate_limit_per_minute}/minute")
    async def generate_code(
        request: Request,
        body: CodeGenerationRequest,
        identity: AuthenticatedKey = Depends(require_api_key),
    ):
        """코드 생성 API"""
        start_time = datetime.now()

        try:
            # 프롬프트 구성
            system_prompt = f"당신은 {body.language} 전문 개발자입니다. 사용자의 요청에 따라 고품질 코드를 작성해주세요."
            full_prompt = f"{system_prompt}\n\n사용자 요청: {body.prompt}"

            if body.stream:
                # 스트리밍 응답
                async def generate():
                    try:
                        response = await async_client.chat(
                            model=model_name,
                            messages=[{"role": "user", "content": full_prompt}],
                            stream=True,
                            options={"temperature": body.temperature}
                        )

                        async for buffered_chunk in buffer_stream(response, buffer_size=10):
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
                response = await async_client.chat(
                    model=model_name,
                    messages=[{"role": "user", "content": full_prompt}],
                    stream=False,
                    options={"temperature": body.temperature}
                )

                content = response.get("message", {}).get("content", "")

                # 메트릭 기록
                inference_time = (datetime.now() - start_time).total_seconds()
                model_inference_time.observe(inference_time)
                api_requests_total.labels(method="POST", endpoint="/api/v1/generate", status="200").inc()

                return UnicodeJSONResponse({
                    "code": content,
                    "language": body.language,
                    "timestamp": datetime.now().isoformat()
                })

        except Exception as e:
            logger.error(f"코드 생성 실패: {e}")
            api_requests_total.labels(method="POST", endpoint="/api/v1/generate", status="500").inc()
            raise HTTPException(status_code=500, detail=f"코드 생성 실패: {str(e)}")

    @router.post("/api/v1/analyze/file")
    async def analyze_file(request: FileAnalysisRequest, identity: AuthenticatedKey = Depends(require_api_key)):
        """단일 파일 분석"""
        try:
            file_path = validate_path(request.file_path, workspace_path)

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
            response = await async_client.chat(
                model=model_name,
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

    @router.post("/api/v1/analyze/project")
    async def analyze_project(request: ProjectAnalysisRequest, identity: AuthenticatedKey = Depends(require_api_key)):
        """프로젝트 전체 분석"""
        try:
            project_path = validate_path(request.project_path, workspace_path)

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
            response = await async_client.chat(
                model=model_name,
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

    return router
