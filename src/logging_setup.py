"""
구조화(JSON) 로깅 + Request ID

요청마다 고유 ID를 생성해 응답 헤더(X-Request-ID)로 돌려주고, 같은 요청에서 발생하는
모든 로그 레코드에 자동으로 심어 인증 실패/에러 발생 시 로그만으로 요청을 추적할 수 있게 한다.
"""

import contextvars
import json
import logging
import uuid
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def get_request_id() -> str:
    """현재 asyncio 태스크에 바인딩된 request_id 조회. 미들웨어/bind_new_request_id()가
    호출되기 전이면 기본값 "-"."""
    return _request_id_ctx.get()


def bind_new_request_id() -> str:
    """WebSocket 등 HTTP 미들웨어가 적용되지 않는 경로에서 수동으로 request_id를 부여한다."""
    request_id = uuid.uuid4().hex
    _request_id_ctx.set(request_id)
    return request_id


class _RequestIDFilter(logging.Filter):
    """모든 로그 레코드에 현재 request_id를 주입 — 로거를 개별적으로 안 고쳐도
    logging.info(...) 호출 어디서든 자동으로 request_id가 붙게 하는 훅."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx.get()
        return True


class _JsonFormatter(logging.Formatter):
    """한 줄짜리 JSON 로그 — 로그 수집기(예: Loki, CloudWatch)가 필드 단위로
    파싱/검색할 수 있도록 평문 대신 구조화된 포맷으로 출력한다."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    """루트 로거의 기존 핸들러를 전부 걷어내고 JSON 핸들러로 교체한다 — uvicorn/기타
    라이브러리가 자체 핸들러를 먼저 붙여놓는 경우가 있어, 앱 시작 시 한 번만 호출해
    모든 로그가 같은 포맷을 쓰도록 강제한다."""
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    handler.addFilter(_RequestIDFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """모든 HTTP 요청에 request_id를 부여(요청에 X-Request-ID가 있으면 그대로 사용)하고 응답 헤더로 되돌려준다."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id")
        request_id = incoming or uuid.uuid4().hex
        token = _request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response
