# AI Coding Agent System

완전히 구현된 AI 코딩 에이전트 시스템입니다. Ollama와 Qwen2.5-Coder 14B 모델을 사용하여 코드 생성, 파일 관리, 테스트 실행 등을 자율적으로 수행합니다.

## 🎉 구현 완료

**Phase 1-7 모두 완료!**

- ✅ **138 tests passed, 6 skipped**
- ✅ **59% code coverage**
- ✅ **11개 도구** (파일, 검색, 테스트, 상호작용)
- ✅ **REST API** + **WebSocket** 지원
- ✅ **보안 검증** (경로 탐색 방지, 명령 주입 방지)

---

## 📋 시스템 아키텍처

```
┌─────────────────────────────────────────┐
│         FastAPI Application             │
│  (POST /api/v1/agent/task, WebSocket)   │
└──────────────┬──────────────────────────┘
               │
               ▼
     ┌─────────────────┐
     │  TaskManager    │  (작업 관리)
     └────────┬────────┘
              │
              ▼
     ┌─────────────────┐
     │ AgentOrchestrator│  (LLM ↔ Tools 반복)
     └────┬────────┬────┘
          │        │
   ┌──────▼──┐  ┌─▼──────────┐
   │ LLM     │  │ToolExecutor│  (11개 도구)
   │ Client  │  └─┬──────────┘
   └─────────┘    │
          │       │
          │   ┌───▼────────┐
          │   │ Security   │  (보안 검증)
          │   │ Validator  │
          └───┴────────────┘
```

---

## 🚀 빠른 시작

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. Ollama 실행

```bash
# Ollama 설치 후
ollama pull qwen2.5-coder:7b
ollama serve
```

### 3. 서버 실행

```bash
# 프로덕션
python -m src.main

# 또는 개발 모드
python src/main.py
```

서버가 `http://localhost:8000`에서 실행됩니다.

---

## 📡 API 사용법

### 1. 작업 생성

```bash
curl -X POST "http://localhost:8000/api/v1/agent/task" \
  -H "Content-Type: application/json" \
  -d '{
    "user_request": "src/test.py 파일에 타입 힌트를 추가해줘",
    "workspace_path": "/workspace"
  }'
```

**응답:**
```json
{
  "task_id": "abc-123-def",
  "status": "pending",
  "user_request": "src/test.py 파일에 타입 힌트를 추가해줘",
  "workspace_path": "/workspace",
  "iteration_count": 0
}
```

### 2. 작업 실행 (Server-Sent Events)

```bash
curl -N "http://localhost:8000/api/v1/agent/task/abc-123-def/execute"
```

**실시간 이벤트 스트림:**
```
data: {"type": "iteration_start", "iteration": 1}

data: {"type": "reasoning", "content": "파일을 먼저 읽겠습니다"}

data: {"type": "action_start", "tool": "read_file", "params": {"path": "src/test.py"}}

data: {"type": "action_success", "result": "def test(): pass"}

data: {"type": "action_start", "tool": "edit_file", ...}

data: {"type": "task_completed", "result": {"message": "타입 힌트 추가 완료"}}
```

### 3. 작업 상태 조회

```bash
curl "http://localhost:8000/api/v1/agent/task/abc-123-def"
```

### 4. WebSocket 실시간 실행

```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/agent/ws/abc-123-def');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`[${data.type}]`, data);

  if (data.type === 'task_completed') {
    console.log('작업 완료:', data.result);
    ws.close();
  }
};
```

---

## 🛠️ 사용 가능한 도구 (11개)

### 파일 도구
- **read_file**: 파일 읽기
- **edit_file**: 파일 수정 (문자열 치환)
- **create_file**: 새 파일 생성
- **delete_file**: 파일 삭제 (백업 포함)

### 검색 도구
- **list_files**: 파일 목록 조회 (패턴, 재귀 지원)
- **search_code**: 코드 검색 (regex 지원)

### 테스트 도구
- **run_tests**: pytest 실행
- **run_command**: 허용된 명령 실행

### 상호작용 도구
- **finish**: 작업 완료 표시
- **ask_user**: 사용자 질문 (WebSocket 필요)
- **report_error**: 에러 보고

---

## 🔒 보안 기능

### 경로 검증
```python
# ✅ 허용
"src/test.py"
"tests/test_agent.py"

# ❌ 차단
"../../../etc/passwd"  # 경로 탐색
".env"                 # 민감한 파일
".git/config"          # 시스템 파일
```

### 명령 검증
```python
# ✅ 허용
"pytest tests/"
"python -m black src/"

# ❌ 차단
"rm -rf /"             # 위험한 명령
"sudo apt install"     # 권한 상승
"cat /etc/passwd"      # 민감한 파일
```

---

## 📊 테스트 결과

```bash
pytest tests/agent/ -v --cov=src/agent
```

**결과:**
```
138 passed, 6 skipped in 4.87s

Name                               Coverage
------------------------------------------
src/agent/executor.py              97%
src/agent/task_manager.py          90%
src/agent/security/validator.py    90%
src/agent/orchestrator.py          88%
src/agent/interaction_tools.py     100%
src/agent/task_state.py            98%
------------------------------------------
TOTAL                              59%
```

---

## 🏗️ 프로젝트 구조

```
src/agent/
├── orchestrator.py          # 핵심 두뇌 (LLM ↔ Tools 반복)
├── executor.py              # 도구 실행 엔진
├── task_manager.py          # 작업 관리자
├── security/
│   └── validator.py         # 보안 검증
├── llm/
│   └── ollama_client.py     # Ollama 클라이언트
├── memory/
│   ├── conversation.py      # 대화 히스토리
│   └── task_state.py        # 작업 상태
└── tools/
    ├── base.py              # 도구 베이스 클래스
    ├── file_tools.py        # 파일 도구 (4개)
    ├── search_tools.py      # 검색 도구 (2개)
    ├── test_tools.py        # 테스트 도구 (2개)
    └── interaction_tools.py # 상호작용 도구 (3개)

src/routes/
└── agent.py                 # FastAPI 라우터

tests/agent/
├── test_orchestrator.py     # 오케스트레이터 테스트
├── test_task_manager.py     # 작업 관리자 테스트
├── test_api.py              # API 테스트
├── test_security.py         # 보안 테스트
├── test_file_tools.py       # 파일 도구 테스트
├── test_search_tools.py     # 검색 도구 테스트
├── test_test_tools.py       # 테스트 도구 테스트
├── test_interaction_tools.py# 상호작용 도구 테스트
└── test_llm.py              # LLM 통합 테스트
```

---

## 💡 사용 예시

### Python 클라이언트

```python
import requests
import json

# 1. 작업 생성
response = requests.post("http://localhost:8000/api/v1/agent/task", json={
    "user_request": "tests/test_example.py 파일에 주석을 추가해줘",
    "workspace_path": "/workspace"
})
task_id = response.json()["task_id"]

# 2. 작업 실행 (SSE 스트림)
with requests.post(
    f"http://localhost:8000/api/v1/agent/task/{task_id}/execute",
    stream=True
) as r:
    for line in r.iter_lines():
        if line.startswith(b'data: '):
            event = json.loads(line[6:])
            print(f"[{event['type']}]", event)

            if event['type'] == 'task_completed':
                print("✅ 작업 완료!")
                break

# 3. 최종 상태 확인
status = requests.get(f"http://localhost:8000/api/v1/agent/task/{task_id}").json()
print(f"Status: {status['status']}")
print(f"Result: {status['result']}")
```

### cURL 예시

```bash
# 작업 생성
TASK_ID=$(curl -s -X POST "http://localhost:8000/api/v1/agent/task" \
  -H "Content-Type: application/json" \
  -d '{"user_request":"테스트 추가","workspace_path":"/workspace"}' \
  | jq -r .task_id)

# 작업 실행
curl -N "http://localhost:8000/api/v1/agent/task/$TASK_ID/execute"

# 상태 확인
curl "http://localhost:8000/api/v1/agent/task/$TASK_ID" | jq
```

---

## 🎯 다음 단계 (선택사항)

### 1. 프로덕션 배포
- Docker Compose 설정
- Nginx 리버스 프록시
- Redis 캐싱 추가

### 2. 고급 기능
- 작업 우선순위 큐
- 병렬 작업 실행
- 작업 일시정지/재개
- 롤백 기능

### 3. UI/UX
- React 프론트엔드
- 실시간 진행 상황 대시보드
- 작업 히스토리 시각화

### 4. 모니터링
- Prometheus 메트릭 추가
- Grafana 대시보드
- 로그 집계 (ELK Stack)

---

## 📝 참고 문서

- [AGENT_SYSTEM_PROMPT_V2.md](./AGENT_SYSTEM_PROMPT_V2.md) - 에이전트 시스템 프롬프트
- [AGENT_IMPLEMENTATION_DESIGN.md](./AGENT_IMPLEMENTATION_DESIGN.md) - 구현 설계 문서
- [FastAPI 문서](https://fastapi.tiangolo.com/)
- [Ollama 문서](https://ollama.ai/)

---

## 🤝 기여

버그 리포트나 기능 제안은 Issue를 통해 제출해주세요!

---

## 📄 라이선스

MIT License

---

**구현 완료일**: 2026-02-11
**테스트 상태**: ✅ 138/138 passed
**코드 커버리지**: 59%
