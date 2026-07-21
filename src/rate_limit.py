"""
Rate limiting

HTTP 엔드포인트는 slowapi(고정 윈도우, API 키 또는 IP 기준)를 사용하고,
WebSocket 연결 시도는 slowapi가 다루지 않으므로 동일한 방식의 수동 카운터를 둔다.

주의: 두 방식 모두 프로세스 내 메모리 상태다. WORKERS=1(단일 프로세스) 배포를
전제로 하며, 워커를 늘리려면(Phase 5) Redis 기반으로 옮겨야 한다.
"""

import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import get_settings


def _rate_limit_key(request: Request) -> str:
    """인증된 요청은 API 키 기준, 아니면 IP 기준으로 제한한다."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    return get_remote_address(request)


limiter = Limiter(key_func=_rate_limit_key)


_ws_attempts: Dict[str, Deque[float]] = defaultdict(deque)


def check_ws_rate_limit(key: str) -> bool:
    """고정 윈도우(60초) WebSocket 연결 제한. 허용되면 True."""
    settings = get_settings()
    limit = settings.rate_limit_per_minute
    now = time.monotonic()
    window = _ws_attempts[key]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        return False
    window.append(now)
    return True
