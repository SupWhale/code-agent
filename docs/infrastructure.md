# Code Agent - 인프라 구성 문서

> 작성일: 2026-07-28
>
> 이 문서는 **네트워크 인프라(Nginx, Docker 네트워크, 실시간 통신)가 실제로 무엇을 하는지**에
> 초점을 맞춘다. 코드/디렉토리 구조 전반은 [PROJECT_STRUCTURE.md](../PROJECT_STRUCTURE.md),
> 배포 절차와 하드닝 진행 상황은 [README.md](../README.md)를 참고.
>
> 근거 파일: `deployment/docker-compose.yml`, `deployment/nginx/nginx.conf.template`,
> `deployment/prometheus/*`, `deployment/alertmanager/*`, `docker/Dockerfile.prod`,
> `src/auth.py`, `src/rate_limit.py`, `src/agent/task_manager.py`, `src/agent/session_manager.py`,
> `src/routes/{agent,vscode,chat}.py`

## 목차

1. [전체 네트워크 토폴로지](#1-전체-네트워크-토폴로지)
2. [Docker 네트워크 & 포트 노출](#2-docker-네트워크--포트-노출)
3. [Nginx 리버스 프록시 상세](#3-nginx-리버스-프록시-상세)
4. [실시간 통신(WebSocket/SSE) 아키텍처](#4-실시간-통신websocketsse-아키텍처)
5. [모니터링/관측 스택 네트워크](#5-모니터링관측-스택-네트워크)
6. [컨테이너 실행/보안 경계](#6-컨테이너-실행보안-경계)
7. [TLS 발급/갱신 흐름](#7-tls-발급갱신-흐름)
8. [알려진 한계 / 향후 과제](#8-알려진-한계--향후-과제)

---

## 1. 전체 네트워크 토폴로지

```
                                인터넷 / LAN
                                     │
              ┌──────────────────────┼───────────────┐
              │ 80 (HTTP)            │ 443 (HTTPS)    │ 8000 (의도적 예외 — 아래 참고)
              ▼                      ▼                ▼
      ┌───────────────────────────────────┐      coding-agent
      │              nginx                │      (FastAPI, :8000)
      │  - 80: ACME 챌린지만 처리, 그 외  │
      │        전부 443으로 301 리다이렉트│
      │  - 443: TLS 종료(certbot 인증서)  │
      │        + 리버스 프록시           │
      └────────────────┬────────────────-┘
                        │ proxy_pass (도커 내부 DNS: coding-agent:8000)
                        ▼
      ┌───────────────────────────────┐        ┌───────────────────────────┐
      │       coding-agent            │◄──────►│         ollama            │
      │       (FastAPI, :8000)        │  HTTP  │   qwen2.5-coder:7b        │
      │  /api/v1/*  /ws/chat  /health │        │   (Nvidia GPU 컨테이너,   │
      │  /metrics                     │        │    호스트 포트 게시 없음) │
      └────────────────┬───────────────┘        └───────────────────────────┘
                        │ :8000/metrics 직접 스크레이핑 (nginx 안 거침)
                        ▼
      ┌───────────────────────────┐   alert   ┌───────────────────────────┐
      │     prometheus (:9090)    │──────────►│    alertmanager (:9093)   │──webhook──► Slack/Discord
      └────────────┬──────────────┘           └───────────────────────────┘
                   │ datasource
                   ▼
             grafana (:3000)

      node-exporter(:9100) — 호스트 메트릭, cadvisor(:8080) — 컨테이너별 메트릭
      → 둘 다 prometheus가 별도 scrape_config로 수집

      ※ prometheus/alertmanager/grafana/cadvisor/node-exporter/ollama는 호스트에
        포트를 게시하지 않는다 — coding-agent-network 내부에서만 서로 접근 가능.
```

모든 서비스는 하나의 Docker 브리지 네트워크(`coding-agent-network`) 위에 있고, 외부에서 "정식으로"
공개하도록 설계된 진입점은 nginx(80/443)다. `coding-agent`의 8000만 예외적으로 호스트에
직접 게시되어 있는데, 이는 실수가 아니라 `scripts/deploy.sh`가 `DOMAIN` 미설정 시(LAN 테스트
배포) nginx/certbot 자체를 안 띄우기 때문에 남겨둔 의도적 결정이다(2.2절).

---

## 2. Docker 네트워크 & 포트 노출

### 2.1 브리지 네트워크와 서비스 디스커버리

프로덕션 구성(`deployment/docker-compose.yml`)의 모든 서비스는 `coding-agent-network`
(`driver: bridge`)에 연결된다. Docker의 임베디드 DNS 덕분에 **서비스 이름이 곧 호스트네임**이
되어, 컨테이너 간 통신은 IP가 아니라 이름으로 이루어진다:

- nginx의 upstream: `server coding-agent:8000;`
- coding-agent → ollama: `OLLAMA_HOST=http://ollama:11434`
- prometheus → 각 타깃: `coding-agent:8000`, `node-exporter:9100`, `cadvisor:8080`
- prometheus → alertmanager: `alertmanager:9093`

개발 환경(`docker/docker-compose.dev.yml`)은 별도의 `coding-agent-dev-network`를 쓰며
`ollama-dev` + `coding-agent-dev` 두 서비스만 존재한다. nginx, TLS, 모니터링 스택 전체가
빠져 있고, `ENVIRONMENT=development` + `API_KEYS` 미설정 조합이라 인증 자체를 건너뛴다
(`src/auth.py::_dev_bypass_identity`) — 즉 dev 구성은 애초에 신뢰된 로컬 환경을 전제로
설계되어 있다.

### 2.2 포트 매핑과 실제 노출 범위

> 2026-07-28 업데이트: nginx를 거칠 필요가 없던 6개 서비스(ollama, prometheus,
> alertmanager, grafana, cadvisor, node-exporter)는 호스트 `ports:` 게시를 제거했다.
> `coding-agent`의 8000만 아래 이유로 의도적으로 남겨뒀다.

| 서비스 | 컨테이너 포트 | 호스트 게시 | 설계상 접근 경로 | 비고 |
|---|---|---|---|---|
| nginx | 80, 443 | `80:80`, `443:443` | 외부 공개 | 유일하게 "공개용"으로 설계된 진입점 |
| coding-agent | 8000 | `8000:8000` (유지) | nginx 경유 **또는** 직접 | **의도적 예외.** `scripts/deploy.sh`는 `DOMAIN`이 없으면(LAN 테스트 배포) nginx/certbot을 아예 안 띄우므로, 그 경로에서는 8000 직접 접근이 API에 닿는 유일한 수단이다(실제 LAN 서버가 이 방식으로 운영 중). nginx가 실제로 앞에 있는 배포에서는 이 포트가 nginx의 TLS 종료·`/metrics` 내부망 제한(3.2절)을 우회하는 구멍이 되므로, `DOMAIN` 없이도 nginx를 HTTP 전용으로 띄우도록 `deploy.sh`를 고친 뒤 제거하는 게 목표(8장). |
| ollama | 11434 | 게시 안 함 | coding-agent만(내부 DNS로 충분) | 앱 동작에는 호스트 게시가 불필요했다. Ollama API는 자체 인증이 없어 게시 시 외부에서 모델을 직접 나열/호출할 수 있었다. |
| prometheus | 9090 | 게시 안 함 | 컨테이너 내부에서만 | nginx 뒤에 있지 않고 인증도 없다. 확인 필요 시 `docker compose exec prometheus wget -qO- http://localhost:9090/-/healthy` |
| alertmanager | 9093 | 게시 안 함 | 컨테이너 내부에서만 | 인증 없음 |
| grafana | 3000 | 게시 안 함 | 컨테이너 내부에서만 | 자체 로그인(admin 비밀번호, `.env` 필수값)은 있지만 이중 방어로 게시 자체를 제거 |
| cadvisor | 8080 | 게시 안 함 | 컨테이너 내부에서만 | 인증 없음. `/rootfs`, `/var/run`, `/sys`, 도커 소켓을 read-only로 마운트하는 서비스라 특히 노출을 피해야 함 |
| node-exporter | 9100 | 게시 안 함 | 컨테이너 내부에서만 | 인증 없음 |

> 브라우저로 Grafana/Prometheus 대시보드를 봐야 하면, 확인하는 동안만
> `deployment/docker-compose.yml`에 해당 서비스의 `ports:`를 한시적으로 되살리는 방식을
> 쓴다(운영 스크립트에는 반영하지 않음 — 상시 노출을 막는 게 목적이므로).

### 2.3 공유 볼륨(네트워크 스토리지 아님, 참고용)

`workspace`(코드 작업 공간), `models`(Ollama 캐시), `certbot-etc`/`certbot-webroot`(TLS),
`prometheus-data`/`alertmanager-data`/`grafana-data`(각 스택 상태)는 전부 로컬 볼륨이며
서비스 간 공유는 같은 호스트 위 bind mount/named volume으로만 이루어진다 — 별도의
네트워크 스토리지 계층은 없다.

---

## 3. Nginx 리버스 프록시 상세

설정 파일: `deployment/nginx/nginx.conf.template`. 컨테이너 기동 시
`envsubst '$DOMAIN' < nginx.conf.template > nginx.conf`로 `${DOMAIN}`만 실제 값으로 치환한 뒤
`nginx -g 'daemon off;'`를 실행한다(`docker-compose.yml`의 nginx `command`).

### 3.1 두 개의 server 블록

- **80번(HTTP)** — `/.well-known/acme-challenge/`만 실제로 처리(webroot, certbot과 볼륨 공유)
  하고 그 외 모든 요청은 `301 → https://$host$request_uri`. 이 블록의 유일한 존재 이유는
  Let's Encrypt 인증이다.
- **443번(HTTPS)** — `ssl_certificate`/`ssl_certificate_key`는 certbot이 발급한 인증서
  (`/etc/letsencrypt/live/${DOMAIN}/...`, `certbot-etc` 볼륨 공유)를 가리킨다. `TLSv1.2`/`TLSv1.3`만
  허용하고 `HIGH:!aNULL:!MD5`로 구식 프로토콜/약한 스위트를 차단한다.

### 3.2 location별 라우팅

| location | 대상 | 특이 설정 | 실제로 처리하는 것 |
|---|---|---|---|
| `/api/` | `coding-agent:8000` | `proxy_read/send/connect_timeout 300s`, `Upgrade`/`Connection` 헤더 전달 | REST API(`/api/v1/agent/*`, `/api/v1/vscode/*`, `/api/v1/files/*`, `/api/v1/generate`) **그리고** 이 prefix 아래 있는 WebSocket 2종(`/api/v1/agent/ws/{task_id}`, `/api/v1/vscode/ws/{session_id}`)과 SSE(`/api/v1/agent/task/{id}/execute`)까지 전부 포함 |
| `/ws/` | `coding-agent:8000` | `proxy_read/send/connect_timeout 7d` | **오직** `/ws/chat`(순수 LLM 채팅)만 매칭 |
| `/health` | `coding-agent:8000` | `access_log off` | 헬스체크 로그 노이즈 방지 |
| `/metrics` | `coding-agent:8000` | `geo $internal_network`로 사설 대역(`10/8`, `172.16/12`, `192.168/16`, `127.0.0.1`) 외 `403` | Prometheus는 이 경로를 거치지 않고 `coding-agent:8000/metrics`를 컨테이너 네트워크로 직접 스크레이핑(`prometheus.yml`)하므로, 이 location은 사람이 브라우저로 확인할 때만 쓰인다. `coding-agent`의 8000이 (2.2절에서 설명한 의도적 예외로) 호스트에 여전히 직접 게시돼 있어 이 제한은 지금도 우회 가능하다 — nginx-only 전환 전까지 남는 한계(8장). |
| `/` | `coding-agent:8000` | - | 위 조건에 안 걸리는 나머지 전부(루트 서비스 정보 등) |

nginx의 location 매칭은 **최장 프리픽스 우선**이다. 그래서 `/api/v1/agent/ws/xyz`나
`/api/v1/vscode/ws/xyz`는 경로 문자열에 `ws`가 들어있어도 `/ws/`가 아니라 `/api/`에 걸린다 —
경로가 `/api/`로 시작하기 때문이다. 이는 4.3절의 타임아웃 비대칭으로 직접 이어진다.

### 3.3 WebSocket 업그레이드 처리

WebSocket은 HTTP/1.1 업그레이드 핸드셰이크로 시작하는데, nginx→백엔드 기본 프로토콜은
HTTP/1.0이라 업그레이드를 지원하지 않는다. 그래서 `/api/`, `/ws/` 두 location 모두
`proxy_http_version 1.1` + `proxy_set_header Upgrade $http_upgrade` +
`proxy_set_header Connection "upgrade"`를 명시해, 클라이언트가 보낸 업그레이드 요청을
그대로 백엔드(FastAPI/Starlette)에 전달한다. (`proxy_cache_bypass $http_upgrade`는 캐시가
있을 때 업그레이드 요청을 캐시에서 우회시키는 관용구인데, 이 설정에는 애초에
`proxy_cache_path`/캐시 존이 정의돼 있지 않아 현재는 실질적 효과가 없는 보일러플레이트다.)

### 3.4 SSE(`text/event-stream`)가 nginx를 통과하는 방식

`/api/v1/agent/task/{id}/execute`(`src/routes/agent.py`)는 `StreamingResponse`로
`data: {json}\n\n` 청크를 내려보내며, 응답 헤더에 `X-Accel-Buffering: no`를 명시적으로 심는다.
이는 애플리케이션이 nginx에게 "이 응답은 버퍼링하지 말고 청크가 생기는 즉시 클라이언트로
흘려보내라"고 지시하는 nginx 전용 헤더다 — 없으면 nginx의 기본 프록시 버퍼링
(`proxy_buffering`은 기본 `on`)이 응답을 모았다가 버퍼가 차거나 연결이 끝나야 흘려보내서
실시간 스트리밍이 사실상 깨진다. 참고로 `gzip_types` 목록에도 `text/event-stream`이 빠져
있어, gzip이 SSE 응답을 압축·버퍼링하는 사고도 함께 피해간다.

### 3.5 대용량 파일 업로드와 값 일치

`client_max_body_size 100M`(nginx, 1024 기준 100×1024×1024 = 104,857,600바이트)은
애플리케이션의 `MAX_FILE_SIZE=104857600`(`src/config.py`)과 정확히 같은 값이다. nginx가
먼저 요청을 자르면 애플리케이션 레벨 제한에는 도달할 일이 없으므로, 두 값이 어긋나면
한쪽 제한이 죽은 코드가 된다 — 값을 바꿀 때는 항상 같이 맞춰야 한다.

### 3.6 동시 연결 상한

`events { worker_connections 1024; }`이고 `worker_processes`를 별도 지정하지 않아 기본값
1(워커 프로세스 1개)이 적용된다. 일반 HTTP 요청은 응답 즉시 슬롯을 반환하지만,
`/ws/chat`처럼 최대 7일까지 열려 있을 수 있는 WebSocket이나 SSE 스트림은 그 기간 내내
슬롯 하나를 계속 점유한다 — 동시 접속자가 늘어나는 시나리오에서는 이 1024가 실질적인
상한선이 된다.

### 3.7 upstream 호스트명은 nginx 기동 시점에 딱 한 번만 resolve된다 (실측, 2026-08-01)

`upstream coding-agent { server coding-agent:8000; }`처럼 `server` 지시자에 변수 없이
호스트명을 직접 쓰면, nginx는 그 이름을 **워커 프로세스 기동 시점에 한 번만** DNS로
resolve하고 캐시한다(요청마다 다시 조회하지 않음). LAN 테스트 환경에서 `coding-agent`가
아직 안 떠 있는 상태로 nginx를 먼저 기동해보면 `host not found in upstream
"coding-agent:8000"` emerg 에러로 nginx가 **아예 시작조차 못 하고** 계속
crash-loop에 빠지는 걸 실측으로 확인했다. 이후 `coding-agent`가 뒤늦게 떠도, nginx
자체를 재시작(`docker compose restart nginx`)하기 전까지는 저절로 복구되지 않는다
(Docker의 `restart: unless-stopped` 재시도 타이밍에 우연히 걸리면 복구되지만
보장되지 않음). `deployment/docker-compose.yml`의 nginx `depends_on: [coding-agent]`가
정상적인 `docker compose up` 흐름에서는 이 순서를 보장해주지만, nginx만 따로
추가 기동할 때는(`scripts/start_nginx_selfsigned.sh` 등) 호출 순서를 직접 챙겨야 한다.

같은 이유로 **이미 정상적으로 떠 있던 `coding-agent`를 재배포(재빌드/재기동)해도**
문제가 생긴다 — 컨테이너가 재생성되면 새 컨테이너가 다른 내부 IP를 받는데
(도커 IPAM이 우연히 같은 IP를 재할당하는 경우도 있어 매번 재현되진 않음, 다른
컨테이너로 그 IP를 미리 점유시켜 강제로 재현·확인함), nginx는 처음 resolve한
옛 IP를 계속 쓰다가 **502 Bad Gateway**를 낸다. 이 경우도 `docker compose restart
nginx`로 즉시 복구된다. `scripts/redeploy_app.sh`가 coding-agent 재배포 후 nginx가
떠 있으면 이 재시작을 자동으로 같이 해준다.

---

## 4. 실시간 통신(WebSocket/SSE) 아키텍처

4개의 실시간 채널이 있고, 인증 방식과 nginx 타임아웃이 서로 다르다.

| 엔드포인트 | 프로토콜 | 인증 시점 | nginx 타임아웃 | 상태 저장 위치 | 용도 |
|---|---|---|---|---|---|
| `/ws/chat` | WebSocket | `accept()` 전 | **7일**(`/ws/`) | `ConnectionManager`(프로세스 메모리, `src/routes/chat.py`) | 툴 실행 없는 순수 LLM 채팅. 히스토리 최대 20개, 10자/줄바꿈 단위로 버퍼링해 전송 |
| `/api/v1/vscode/ws/{session_id}` | WebSocket | `accept()` 전 | **300초**(`/api/`) | `SessionManager`(프로세스 메모리 + 디스크) | VS Code 확장용 양방향 채널. 파일 업로드, 에이전트 실행 요청, 파일 변경/삭제 이벤트를 같은 소켓 하나로 멀티플렉싱 |
| `/api/v1/agent/ws/{task_id}` | WebSocket | `accept()` 전 | **300초**(`/api/`) | `TaskManager`(프로세스 메모리) | 이미 생성된 태스크를 실행하며 이벤트를 스트리밍 |
| `/api/v1/agent/task/{id}/execute` | SSE | 요청 헤더(`Authorization: Bearer`) | 300초(`/api/`) | `TaskManager` | 위와 동일한 이벤트를 SSE로 스트리밍 — WebSocket을 못 쓰는 클라이언트용 대안 경로 |

### 4.1 인증이 두 갈래로 나뉜 이유

FastAPI의 `HTTPBearer`는 Starlette `Request`(HTTP 전용) 객체에 의존한다. 라우터 레벨
`dependencies=[Depends(require_api_key)]`로 걸면 같은 라우터에 등록된 WebSocket
엔드포인트에도 적용되려다 `Request`를 못 받아 핸드셰이크 자체가 `TypeError` → HTTP 500으로
죽는다 — 이 문제는 실제 운영 중 발견되어 README.md의 "실전 배포에서 발견한 문제" 1번에
기록되어 있다. 그래서:

- **HTTP 엔드포인트**는 함수 시그니처에 개별적으로 `Depends(require_api_key)`를 건다.
- **WebSocket 엔드포인트**는 `await websocket.accept()` **이전에** `authenticate_websocket()`을
  직접 호출해 검증하고, 실패하면 `close(code=1008)`(정책 위반)로 끊는다(`src/auth.py`).

브라우저 WebSocket API는 커스텀 헤더를 못 보내므로, WebSocket 인증은 `?api_key=` 쿼리
파라미터도 허용한다(`Authorization: Bearer` 헤더도 폴백으로 지원). SSE는 일반 HTTP 요청이라
헤더 방식만 쓴다.

### 4.2 WebSocket 연결 자체에 대한 rate limit

`slowapi`는 HTTP 요청만 다루므로 WebSocket "연결 시도"에는 적용되지 않는다.
`src/rate_limit.py::check_ws_rate_limit`이 API 키(또는 IP)별 60초 고정 윈도우 카운터를
직접 구현해 `accept()` 전에 검사하고, 초과 시 `close(code=1013)`(Try Again Later)로 끊는다.
이 카운터도 4.4절과 마찬가지로 프로세스 메모리에 있다.

### 4.3 타임아웃 비대칭이 실제로 의미하는 것 (실측 완료, 2026-08-01)

3.2절에서 본 것처럼 `/api/v1/vscode/ws/{session_id}`와 `/api/v1/agent/ws/{task_id}`는
`/api/` location(300초 idle 타임아웃)에 걸리고, `/ws/chat`만 `/ws/` location(7일)에 걸린다.
에이전트 오케스트레이터는 최대 20회 반복이고 매 반복마다 LLM 추론 + 툴 실행(`run_tests`
등)이 들어가는데, 로컬에 nginx의 `/api/`·`/ws/` location 설정만 그대로 재현한 테스트
스택을 띄우고 세 경로를 300초+ 침묵시켜본 결과는 다음과 같았다:

| 경로 | nginx 타임아웃 | 실측 결과 |
|---|---|---|
| SSE `/api/v1/agent/task/{id}/execute` | 300s | **300.1초에 정확히 끊김**(`peer closed connection`) |
| WS `/api/v1/agent/ws/{task_id}` | 300s (같은 `/api/`) | 320초까지 생존 |
| WS `/ws/chat` | 7d | 320초까지 생존 |

WebSocket 2종이 같은 300초 설정인데도 살아남은 이유는 uvicorn(`websockets` 구현)이
애플리케이션 로직과 무관하게 자동으로 보내는 WS PING/PONG(기본 ~20초 간격) 때문이다.
nginx는 WS 업그레이드 이후 그 연결을 바이트 단위로 그냥 릴레이할 뿐이라, 이 PING도
"업스트림에서 온 데이터"로 카운트되어 `proxy_read_timeout`을 계속 리셋시킨다.
**반면 SSE는 순수 HTTP 스트리밍이라 이런 프로토콜 레벨 하트비트가 없어서, 침묵이
300초를 넘기면 예외 없이 nginx가 먼저 끊는다.** 즉 실제 위험은 WebSocket 2종이 아니라
SSE 엔드포인트 하나에 집중되어 있었다.

**근본 원인과 수정 (2026-08-01):** SSE가 침묵하는 이유는 nginx나 WS 프로토콜의 문제가
아니라, `src/agent/llm/ollama_client.py`의 Ollama 호출이 `stream=False`로 응답 전체가
완성될 때까지 기다렸다가 한 번에 반환하는 방식이었기 때문이다 — 이 대기 시간 내내
오케스트레이터(`orchestrator.py`)가 이벤트를 하나도 `yield`하지 않았다. 이를 고치기 위해
`LLMClient`에 `stream_next_actions()`를 추가하고(`src/agent/llm/base.py` — 논스트리밍
백엔드는 `get_next_actions_async()`를 감싸는 기본 구현으로 자동 호환), `OllamaAgentClient`가
`ollama.AsyncClient.chat(..., stream=True)`로 실제 토큰 스트리밍을 구현하도록 바꿨다.
오케스트레이터는 이제 각 iteration마다 토큰이 도착하는 대로 `{"type": "llm_token", ...}`
이벤트를 계속 흘려보내고, 전체 텍스트가 다 모이면 기존과 동일하게 파싱해 액션을 실행한다
(Structured Outputs `format=` 스키마 강제는 그대로 유지). 그 결과 SSE에도 실제 콘텐츠가
계속 흐르게 되어, uvicorn PING 같은 프로토콜 레벨 편법 없이도 300초 침묵 자체가 사라졌다.

### 4.4 연결이 실행 도중 끊기면 벌어지는 일

`TaskManager.execute_task`(`src/agent/task_manager.py`)는 오케스트레이터 이벤트를 그대로
`yield`해서 WS/SSE로 전달한다. 클라이언트(또는 위 4.3절처럼 nginx)가 스트리밍 도중 연결을
끊으면 `asyncio.CancelledError`가 발생하는데, 이는 Python 3.8+에서 `Exception`이 아니라
`BaseException` 계열이라 `except Exception`에는 안 잡힌다. `finally` 블록에서 태스크 상태가
여전히 `RUNNING`이면 명시적으로 `fail()` 처리해 영구 `running` 상태로 남는 것을 막는다
(`CancelledError` 자체는 삼키지 않고 그대로 전파시켜 취소 시맨틱은 보존한다). 이 문제는
실제 LAN 배포 중 SSE 연결이 클라이언트 측 타임아웃으로 끊기면서 재현된 뒤 수정됐다
(커밋 `596ab1f`).

### 4.5 상태가 전부 "프로세스 메모리"에 있다는 제약

`TaskManager`, `SessionManager`, WebSocket rate-limit 카운터, `/ws/chat`의
`ConnectionManager` 전부 단일 프로세스 메모리 상의 dict/deque다. 그래서 `WORKERS=1`이
강제되어 있다(`docker-compose.yml` 주석: "워커 간 상태 불일치 유발"). Uvicorn 워커를
늘리거나 컨테이너를 여러 대로 스케일아웃하면, 요청이 다른 워커/인스턴스로 라우팅되는
순간 "태스크를 찾을 수 없음"류 오류가 나거나 세션이 안 보이게 된다. Redis 도입 전까지는
수평 확장이 불가능한 구조다(README.md Phase 3+ 항목).

### 4.6 세션 만료와 정리

`SessionManager.cleanup_expired_sessions()`(기본 30분 비활성 기준)는 `main.py`의
`startup_event`에서 `periodic_session_cleanup()`을 `asyncio.create_task()`로 띄워 300초
(`SESSION_CLEANUP_INTERVAL_SECONDS`)마다 자동 호출하고, `shutdown_event`에서 `cancel()`로
정리한다(커밋 `2ef06d3`). `/api/v1/vscode/ws/{session_id}`가 받는 `ping` 메시지는
`session.update_activity()`를 갱신하므로, 클라이언트가 주기적으로 ping을 보내는 한 그
세션은 만료되지 않는다.

---

## 5. 모니터링/관측 스택 네트워크

| 컴포넌트 | 역할 |
|---|---|
| Prometheus(:9090) | `deployment/prometheus/prometheus.yml` 기준 15초 간격으로 4개 타깃(`coding-agent:8000/metrics`, 자기 자신, `node-exporter:9100`, `cadvisor:8080`)을 스크레이핑. `alert_rules.yml` 평가 결과를 `alertmanager:9093`으로 전달 |
| Alertmanager(:9093) | webhook 라우팅(`group_wait 30s`, `group_interval 5m`, `repeat_interval 3h`). 실제 webhook URL은 `.yml.example`을 복사해 채우며 `.gitignore` 대상 |
| Grafana(:3000) | 데이터소스로 Prometheus를 프로비저닝, `coding-agent.json` 대시보드 자동 로드 |
| node-exporter(:9100) | 호스트 CPU/메모리/디스크 등 시스템 메트릭 |
| cadvisor(:8080) | 컨테이너별 리소스 사용량/재시작 횟수 — 컨테이너 재시작 루프 감지에 사용 |

`alert_rules.yml`에 정의된 알람 5종:

- **InstanceDown** — 2분 이상 스크레이핑 실패
- **GenerateEndpointHighErrorRate** — `/api/v1/generate`의 5xx 비율이 5분 평균 5% 초과 (이
  지표는 `src/routes/generate.py`에서만 기록되므로 전체 API가 아닌 이 엔드포인트에 한정됨)
- **GenerateLatencyHigh** — 코드 생성 p95 지연시간 30초 초과
- **DiskSpaceLow** / **HostMemoryLow** — 루트 파일시스템/메모리 여유 10% 미만
- **ContainerRestartingTooOften** — 15분 내 3회 이상 재시작(크래시 루프 감지)

**요청 추적**: `RequestIDMiddleware`(`src/logging_setup.py`)가 모든 HTTP 요청에
`request_id`를 부여하고 `X-Request-ID` 응답 헤더로 돌려준다. WebSocket 경로는 HTTP
미들웨어를 안 타므로 각 핸들러 시작 시 `bind_new_request_id()`를 수동 호출한다. 모든
로그는 JSON 한 줄 포맷(`request_id` 필드 포함)이라 Loki 등 로그 수집기가 필드 단위로
검색·상관관계 분석을 할 수 있다.

### 5.1 데이터소스 UID가 어긋나면 전 패널이 조용히 빈다 (실측, 2026-08-13)

`coding-agent.json`의 패널들은 데이터소스를 `{"type": "prometheus", "uid": "prometheus"}`로
참조하는데, `provisioning/datasources/prometheus.yml`에 `uid`가 없으면 Grafana가 임의의
UID(실측값 `PBFA97CFB590B2093`)를 부여한다. 그 결과 **대시보드의 모든 패널이 "No data"로
뜬다.**

진단이 까다로운 이유는 아래가 전부 정상으로 보이기 때문이다:

- Prometheus 타깃 4개 전부 `up`
- `/metrics`에 값이 정상적으로 쌓임
- Prometheus에 직접 질의(`:9090/api/v1/query`)하면 데이터가 나옴
- Grafana 자체도 `/api/health`가 `ok`

구분 포인트는 **패널 제목 옆의 경고 아이콘**이다. 데이터가 없는 게 아니라 쿼리가
에러를 낸 것이므로, 진짜 "데이터 없음"과는 표시가 다르다. 확인은 Grafana의
데이터소스 프록시로 우회 질의해보면 가장 빠르다:

```bash
curl -s -u "admin:$PW" --get \
  "http://localhost:3000/api/datasources/proxy/uid/prometheus/api/v1/query" \
  --data-urlencode 'query=sum(api_requests_total)'
# 데이터소스가 없으면 여기서 바로 실패한다
curl -s -u "admin:$PW" http://localhost:3000/api/datasources   # 실제 uid 확인
```

수정은 프로비저닝에 `uid: prometheus`를 명시하는 것이다. 단, **그것만 하면 기존 배포는
기동 자체에 실패한다** — `grafana-data` 볼륨에 옛 UID의 데이터소스가 남아 있으면
Grafana가 `Datasource provisioning error: data source not found`를 내며 크래시 루프에
빠진다(실측). 같은 이름의 데이터소스를 먼저 지우도록 `deleteDatasources`를 함께 둬야
새 배포·기존 배포 양쪽에서 자가 복구된다.

### 5.2 대시보드 패널과 실제 계측 지점은 따로 논다 (실측, 2026-08-13)

메트릭이 **선언만 되어 있고 어디서도 `observe()`/`inc()`되지 않아도** 대시보드 패널은
아무 경고 없이 만들어진다. `api_response_time_seconds`가 그런 경우였고, 해당 패널은 어떤
부하를 넣어도 영구히 비어 있었다 — 2026-08-13에 메트릭 선언과 패널을 함께 제거했다.

남은 앱 메트릭이 실제로 증가하는 경로는 아래로 한정된다:

| 메트릭 | 증가하는 경로 | 증가하지 **않는** 경로 |
|---|---|---|
| `api_requests_total`, `model_inference_time_seconds` | `POST /api/v1/generate` | 에이전트 태스크 실행 전체 |
| `file_operations_total` | Files API(`/api/v1/files/*`) | 에이전트의 `file_tools` 툴 실행 |
| `active_websockets`, `active_chat_clients` | `/ws/chat` | `/api/v1/vscode/ws/*`, `/api/v1/agent/ws/*` |

즉 **에이전트 태스크(`agent ask`)를 아무리 돌려도 앱 패널은 하나도 움직이지 않는다.**
에이전트 실행 경로에 아직 계측이 없기 때문이며, 대시보드만 보고 "사용량 없음"으로
오해하기 쉽다. 8장(알려진 한계)에 후속 과제로 정리해 둔다.

### 5.3 소켓 수 · 활성 client_id 수 · 대화 기록은 전부 다른 값이다 (실측, 2026-08-13)

`ConnectionManager`(`src/routes/chat.py`)는 서로 다른 세 가지를 들고 있다.

| | 세는 단위 | 수명 |
|---|---|---|
| `active_websockets` | 소켓 1개 = 1 | 연결이 끊기면 즉시 감소 |
| `active_chat_clients` | 연결을 1개 이상 가진 `client_id` = 1 | 그 클라이언트의 마지막 소켓이 닫힐 때 감소 |
| `conversation_history` | `client_id`별 대화 기록 | **연결과 무관하게 계속 유지** |

한 클라이언트가 창을 3개 열면 소켓은 3, 활성 `client_id`는 1이다. 소켓 수만으로는 접속
주체가 몇인지 알 수 없어 2026-08-13에 `active_chat_clients`를 추가했다. 실측 동작:

```
alice 창 3개          -> 소켓 3 / client_id 1
+ bob 창 1개          -> 소켓 4 / client_id 2
alice 창 2개 닫음      -> 소켓 2 / client_id 2   (alice가 아직 1개 남음)
alice 마지막 창 닫음    -> 소켓 1 / client_id 1
전부 닫음             -> 소켓 0 / client_id 0   (누수 없음)
```

**`active_chat_clients`를 "사용자 수"로 읽으면 안 된다.** `client_id`는
`/ws/chat?client_id=...` 쿼리 파라미터로 **클라이언트가 스스로 declare하는 값**이고,
`authenticate_websocket()`이 검증한 신원(`AuthenticatedKey`)과는 아무 관계가 없다.
같은 API 키로 서로 다른 `client_id`를 얼마든지 만들 수 있다. 특히 기본값이 `"default"`라
**`client_id`를 안 보내는 클라이언트는 몇이 붙든 전부 1로 합쳐진다** — 실측으로
`client_id` 없이 4개를 연결했을 때 소켓 4 / `client_id` 1이 나왔다. 어디까지나 사용자
수의 대리 지표이며, 클라이언트가 고유한 값을 보내줄 때만 의미가 있다. 검증된 신원 기준으로
집계하려면 `identity.key`를 집계 키로 쓰도록 바꿔야 한다(8장 참고).

두 게이지 모두 Gauge라 누적이 아니다. 다만 `disconnect()`가 호출되지 않는 예외 경로가
하나라도 생기면 값이 단조 증가해 사실상 누적처럼 망가지므로, `disconnect()`는 중복
호출에 대해 멱등하게 구현돼 있다.

**대화 기록은 연결보다 오래 산다.** 연결을 전부 끊었다가 같은 `client_id`로 재접속하면
이전 대화를 그대로 이어받는 것을 실측으로 확인했다(의도된 동작). 반대급부로
`conversation_history`는 `disconnect()`에서 지워지지 않아 **새로운 `client_id`가 등장할
때마다 항목이 쌓이고 회수되지 않는다** — 항목당 최대 20개 메시지로 제한돼 폭발적이진
않지만 단조 증가하는 인메모리 누수다. 에이전트 세션 쪽(`SessionManager`)에 있는
`periodic_session_cleanup` 같은 정리 장치가 여기에는 없다(8장 참고).

---

## 6. 컨테이너 실행/보안 경계

- **non-root 실행**: uid 1000(`appuser`)으로 실행하며, `/workspace`만 `chmod 777`로 열어
  호스트 바인드 마운트의 UID 불일치를 흡수한다(`/app`은 소유권 제한 유지).
- **Graceful shutdown**: `uvicorn --timeout-graceful-shutdown 25`(초) <
  `stop_grace_period: 30s`(docker-compose) — SIGTERM 수신 후 진행 중인 WS/SSE 스트림이
  정리될 시간을 확보한다.
- **헬스체크**: `curl -f localhost:8000/health`를 30초 간격으로 실행하며, Ollama 연결·모델
  존재 여부·에이전트 초기화 상태·워크스페이스 쓰기 가능 여부·태스크 통계까지 확인한다.
- **셸 실행 차단**: `run_command` 툴은 공개 API(HTTP/WS)의 `ToolExecutor`에는 아예 등록되지
  않는다. 로컬 신뢰 경계인 MCP 서버(`src/mcp_server.py`)에서만 활성화된다.

---

## 7. TLS 발급/갱신 흐름

`scripts/init_letsencrypt.sh`가 최초 인증서 발급을 5단계로 처리한다:

1. 더미 인증서(자체 서명, 1일 유효)를 생성해 nginx가 443을 열 수 있게 함
2. nginx 기동
3. 더미 인증서 삭제
4. `certbot certonly --webroot`로 실제 인증서 발급 요청(80번 포트,
   `/.well-known/acme-challenge/` 경로, 사전에 DNS A 레코드와 80/443 포트 도달 가능성 필요)
5. nginx 재시작(실제 인증서 반영)

이후 `certbot` 컨테이너가 `while true; do certbot renew; sleep 12h; done` 루프로 12시간마다
갱신을 시도한다(certbot이 만료 30일 이내인 인증서만 실제로 갱신). 인증서 파일은
`certbot-etc` 볼륨을 통해 nginx와 공유되지만, **nginx 프로세스 자체는 갱신을 감지해
자동으로 reload하지 않는다** — 갱신된 인증서를 실제로 반영하려면 `nginx` 컨테이너 재시작이
별도로 필요할 수 있고, 현재 이 부분은 자동화되어 있지 않다.

### 7.1 공인 도메인 없이 LAN에서 nginx만 검증하기

`init_letsencrypt.sh`의 4단계(실제 인증서 발급)는 공인 도메인 + 80/443 외부 도달성이
필요해 LAN 전용 배포에서는 쓸 수 없다. `scripts/deploy.sh`도 `DOMAIN`이 비어있거나
placeholder(`lan-test.local`)면 nginx/certbot 자체를 SERVICES에서 빼고 기동하므로,
LAN 환경에서는 기본적으로 nginx가 아예 없는 상태다. nginx의 실제 리버스 프록시 동작
(location 라우팅, 타임아웃, 인증 헤더 전달 등)을 LAN에서 직접 검증하고 싶다면
`scripts/start_nginx_selfsigned.sh`를 쓴다 — `init_letsencrypt.sh`의 1~2단계(더미
인증서 생성 + nginx 기동)만 수행하고 3~5단계(실제 인증서 교체)는 건너뛴 채 자체 서명
인증서로 계속 유지한다. 클라이언트는 인증서 검증을 꺼야 한다(`curl -k`, 브라우저
경고 무시). `coding-agent`가 먼저 떠 있어야 하는 이유는 3.7절 참고.

---

## 8. 알려진 한계 / 향후 과제

- ~~9090/9093/3000/8080/9100/11434 포트가 nginx 없이 호스트에 직접 게시되어 있던 문제~~ —
  2026-07-28에 해당 6개 서비스의 호스트 `ports:` 게시를 제거해 해결.
- `coding-agent`의 8000만 여전히 호스트에 게시되어 있다 — `scripts/deploy.sh`가 `DOMAIN`
  미설정 시(LAN 테스트 배포) nginx/certbot을 안 띄우기 때문에 남겨둔 의도적 예외다(2.2절).
  이 상태에서는 nginx의 TLS 종료·`/metrics` 내부망 제한이 8000 직접 접근으로 우회 가능하다.
  근본적으로 없애려면 `DOMAIN` 없이도 nginx를 HTTP 전용으로 띄우도록 `deploy.sh`/
  `nginx.conf.template`을 먼저 고쳐야 한다 — Phase 3(퍼블릭 도메인) 전환 시 함께 정리할 것.
  (`scripts/start_nginx_selfsigned.sh`로 LAN에서 nginx 자체 동작은 검증할 수 있게 됐지만,
  8000 직접 노출 자체를 없애주지는 않는다 — 7.1절 참고.)
- `WORKERS=1` 고정 — Redis 기반 상태 공유 도입 전까지 단일 프로세스이며 수평 확장 불가.
- ~~`/api/` 경로 SSE(`/api/v1/agent/task/{id}/execute`)가 LLM 추론 중 300초 이상
  침묵하면 nginx idle 타임아웃에 끊기던 문제~~ — 2026-08-01 실측으로 확인 후,
  `OllamaAgentClient`에 토큰 스트리밍(`stream_next_actions`)을 추가해 해결(4.3절).
  같은 300초 설정이 걸리는 WebSocket 2종(vscode, agent)은 uvicorn의 자동 WS PING
  덕분에 애초에 실질적 위험이 아니었던 것도 실측으로 확인됨.
- certbot 인증서 갱신 후 nginx 자동 reload가 구성되어 있지 않음.
- **에이전트 실행 경로에 메트릭 계측이 없다** — `agent ask`로 태스크를 돌려도 대시보드의
  앱 패널은 하나도 움직이지 않는다(5.2절). 태스크 수/반복 횟수/툴 실행 결과/LLM 추론
  시간을 오케스트레이터와 `ToolExecutor`에 계측해야 실제 사용량이 관측 가능해진다.
  지금은 `/api/v1/generate`와 Files API만 계측돼 있어 대시보드가 실사용을 대표하지 못한다.
- **`active_chat_clients`가 검증된 신원 기준이 아니다** — 클라이언트가 스스로 보내는
  `client_id` 쿼리 파라미터로 집계하므로, 값을 생략하면 전부 `"default"` 하나로 합쳐지고
  임의로 조작할 수도 있다(5.3절). 인증된 신원 기준으로 바꾸려면 `identity.key`를 집계
  키로 쓰면 되지만, 키를 여러 사람이 공유하는 경우는 여전히 구분되지 않는다.
- **`/ws/chat`의 `conversation_history`가 회수되지 않는다** — `disconnect()`가 대화
  기록을 지우지 않아(재접속 시 이어가기 위한 의도된 동작) 새 `client_id`가 등장할 때마다
  항목이 쌓인다. 항목당 20개 메시지 상한이 있어 폭발적이진 않지만 단조 증가하는 인메모리
  누수이며, `SessionManager`의 `periodic_session_cleanup`에 해당하는 정리 장치가 없다.
- 퍼블릭 도메인 배포는 아직 진행 전(README.md Phase 3) — 현재는 LAN 환경에서의 실사용
  검증 단계.

---

## 참고

- 배포 절차 전반/하드닝 진행 상황: [README.md](../README.md)
- 컴포넌트·API·코드 구조: [PROJECT_STRUCTURE.md](../PROJECT_STRUCTURE.md)
- 실제 설정 파일: `deployment/nginx/nginx.conf.template`, `deployment/docker-compose.yml`,
  `deployment/prometheus/`, `deployment/alertmanager/`, `docker/Dockerfile.prod`
