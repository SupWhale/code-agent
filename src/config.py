"""
Application Settings

환경 변수를 fail-fast로 검증합니다. 필수 값이 없거나 형식이 잘못되면
앱이 요청을 받기 전에(기동 시점에) 즉시 실패합니다.
"""

from pathlib import Path
from functools import lru_cache
from typing import Dict, List, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", protected_namespaces=(), populate_by_name=True
    )

    environment: Literal["development", "production"] = "production"

    ollama_host: str = "http://localhost:11434"
    model_name: str = "qwen2.5-coder:7b"
    workspace_path: Path = Path(".")
    max_file_size: int = 104_857_600  # 100MB
    api_port: int = 8000
    log_level: str = "INFO"
    workers: int = 1

    # 콤마로 구분된 명시적 origin 목록. 비어 있으면 브라우저 크로스오리진 접근을 전혀 허용하지 않음.
    cors_allowed_origins_raw: str = Field(default="", alias="CORS_ALLOWED_ORIGINS")

    # "key1:admin,key2:user" 형식. scope 생략 시 "user".
    api_keys_raw: str = Field(default="", alias="API_KEYS")

    # 공개 API 표면에서 임의 셸 명령 실행(run_command) 허용 여부. 기본 비활성화.
    enable_shell_tool: bool = False

    rate_limit_per_minute: int = 30

    @field_validator("workspace_path")
    @classmethod
    def _resolve_workspace(cls, v: Path) -> Path:
        return v.resolve()

    @property
    def cors_allowed_origins(self) -> List[str]:
        return [o.strip() for o in self.cors_allowed_origins_raw.split(",") if o.strip()]

    @property
    def api_keys(self) -> Dict[str, str]:
        """API 키 -> scope("admin"|"user") 매핑"""
        keys: Dict[str, str] = {}
        for entry in self.api_keys_raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if ":" in entry:
                key, scope = entry.split(":", 1)
            else:
                key, scope = entry, "user"
            keys[key.strip()] = scope.strip() or "user"
        return keys

    @model_validator(mode="after")
    def _validate_production_requirements(self) -> "Settings":
        if self.environment == "production" and not self.api_keys:
            raise ValueError(
                "API_KEYS가 설정되지 않았습니다. 프로덕션 환경에서는 최소 1개 이상의 API 키가 "
                "필요합니다 (예: API_KEYS=<random-token>:admin). 로컬 개발용으로 인증 없이 "
                "실행하려면 ENVIRONMENT=development를 설정하세요."
            )
        if not self.workspace_path.exists():
            raise ValueError(f"WORKSPACE_PATH가 존재하지 않습니다: {self.workspace_path}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
