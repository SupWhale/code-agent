# Code Agent - 프로젝트 구조 분석 문서

> 작성일: 2026-04-12

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [디렉토리 구조](#2-디렉토리-구조)
3. [기술 스택](#3-기술-스택)
4. [컴포넌트 상세 설명](#4-컴포넌트-상세-설명)
5. [시스템 아키텍처](#5-시스템-아키텍처)
6. [API 엔드포인트](#6-api-엔드포인트)
7. [에이전트 실행 흐름](#7-에이전트-실행-흐름)
8. [보안 구조](#8-보안-구조)
9. [배포 구성](#9-배포-구성)
10. [의존성 목록](#10-의존성-목록)

---

## 1. 프로젝트 개요

**Code Agent**는 LLM(Large Language Model)을 활용한 자율 코딩 에이전트 시스템입니다.

### 핵심 기능

- LLM 기반 코드 자동 읽기, 분석, 수정
- CLI 터미널 및 VS Code 확장 지원 (이중 인터페이스)
- WebSocket 기반 실시간 스트리밍 응답
- 세션 격리된 워크스페이스 관리
- Prometheus + Grafana 기반 모니터링

### 사용 LLM

- **모델:** `qwen2.5-coder:7b`
- **런타임:** [Ollama](https://ollama.com) (로컬 실행)

---

## 2. 디렉토리 구조

```
code-agent/
├── agent                           # CLI 실행 스크립트 (bash)
│
├── cli/                            # 터미널 CLI 인터페이스
│   ├── main.py                     # CLI 진입점 (Typer 기반)
│   ├── client.py                   # HTTP/WebSocket 클라이언트
│   ├── config.py                   # 설정 관리자
│   ├── README.md                   # CLI 사용 가이드 (한국어)
│   └── requirements.txt            # CLI 전용 의존성
│
├── src/                            # 백엔드 서버
│   ├── main.py                     # FastAPI 애플리케이션
│   ├── routes/                     # API 라우터
│   │   ├── agent.py                # 에이전트 태스크 관리 엔드포인트
│   │   └── vscode.py               # VS Code 확장 전용 엔드포인트
│   └── agent/                      # 핵심 에이전트 시스템
│       ├── orchestrator.py         # 메인 오케스트레이터 (에이전트 루프)
│       ├── executor.py             # 툴 실행 엔진
│       ├── task_manager.py         # 태스크 생명주기 관리
│       ├── session_manager.py      # 클라이언트 세션 격리
│       ├── llm/
│       │   └── ollama_client.py    # Ollama LLM 통신
│       ├── memory/
│       │   ├── conversation.py     # 대화 기록 관리
│       │   └── task_state.py       # 태스크 상태 추적
│       ├── security/
│       │   └── validator.py        # 보안 검증기
│       └── tools/
│           ├── base.py             # 툴 기본 인터페이스
│           ├── file_tools.py       # 파일 읽기/수정/생성/삭제
│           ├── search_tools.py     # 파일 목록/코드 검색
│           ├── test_tools.py       # 테스트 실행
│           ├── interaction_tools.py # 사용자 상호작용
│           └── sync_tools.py       # 파일 동기화
│
├── prompts/
│   └── system_prompt.txt           # 에이전트용 LLM 시스템 프롬프트 (11.2KB)
│
├── deployment/                     # 프로덕션 배포 설정
│   ├── docker-compose.yml          # 프로덕션 멀티 서비스 구성
│   ├── grafana/                    # Grafana 대시보드
│   ├── prometheus/                 # Prometheus 메트릭 설정
│   └── nginx/                      # Nginx 리버스 프록시 설정
│
├── docker/                         # Docker 이미지 빌드
│   ├── Dockerfile.prod             # 프로덕션 이미지
│   ├── Dockerfile.dev              # 개발 이미지
│   └── docker-compose.dev.yml      # 개발 환경 구성
│
├── scripts/                        # 운영 스크립트
│   ├── deploy.sh                   # 배포 스크립트
│   ├── deploy_to_server.sh         # 서버 배포
│   ├── dev.sh                      # 개발 실행기
│   └── rollback.sh                 # 롤백 스크립트
│
├── requirements.txt                # 프로덕션 의존성
├── requirements-dev.txt            # 개발 의존성
└── .vscode/                        # VS Code 편집기 설정
```

---

## 3. 기술 스택

| 분류 | 기술 | 버전 |
|------|------|------|
| **백엔드 프레임워크** | FastAPI | 0.109.2 |
| **ASGI 서버** | Uvicorn | 0.27.1 |
| **LLM 런타임** | Ollama | 0.1.7 |
| **LLM 모델** | qwen2.5-coder | 7b |
| **CLI 프레임워크** | Typer | latest |
| **데이터 검증** | Pydantic | 2.6.1 |
| **통신 프로토콜** | HTTP + WebSocket | - |
| **비동기 파일 IO** | aiofiles | 23.2.1 |
| **컨테이너** | Docker + GPU(Nvidia) | - |
| **모니터링** | Prometheus + Grafana | latest |
| **리버스 프록시** | Nginx | alpine |
| **언어** | Python | 3.11+ |

---

## 4. 컴포넌트 상세 설명

### 4.1 백엔드 서버 (`src/`)

#### `src/main.py` - FastAPI 애플리케이션

전체 백엔드의 진입점으로, 다음 기능을 담당합니다:

- FastAPI 앱 초기화 및 라우터 등록
- `/health` 헬스체크 (Ollama 연결 상태 확인 포함)
- `/api/v1/generate` - 코드 생성 엔드포인트
- `/api/v1/analyze/*` - 파일/프로젝트 분석
- `/api/v1/files/*` - 파일 업로드, 목록, 읽기, 다운로드
- `/ws/chat` - WebSocket 스트리밍 채팅
- Prometheus 메트릭 수집

#### `src/agent/orchestrator.py` - 에이전트 오케스트레이터

에이전트의 핵심 실행 루프를 담당합니다:

- **최대 반복 횟수:** 20회
- 매 반복: 대화 기록 → Ollama LLM 요청 → JSON 액션 파싱 → 툴 실행 → 결과 기록
- 이벤트를 WebSocket 스트림으로 실시간 전송 (async generator)

#### `src/agent/executor.py` - 툴 실행 엔진

툴 레지스트리 및 디스패처:

- 등록된 툴 관리
- 툴 이름 기반 실행 라우팅
- 실행 결과 반환

#### `src/agent/task_manager.py` - 태스크 관리자

태스크 생명주기 관리:

```
pending → running → completed / failed
```

- 여러 태스크 동시 관리
- 태스크 상태 조회 API 지원

#### `src/agent/session_manager.py` - 세션 관리자

VS Code 확장 및 CLI 클라이언트별 격리된 세션 관리:

- 세션별 독립 워크스페이스: `/tmp/sessions/{session_id}`
- 세션 생성/삭제/조회

#### `src/agent/llm/ollama_client.py` - LLM 클라이언트

Ollama API 통신:

- 시스템 프롬프트 + 대화 기록 조합
- LLM 응답에서 JSON 액션 파싱
- 스트리밍 응답 처리

#### `src/agent/memory/` - 메모리 관리

| 파일 | 역할 |
|------|------|
| `conversation.py` | 대화 기록 유지 (최대 20개 항목) |
| `task_state.py` | 태스크 실행 중 상태 추적 |

#### `src/agent/security/validator.py` - 보안 검증기

모든 파일 경로 및 명령어 검증:

- 경로 탐색 공격(Path Traversal) 방지
- 위험 명령어 화이트리스트 기반 필터링
- 파일 크기 제한 (최대 100MB)

#### `src/agent/tools/` - 에이전트 툴셋

LLM이 사용할 수 있는 도구 모음:

| 툴 | 파일 | 기능 |
|----|------|------|
| `read_file` | file_tools.py | 파일 내용 읽기 |
| `edit_file` | file_tools.py | 파일 내용 수정 |
| `create_file` | file_tools.py | 새 파일 생성 |
| `delete_file` | file_tools.py | 파일 삭제 |
| `list_files` | search_tools.py | 디렉토리 파일 목록 |
| `search_code` | search_tools.py | 코드 내 패턴 검색 |
| `run_tests` | test_tools.py | 테스트 실행 |
| `run_command` | interaction_tools.py | 셸 명령 실행 |
| `ask_user` | interaction_tools.py | 사용자에게 질문 |
| `finish` | interaction_tools.py | 태스크 완료 선언 |
| `report_error` | interaction_tools.py | 오류 보고 |

---

### 4.2 CLI 클라이언트 (`cli/`)

#### `cli/main.py` - CLI 진입점

Typer 기반 CLI 명령어 제공:

| 명령어 | 기능 |
|--------|------|
| `./agent status` | 서버 상태 확인 |
| `./agent session` | 세션 정보 조회 |
| `./agent files` | 워크스페이스 파일 목록 |
| `./agent ask "<요청>"` | 단일 에이전트 태스크 실행 |
| `./agent chat` | 대화형 채팅 모드 |

#### `cli/client.py` - HTTP/WebSocket 클라이언트

백엔드 서버와의 통신 담당:

- httpx 기반 HTTP 요청
- websockets 기반 WebSocket 연결
- 이벤트 스트림 수신 및 출력

#### `cli/config.py` - 설정 관리자

사용자 설정 파일 관리:

- 설정 위치: `~/.config/code-agent/config.json`
- 서버 URL, 세션 ID 저장

---

### 4.3 시스템 프롬프트 (`prompts/system_prompt.txt`)

에이전트 LLM에게 전달되는 11.2KB 크기의 상세 지시문:

- 사용 가능한 툴 목록 및 파라미터 명세
- JSON 응답 형식 규칙
- 코드 수정 시 주의사항
- 반복 실행 전략 가이드

---

## 5. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                         사용자 인터페이스                         │
│  ┌───────────────────────────┐  ┌──────────────────────────┐   │
│  │      CLI (./agent)        │  │    VS Code Extension     │   │
│  │  ask, chat, files, status │  │   WebSocket 채팅/동기화   │   │
│  └─────────────┬─────────────┘  └────────────┬─────────────┘   │
└────────────────┼──────────────────────────────┼─────────────────┘
                 │       HTTP + WebSocket        │
┌────────────────▼──────────────────────────────▼─────────────────┐
│                   FastAPI 백엔드 (src/main.py)                   │
│                                                                   │
│  /api/v1/agent/*    /api/v1/vscode/*    /api/v1/files/*         │
│  /api/v1/generate   /api/v1/analyze/*   /ws/chat                │
└─────────────────────────────┬───────────────────────────────────┘
                               │
               ┌───────────────┼───────────────┐
               │               │               │
        ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
        │TaskManager  │ │SessionMgr   │ │ Prometheus  │
        │(태스크 관리) │ │(세션 격리)  │ │  (메트릭)   │
        └──────┬──────┘ └─────────────┘ └─────────────┘
               │
        ┌──────▼──────────────────────────────────────┐
        │           AgentOrchestrator                  │
        │   (최대 20회 반복 에이전트 실행 루프)          │
        └──────┬──────────────────────┬────────────────┘
               │                      │
        ┌──────▼──────┐       ┌────────▼────────┐
        │ Ollama LLM  │       │  ToolExecutor   │
        │ qwen2.5-coder│      │  (툴 디스패처)  │
        └─────────────┘       └────────┬────────┘
                                        │
                         ┌──────────────┼──────────────┐
                         │              │              │
                  ┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼─────┐
                  │ file_tools  │ │search_tools│ │test_tools │
                  │ (파일 조작) │ │(코드 검색) │ │(테스트)   │
                  └─────────────┘ └───────────┘ └───────────┘
                         │
                  ┌──────▼──────────┐
                  │SecurityValidator│
                  │ (경로/명령 검증) │
                  └─────────────────┘
```

---

## 6. API 엔드포인트

### 에이전트 API (`/api/v1/agent/`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/v1/agent/tasks` | 새 태스크 생성 |
| `GET` | `/api/v1/agent/tasks/{task_id}` | 태스크 상태 조회 |
| `GET` | `/api/v1/agent/tasks` | 전체 태스크 목록 |
| `DELETE` | `/api/v1/agent/tasks/{task_id}` | 태스크 삭제 |
| `POST` | `/api/v1/agent/tasks/{task_id}/execute` | 태스크 실행 |

### VS Code 확장 API (`/api/v1/vscode/`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/v1/vscode/sessions` | 세션 생성 |
| `GET` | `/api/v1/vscode/sessions/{id}` | 세션 조회 |
| `DELETE` | `/api/v1/vscode/sessions/{id}` | 세션 삭제 |
| `WS` | `/api/v1/vscode/ws/{session_id}` | WebSocket 스트리밍 |
| `GET` | `/api/v1/vscode/files/{session_id}` | 세션 파일 목록 |

### 파일 API (`/api/v1/files/`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/v1/files/upload` | 파일 업로드 |
| `GET` | `/api/v1/files/` | 파일 목록 |
| `GET` | `/api/v1/files/{path}` | 파일 읽기 |
| `GET` | `/api/v1/files/{path}/download` | 파일 다운로드 |

### 기타 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/health` | 헬스체크 (Ollama 연결 확인) |
| `POST` | `/api/v1/generate` | 코드 생성 |
| `GET/POST` | `/api/v1/analyze/*` | 파일/프로젝트 분석 |
| `GET` | `/metrics` | Prometheus 메트릭 |
| `WS` | `/ws/chat` | WebSocket 채팅 |

---

## 7. 에이전트 실행 흐름

### CLI에서 태스크 실행

```
사용자
  └─> ./agent ask "버그를 수정해줘"
        └─> cli/main.py::ask()
              └─> cli/client.py::run_agent()
                    └─> WebSocket 연결 → /api/v1/vscode/ws/{session_id}
                          └─> routes/vscode.py::websocket_handler()
                                └─> AgentOrchestrator::execute_task()
                                      │
                                      ├─ [반복 1~20회]
                                      │    ├─ ConversationMemory에서 대화 기록 읽기
                                      │    ├─ OllamaClient::chat() → LLM 요청
                                      │    ├─ JSON 액션 파싱
                                      │    │    예: {"action": "read_file", "path": "main.py"}
                                      │    ├─ SecurityValidator::validate()
                                      │    ├─ ToolExecutor::execute()
                                      │    ├─ 결과를 ConversationMemory에 저장
                                      │    └─ 이벤트를 WebSocket으로 스트리밍
                                      │
                                      └─ finish 액션 또는 최대 반복 도달 → 종료
```

### LLM 응답 JSON 형식

```json
{
  "action": "edit_file",
  "path": "src/main.py",
  "content": "수정된 파일 내용",
  "reason": "버그 수정: null 체크 추가"
}
```

---

## 8. 보안 구조

### `src/agent/security/validator.py`

| 보안 항목 | 구현 방식 |
|-----------|----------|
| 경로 탐색 방지 | 절대 경로 정규화 후 워크스페이스 경계 확인 |
| 명령어 제한 | 허용 명령어 화이트리스트 기반 필터링 |
| 파일 크기 제한 | 최대 100MB (`MAX_FILE_SIZE=104857600`) |
| 세션 격리 | 클라이언트별 `/tmp/sessions/{id}` 격리 워크스페이스 |

---

## 9. 배포 구성

### Docker Compose 서비스 구성

| 서비스 | 이미지 | 포트 | 역할 | GPU |
|--------|--------|------|------|-----|
| `ollama` | ollama/ollama:latest | 11434 | LLM 런타임 | Nvidia GPU |
| `coding-agent` | 커스텀 (Dockerfile.prod) | 8000 | FastAPI 백엔드 | - |
| `nginx` | nginx:alpine | 80 / 443 | 리버스 프록시 | - |
| `prometheus` | prom/prometheus:latest | 9090 | 메트릭 수집 | - |
| `grafana` | grafana/grafana:latest | 3000 | 모니터링 대시보드 | - |
| `node-exporter` | prom/node-exporter:latest | 9100 | 시스템 메트릭 | - |

### 주요 환경 변수

```env
OLLAMA_HOST=http://ollama:11434
MODEL_NAME=qwen2.5-coder:7b
API_PORT=8000
LOG_LEVEL=INFO
WORKSPACE_PATH=/workspace
MAX_FILE_SIZE=104857600
WORKERS=4
```

### 공유 볼륨

```
/workspace          # 파일 작업용 공유 워크스페이스
./models            # Ollama 모델 캐시
prometheus-data     # Prometheus 데이터 저장소
grafana-data        # Grafana 대시보드 저장소
```

### 배포 스크립트

| 스크립트 | 용도 |
|----------|------|
| `scripts/deploy.sh` | 일반 배포 |
| `scripts/deploy_to_server.sh` | 원격 서버 배포 |
| `scripts/dev.sh` | 개발 환경 실행 |
| `scripts/rollback.sh` | 이전 버전 롤백 |

---

## 10. 의존성 목록

### 프로덕션 (`requirements.txt`)

```
fastapi==0.109.2
uvicorn[standard]==0.27.1
pydantic==2.6.1
ollama==0.1.7
prometheus-client==0.19.0
aiofiles==23.2.1
websockets==12.0
python-multipart==0.0.6
```

### 개발 (`requirements-dev.txt`)

```
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
httpx==0.25.2
```

### CLI (`cli/requirements.txt`)

```
typer
rich
httpx
websockets
```

---

## 참고

- CLI 사용 가이드: [cli/README.md](cli/README.md)
- 에이전트 시스템 프롬프트: [prompts/system_prompt.txt](prompts/system_prompt.txt)
- 프로덕션 배포 설정: [deployment/docker-compose.yml](deployment/docker-compose.yml)