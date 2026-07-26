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
    """환경 변수에서 로드되는 앱 설정. `*_raw` 필드는 pydantic-settings가 env var를
    그대로 담는 곳이고, 파싱된 형태(리스트/딕셔너리)는 아래 @property로 노출한다 —
    BaseSettings 필드 자체를 리스트/딕셔너리로 선언하면 커스텀 콤마 구분 포맷을
    자동 파싱해주지 않기 때문."""

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
        """상대 경로(기본값 ".")를 절대 경로로 고정 — 이후 os.chdir 등으로 CWD가
        바뀌어도 워크스페이스 경계 검증(SecurityValidator)이 흔들리지 않게 한다."""
        return v.resolve()

    @property
    def cors_allowed_origins(self) -> List[str]:
        """빈 값이면 크로스오리진 브라우저 접근을 전혀 허용하지 않는다(CLI/서버 간 통신엔 불필요)."""
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
        """fail-fast 게이트 — 여기서 막지 않으면 인증 없이 배포되거나 워크스페이스가
        없는 채로 기동해서 첫 요청이 들어올 때야 실패가 드러난다."""
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
    """프로세스 생애주기 동안 한 번만 읽고 캐시한다 — 즉, 컨테이너를 재시작하지 않고는
    환경 변수를 바꿔도 반영되지 않는다(예: API_KEYS 회수는 재배포가 필요함).
    테스트에서 env를 바꿔가며 검증할 땐 get_settings.cache_clear()를 호출해야 한다."""
    return Settings()
