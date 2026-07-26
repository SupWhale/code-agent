"""
API 키 인증

프로덕션(외부 공개) 환경에서는 API_KEYS 환경 변수에 등록된 키만 허용합니다.
ENVIRONMENT=development이고 API_KEYS가 비어 있으면 로컬 개발 편의를 위해 인증을 건너뜁니다.
"""

import hmac
import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings

logger = logging.getLogger(__name__)

# HTTPBearer는 Starlette Request에 의존하므로 HTTP 라우트에서만 쓸 수 있다 — WebSocket
# 라우트에 FastAPI dependency(라우터 레벨 dependencies=[...] 포함)로 걸면
# "HTTPBearer.__call__() missing 1 required positional argument: 'request'"로 핸드셰이크
# 자체가 500으로 죽는다. 그래서 WebSocket 인증은 이 스킴을 쓰지 않고 authenticate_websocket()으로
# accept() 전에 수동 검증한다.
_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthenticatedKey:
    """인증 성공 시 dependency가 반환하는 신원 정보."""

    key: str
    scope: str  # "admin" | "user" — admin만 공유 워크스페이스 전역에 영향을 주는 엔드포인트 사용 가능


def _dev_bypass_identity() -> Optional[AuthenticatedKey]:
    """ENVIRONMENT=development이고 API_KEYS가 비어 있을 때만 인증을 건너뛴다.
    production에서는 config.py가 API_KEYS 없이 기동 자체를 막으므로 이 경로를 타지 않는다."""
    settings = get_settings()
    if settings.environment == "development" and not settings.api_keys:
        return AuthenticatedKey(key="dev", scope="admin")
    return None


def _match_key(token: str) -> Optional[AuthenticatedKey]:
    """hmac.compare_digest로 비교해 키 길이/내용에 따라 응답 시간이 달라지는
    타이밍 공격을 막는다 (`==` 비교는 첫 불일치 바이트에서 조기 종료되어 취약함)."""
    settings = get_settings()
    for known_key, scope in settings.api_keys.items():
        if hmac.compare_digest(token, known_key):
            return AuthenticatedKey(key=token, scope=scope)
    return None


async def require_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> AuthenticatedKey:
    """HTTP 엔드포인트용 인증 dependency. `Authorization: Bearer <key>` 필요."""
    bypass = _dev_bypass_identity()
    if bypass is not None:
        return bypass

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization 헤더가 필요합니다 (Bearer <API 키>)",
        )

    matched = _match_key(credentials.credentials)
    if matched is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 API 키입니다")

    return matched


async def require_admin_key(
    identity: AuthenticatedKey = Depends(require_api_key),
) -> AuthenticatedKey:
    """워크스페이스 전체에 영향을 주는 파괴적/공유 엔드포인트용. scope=admin 키 필요."""
    if identity.scope != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin 권한이 필요합니다")
    return identity


async def authenticate_websocket(websocket: WebSocket) -> Optional[AuthenticatedKey]:
    """
    WebSocket 연결 인증.

    accept() 호출 전에 검증해야 하므로 예외 대신 None을 반환합니다 — 호출자는
    None이면 accept() 없이 close(code=1008)로 연결을 거부해야 합니다.
    토큰은 ?api_key=... 쿼리 파라미터 또는 Authorization: Bearer 헤더로 전달합니다.
    """
    bypass = _dev_bypass_identity()
    if bypass is not None:
        return bypass

    token = websocket.query_params.get("api_key")
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:]

    if not token:
        return None

    return _match_key(token)
