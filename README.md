# Code Agent

LLM(Ollama + Qwen2.5-Coder) 기반 자율 코딩 에이전트. FastAPI 백엔드, CLI 클라이언트, MCP 서버로 구성되어 있으며 파일 읽기/수정, 코드 검색, 테스트 실행 등을 에이전트 루프로 자동 수행합니다.

> 개인 포트폴리오 프로젝트입니다. 구조/아키텍처 상세는 [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)를 참고하세요.

## 핵심 기능

- LLM 기반 코드 자동 읽기·분석·수정 (최대 20회 반복 에이전트 루프)
- CLI 터미널 인터페이스 + WebSocket/SSE 실시간 스트리밍
- 세션 격리 워크스페이스, Prometheus + Grafana 모니터링
- Claude Code/Desktop에서 바로 쓸 수 있는 MCP 서버 (`src/mcp_server.py`)

## 기술 스택

FastAPI · Uvicorn · Pydantic v2 · Ollama · Prometheus/Grafana · Docker · Nginx · Typer/Rich(CLI)

## 프로덕션 준비 상태

이 레포는 실제 외부 공개 서비스로 운영하는 것을 목표로 단계적으로 하드닝 중입니다. 진행 상황을 숨기지 않고 그대로 남겨둡니다.

**완료 (Phase 1 — 보안/안정성 stop-ship 수정)**
- API 키 인증(`user`/`admin` 스코프), 모든 `/api/v1/*` 엔드포인트(HTTP/WS/SSE) 적용
- CORS 화이트리스트, `run_command`(임의 셸 실행) 공개 API 표면에서 제거
- Rate limiting, 파일 삭제/업로드 등 파괴적 엔드포인트 admin 스코프 제한
- 에이전트 초기화 실패 시 크래시 후 재시작(이전엔 조용히 기능 없이 계속 실행됨)
- 컨테이너 non-root 실행, `pydantic-settings` 기반 fail-fast 설정 검증
- Grafana 기본 비밀번호 제거, 배포 스크립트 비밀번호 echo 제거
- nginx + certbot 기반 TLS(Let's Encrypt) 스캐폴딩

**진행 예정 (Phase 2+)**
- CI/CD 파이프라인(GitHub Actions), 린트/타입체크(ruff/mypy) 도입
- 구조화 로깅, 이미지 버저닝 및 안전한 롤백(현재 배포 스크립트는 소스 rsync + 현지 빌드 방식)
- 의존성/이미지 취약점 스캔, Prometheus 알림 규칙
- Redis 기반 상태 공유(현재 `WORKERS=1` 고정 — 태스크/세션 상태가 프로세스 메모리에 있음)

## 로컬 실행

```bash
# 개발 모드 (인증 없이, 핫리로드)
docker compose -f docker/docker-compose.dev.yml up

# 프로덕션 구성 (인증/TLS 필요 — .env.example 참고)
cp .env.example .env   # API_KEYS, GRAFANA_ADMIN_PASSWORD 등 채우기
cd deployment && docker compose --env-file ../.env up -d
```

CLI 사용법은 [cli/README.md](cli/README.md)를 참고하세요.

## 보안 노트

- `.env`는 `.gitignore`에 포함되어 있으며 이 레포 히스토리에 커밋된 적이 없습니다. `.env.example`에는 실제 값이 들어있지 않습니다.
- 데모를 공개로 운영할 경우 데모 전용 API 키를 별도로 발급하고, 절대 레포에 커밋하지 마세요.
- 임의 셸 명령 실행(`run_command`)은 공개 API에서 비활성화되어 있으며, MCP(로컬 신뢰 경계)에서만 사용 가능합니다.
