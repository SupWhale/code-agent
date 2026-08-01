# Code Agent

LLM(Ollama + Qwen2.5-Coder) 기반 자율 코딩 에이전트. FastAPI 백엔드, CLI 클라이언트, MCP 서버로 구성되어 있으며 파일 읽기/수정, 코드 검색, 테스트 실행 등을 에이전트 루프로 자동 수행합니다.

> 개인 포트폴리오 프로젝트입니다. 구조/아키텍처 상세는 [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md), 네트워크·실시간 통신 인프라 상세는 [docs/infrastructure.md](docs/infrastructure.md)를 참고하세요.

## 핵심 기능

- LLM 기반 코드 자동 읽기·분석·수정 (최대 20회 반복 에이전트 루프)
- CLI 터미널 인터페이스 + WebSocket/SSE 실시간 스트리밍
- 세션 격리 워크스페이스, Prometheus + Grafana 모니터링
- Claude Code/Desktop에서 바로 쓸 수 있는 MCP 서버 (`src/mcp_server.py`)

## 기술 스택

FastAPI · Uvicorn · Pydantic v2 · Ollama · Prometheus/Grafana/Alertmanager/cAdvisor · Docker · Nginx · GitHub Actions · Typer/Rich(CLI)

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

**완료 (Phase 2 — 운영 안정성 기반)**
- 구조화(JSON) 로깅 + Request ID 미들웨어(HTTP 전체 + WebSocket)
- `/health`에 워크스페이스 쓰기 가능 여부·태스크 통계 추가
- 컨테이너 CPU/메모리 제한, graceful shutdown(uvicorn timeout + stop_grace_period)
- Prometheus 알림 규칙(인스턴스 다운/5xx율/지연시간/디스크·메모리/컨테이너 재시작 루프) + Alertmanager + cAdvisor
- GitHub Actions(`.github/workflows/build-and-push.yml`)로 테스트 통과 시 GHCR(`ghcr.io/supwhale/code-agent`)에 이미지 빌드/푸시
- 배포 스크립트를 현지 빌드 방식에서 GHCR 태그 pull 방식으로 전환, `rollback.sh`는 `git reset --hard`/`rm -rf` 대신 이전 태그로 안전하게 롤백

**진행 예정 (Phase 3+)**
- 첫 공개 배포 (실제 도메인 필요 — LAN 환경 배포/실사용 검증은 완료)
- 린트/타입체크(ruff/mypy) 도입, 라우트/오케스트레이터 루프 테스트 확충
- 의존성/이미지 취약점 스캔
- Redis 기반 상태 공유(현재 `WORKERS=1` 고정 — 태스크/세션 상태가 프로세스 메모리에 있음)

## 실전 배포에서 발견한 문제

홈서버(LAN)에 실제로 배포해보면서 코드 리뷰나 유닛 테스트만으로는 안 드러나는 문제들을 발견하고 고쳤습니다. 그대로 커밋 히스토리에 남겨뒀습니다.

1. **WebSocket 라우트가 인증 미들웨어에 의해 깨짐** — 라우터 레벨 `dependencies=[Depends(require_api_key)]`가 내부적으로 HTTP 전용 `HTTPBearer`(Starlette `Request` 필요)에 의존하는데, 같은 라우터에 등록된 WebSocket 엔드포인트에도 그대로 적용되면서 핸드셰이크 자체가 `TypeError`로 죽고 클라이언트에는 HTTP 500만 찍혔습니다. 유닛 테스트는 HTTP 엔드포인트만 돌렸어서 못 잡았고, 실제로 WebSocket 클라이언트를 붙여보고서야 발견 → HTTP 엔드포인트마다 개별 dependency로 바꾸고, WebSocket은 `accept()` 전 수동 인증(`authenticate_websocket()`)으로 분리.
2. **non-root 전환 후 기존 볼륨 권한 충돌** — 컨테이너를 non-root(uid 1000)로 바꾼 뒤, 예전에 root로 실행되던 컨테이너가 만들어둔 호스트 바인드 마운트(`deployment/workspace/`)를 새 프로세스가 쓰지 못해 기동 직후 크래시 루프에 빠짐 → 배포 스크립트가 실제 쓰기 가능 여부를 사전 점검하고, 안 되면 `sudo chmod` 안내 후 종료하도록 방어.
3. **배포 스크립트 자체의 버그 3종** — 실행 권한(+x) 누락, `docker compose`가 대상 서비스와 무관하게 파일 전체를 먼저 해석해서 `DOMAIN` 없이는 아무 서비스도 못 띄우던 문제, 자동으로 채워둔 placeholder 도메인(`lan-test.local`)을 "진짜 도메인 설정됨"으로 오인식해 TLS를 켜려던 로직 오류.
4. **SSE가 LLM 추론이 오래 걸리면 nginx idle 타임아웃(300초)에 끊김** — 실제 nginx 설정(`nginx.conf.template`)을 로컬에 그대로 재현해 300초 이상 침묵시켜본 결과, WebSocket 2종(`/api/v1/vscode/ws/*`, `/api/v1/agent/ws/*`)은 uvicorn의 자동 WS PING(~20초 간격) 덕분에 살아남았지만 SSE(`/api/v1/agent/task/{id}/execute`)는 정확히 300.1초에 끊겼습니다. 원인은 `ollama_client.py`가 `stream=False`로 LLM 응답 전체가 완성될 때까지 아무 이벤트도 안 내던 것 → `ollama.AsyncClient`의 토큰 스트리밍(`stream=True`)으로 바꿔 추론 중에도 계속 이벤트가 나가도록 수정. 상세: [docs/infrastructure.md](docs/infrastructure.md) 4.3절.

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
