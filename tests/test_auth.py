"""API 키 인증(src/auth.py) 단위 테스트"""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from src import auth
from src.config import get_settings


class FakeWebSocket:
    """authenticate_websocket이 사용하는 최소 인터페이스만 흉내낸다."""

    def __init__(self, query_params=None, headers=None):
        self.query_params = query_params or {}
        self.headers = headers or {}


@pytest.fixture
def production_keys(monkeypatch):
    """production 환경 + 고정 API 키 세트로 설정하고, 끝나면 캐시를 원복한다."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("API_KEYS", "user-key:user,admin-key:admin")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_require_api_key_missing_credentials_rejected(production_keys):
    with pytest.raises(HTTPException) as exc_info:
        await auth.require_api_key(credentials=None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_api_key_wrong_key_rejected(production_keys):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-real-key")
    with pytest.raises(HTTPException) as exc_info:
        await auth.require_api_key(credentials=creds)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_api_key_valid_user_key_accepted(production_keys):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="user-key")
    identity = await auth.require_api_key(credentials=creds)
    assert identity.key == "user-key"
    assert identity.scope == "user"


@pytest.mark.asyncio
async def test_require_admin_key_rejects_user_scope(production_keys):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="user-key")
    identity = await auth.require_api_key(credentials=creds)
    with pytest.raises(HTTPException) as exc_info:
        await auth.require_admin_key(identity=identity)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_admin_key_accepts_admin_scope(production_keys):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="admin-key")
    identity = await auth.require_api_key(credentials=creds)
    result = await auth.require_admin_key(identity=identity)
    assert result.scope == "admin"


@pytest.mark.asyncio
async def test_authenticate_websocket_query_param_token(production_keys):
    ws = FakeWebSocket(query_params={"api_key": "admin-key"})
    identity = await auth.authenticate_websocket(ws)
    assert identity is not None
    assert identity.scope == "admin"


@pytest.mark.asyncio
async def test_authenticate_websocket_bearer_header_token(production_keys):
    ws = FakeWebSocket(headers={"authorization": "Bearer user-key"})
    identity = await auth.authenticate_websocket(ws)
    assert identity is not None
    assert identity.key == "user-key"


@pytest.mark.asyncio
async def test_authenticate_websocket_missing_token_returns_none(production_keys):
    ws = FakeWebSocket()
    identity = await auth.authenticate_websocket(ws)
    assert identity is None


@pytest.mark.asyncio
async def test_authenticate_websocket_wrong_token_returns_none(production_keys):
    ws = FakeWebSocket(query_params={"api_key": "bogus"})
    identity = await auth.authenticate_websocket(ws)
    assert identity is None


@pytest.mark.asyncio
async def test_development_bypass_without_api_keys(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("API_KEYS", "")
    get_settings.cache_clear()
    try:
        identity = await auth.require_api_key(credentials=None)
        assert identity.scope == "admin"

        ws = FakeWebSocket()
        ws_identity = await auth.authenticate_websocket(ws)
        assert ws_identity is not None
    finally:
        get_settings.cache_clear()
