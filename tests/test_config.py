"""Settings(pydantic-settings) fail-fast 검증 테스트"""

import pytest

from src.config import Settings


def test_production_requires_api_keys(tmp_path):
    with pytest.raises(ValueError, match="API_KEYS"):
        Settings(environment="production", workspace_path=tmp_path, api_keys_raw="")


def test_production_with_api_keys_succeeds(tmp_path):
    settings = Settings(environment="production", workspace_path=tmp_path, api_keys_raw="abc:admin")
    assert settings.api_keys == {"abc": "admin"}


def test_development_allows_no_api_keys(tmp_path):
    settings = Settings(environment="development", workspace_path=tmp_path, api_keys_raw="")
    assert settings.api_keys == {}


def test_missing_workspace_path_rejected(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(ValueError, match="WORKSPACE_PATH"):
        Settings(environment="development", workspace_path=missing)


def test_api_keys_parsing_defaults_to_user_scope(tmp_path):
    settings = Settings(
        environment="development",
        workspace_path=tmp_path,
        api_keys_raw="key1:admin, key2 , key3:user",
    )
    assert settings.api_keys == {"key1": "admin", "key2": "user", "key3": "user"}


def test_cors_origins_parsed_from_comma_separated_string(tmp_path):
    settings = Settings(
        environment="development",
        workspace_path=tmp_path,
        cors_allowed_origins_raw="https://a.example.com, https://b.example.com",
    )
    assert settings.cors_allowed_origins == ["https://a.example.com", "https://b.example.com"]


def test_cors_origins_empty_by_default(tmp_path):
    settings = Settings(environment="development", workspace_path=tmp_path)
    assert settings.cors_allowed_origins == []


def test_enable_shell_tool_defaults_false(tmp_path):
    settings = Settings(environment="development", workspace_path=tmp_path)
    assert settings.enable_shell_tool is False
