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
    return _request_id_ctx.get()


def bind_new_request_id() -> str:
    """WebSocket 등 HTTP 미들웨어가 적용되지 않는 경로에서 수동으로 request_id를 부여한다."""
    request_id = uuid.uuid4().hex
    _request_id_ctx.set(request_id)
    return request_id


class _RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx.get()
        return True


class _JsonFormatter(logging.Formatter):
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
