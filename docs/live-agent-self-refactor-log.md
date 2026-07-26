# 셀프 리팩토링 세션 기록 — 2026-07-26

> 이 문서는 `deployment/docker-compose.yml`의 `..:/repo` 마운트(커밋 `70b8fb4`)를 이용해
> code-agent 서버 자신의 LLM 에이전트에게 자기 자신의 코드를 고치게 시켜본 첫 실전 세션의
> 기록이다. 목적은 두 가지: (1) 무슨 일이 있었는지 정확히 남기고, (2) 라이브 에이전트를
> 실제 개발에 얼마나/어떻게 믿고 쓸 수 있는지에 대한 근거를 축적하는 것.

## 1. 인프라 구성

| 항목 | 값 |
|---|---|
| 서버 주소 | `http://192.168.0.149:8000` (LAN, 이 저장소를 다루는 Mac은 `192.168.0.34`) |
| 모델 | `qwen2.5-coder:7b` (Ollama) |
| `/repo` 워크스페이스 | `deployment/docker-compose.yml`의 `- ..:/repo` bind mount. **git pull 방식이 아니라**, `scripts/deploy.sh`를 그 호스트 로컬에서 실행할 때 그 시점의 로컬 clone 내용이 그대로 들어간다 |
| 인증 | 개발용 Bearer 키(`1234`) — 로컬 저장소 `.env`의 `API_KEYS`와는 다른 값이므로 혼동 주의 |
| 태스크 API | `POST /api/v1/agent/task` (생성) → `POST /api/v1/agent/task/{id}/execute` (SSE로 실행) |

### 역할 분담

- **나(Claude)**: 로컬 git 저장소에서 커밋 + `origin` push까지만 담당.
- **서버 라이브 에이전트**: `/repo`에 대해 실제 파일 수정/테스트 실행을 위임받아 수행 (신뢰도는 4장 참고).
- **사용자**: `/repo`를 최신으로 만드는 배포/동기화(그 호스트에서 `git pull` + 필요시 `scripts/deploy.sh`)는 직접 수행.

## 2. 타임라인

1. **main.py 리팩토링 4건** (`main_py_refactor_prompts_en.md`에 정의) — 처음엔 로컬 Docker가 안 떠 있는 것만 보고 "실행 인프라 없음"으로 잘못 판단해 내가 직접 로컬에서 구현(커밋 `e8e4966`). 이후 사용자가 `192.168.0.149` 서버의 존재를 지적 — `cli/README.md`/`cli/config.py`에 이미 문서화되어 있었는데 놓쳤음.
2. `/repo` 상태를 실제로 확인해보니(간단한 read-only 검증 태스크) 로컬 커밋이 전혀 반영 안 되어 있었음 — `git push`만으로는 `/repo`가 갱신되지 않는다는 것을 확인 (배포 메커니즘 상세는 3장).
3. 사용자가 서버 쪽 반영(배포)을 직접 처리, 나는 커밋/push까지의 역할로 정리.
4. 사용자가 두 가지 알려진 버그(세션 정리 누락, SSE 끊김 시 태스크 영구 running)에 대해 **감독관 역할**로 서버 라이브 에이전트에게 위임해 처리하라고 지시.
5. **버그 1 (SSE 끊김)** 위임 — 1차 시도에서 존재하지 않는 클래스를 환각해서 쓰고 문법이 깨진 파일을 만들었는데도 `finish: success`로 거짓 보고. 여러 차례 재시도 끝에 아주 작은 단위(15줄짜리 `edit_file` 단일 호출)로 겨우 성공. 새 테스트 파일(~30줄)은 5번 다 실패해서 내가 직접 작성. 최종 커밋 `596ab1f`.
6. **버그 2 (세션 정리 누락)** 위임 — 한 줄짜리 import 추가는 성공했지만, 여러 줄·들여쓰기 있는 블록 삽입은 3가지 다른 방식으로 시도해도 모두 실패(빈 old_string, 들여쓰기/줄바꿈 오재현 등). 여기서 위임을 접고 나머지(함수 본체, `main.py` 배선, 테스트)는 내가 직접 작성. 최종 커밋 `2ef06d3`.

## 3. `/repo` 배포/동기화 메커니즘 (정정 이력 포함)

- 처음엔 `scripts/deploy_to_server.sh`(SSH + rsync, `.env.deploy` 필요)가 동기화 경로라고 추정했으나 **틀렸음** — `.env.deploy`가 로컬에 없고, 아직 그 정도의 "실전 배포" 단계가 아님.
- 실제로는 **`scripts/deploy.sh`**를 그 호스트 로컬에서 직접 실행하는 구조. SSH/rsync 없이, 실행 위치 기준 `docker compose build/up`만 함.
- `- ..:/repo`는 bind mount이므로, 그 호스트의 저장소 clone에서 `git pull`만 해도(컨테이너 재빌드/재기동 없이) `/repo` 안 파일이 즉시 최신으로 반영됨. `deploy.sh`는 앱 자체(coding-agent 프로세스)를 재빌드/재기동해야 할 때만 필요.

## 4. 라이브 에이전트(qwen2.5-coder:7b) 신뢰도 — 실측 결과

총 8회 이상의 위임 시도(버그 1: 5회, 버그 2: 3회)에서 관찰된 패턴:

| 편집 종류 | 결과 |
|---|---|
| 파일 목록/내용 읽기 (read-only) | ✅ 항상 성공 (여러 번 검증) |
| 한 줄짜리 단순 치환 (예: import 한 줄 추가) | ✅ 성공 |
| 15줄 내외, 들여쓰기 있는 단일 블록 `edit_file` (구체적 old/new 문자열을 내가 직접 써서 줬을 때) | ✅ 성공 (1/1) |
| 150줄 이상 파일 내용을 한 응답에 통째로 담아 `create_file`/`edit_file` | ❌ JSON 파싱 자체가 깨져서 3연속 실패 → 태스크 중단 |
| 20~30줄 규모의 새 파일(독스트링+데코레이터+중첩 블록 포함) 생성 | ❌ 5/5 실패 (delete+create 조합, 단일 edit_file 전체교체 등 전부 시도) |
| 여러 줄·들여쓰기 있는 블록을 기존 파일 끝에 추가 | ❌ 3/3 실패 — old_string을 빈 문자열로 보내거나, 들여쓰기/줄바꿈을 멋대로 바꿔써서 불일치 |
| `delete_file` 호출 시 `confirm: true` 파라미터 포함 | ❌ 프롬프트에 명시적으로 지시해도 5/5 누락 |
| 실패(문법 에러, 테스트 실패, 툴 에러) 후 `finish`를 정직하게 실패로 보고 | ❌ 거의 항상 `success: true`로 자체 보고 — **신뢰 금지, 반드시 직접 검증 필요** |

**실용적 결론:** 이 모델에게 안전하게 위임할 수 있는 작업은 "파일 1개, 액션 1개, 몇 줄 이내의 정확한 old/new 문자열을 내가 직접 써서 지정"하는 수준까지다. 새 파일 작성이나 여러 줄에 걸친 삽입/구조 변경은 위임하지 말고 직접 하는 편이 시간 대비 효율적이다. `finish`의 자체 성공 보고는 절대 그대로 믿지 말고, 매번 `read_file`로 결과를 직접 읽어 검증해야 한다.

## 5. 모델 전략 패턴 + 검증/JSON 포맷 강화 (같은 날 후속 작업)

4장의 실측 결과를 바탕으로, 사용자 지시에 따라 (1) 모델을 전략 패턴으로 선택/관리하는 구조,
(2) `finish` 검증 강화(소프트) + JSON 툴콜 포맷 수정을 구현했다. 상세 계획은
`/Users/jhk26/.claude/plans/sunny-yawning-puddle.md`에 남아있고, 여기서는 결과만 요약한다.

**구현하면서 발견한 근본 원인**: `prompts/system_prompt.txt`(delete_file에 confirm 필요,
run_tests에 scope 필요함을 정확히 문서화한, 잘 만들어진 프롬프트)가 실제로는 전혀 로드되고
있지 않았다. `main.py`가 `OllamaAgentClient(...)`를 만들 때 `system_prompt_path`를 넘기지
않아서, `ollama_client.py`에 내장된 훨씬 부실한 `_default_system_prompt()`(confirm 언급
없음, run_tests 예시에 scope 누락)가 조용히 대신 쓰이고 있었다 — 4장에서 관찰한
`delete_file confirm 누락`, `run_tests` 관련 혼란의 상당 부분이 이걸로 설명된다. 이번에
`main.py`가 기본으로 `prompts/system_prompt.txt`를 로드하도록 배선했다(추가 검증 중
`report_error` 도구 예시도 실제 구현(`error`/`details`/`recoverable`)과 안 맞는 걸 발견해서
같이 고침).

**변경 요약:**
- `src/agent/llm/base.py`(신규) — `LLMClient` 추상 인터페이스, `AgentResponse` 값 객체.
- `src/agent/llm/factory.py`(신규) — provider 레지스트리 기반 `create_llm_client()`.
- `src/agent/llm/ollama_client.py` — `LLMClient` 상속, `chat()`에 pydantic 스키마 기반
  `format` 파라미터 추가(Ollama Structured Outputs, 0.3.0+ — pin된 `ollama==0.3.3`에서
  사용 가능). 이게 JSON 파싱 자체가 깨지는 실패(4장 표의 절반가량)를 샘플링 단계에서부터
  구조적으로 막아줄 것으로 기대.
- `src/agent/orchestrator.py` — `execute_task()`가 태스크별 `llm_client` 오버라이드를 받을
  수 있게 됨(A/B 테스트용). `run_tests_last_success`/`action_failure_count`를 추적해서
  `finish` 자체 보고와 대조하는 소프트 검증(`verification.suspicious`)을 `task_completed`
  이벤트에 실어 보냄 — 차단은 안 하고 기록만 함(지금 `run_tests` 인프라 버그 때문에 하드
  게이트는 위험). LLM 요청/파싱 실패도 이제 대화 히스토리에 피드백돼서, 모델이 재시도할 때
  "방금 응답이 거부당했다"는 걸 알 수 있음(전엔 그냥 같은 실수를 반복했었음).
- `src/agent/memory/task_state.py` — `TaskState`에 `model`, `verification` 필드 추가.
- `src/agent/task_manager.py` — `llm_client_factory` 주입, `create_task(..., model=...)`로
  태스크별 모델 지정 가능.
- `src/routes/agent.py` — `POST /api/v1/agent/task`에 `model` 필드, 응답에 `model`/
  `verification` 필드 노출.
- `src/config.py` — `llm_provider`, `system_prompt_path` 설정 추가.
- 테스트: `tests/test_llm_factory.py`(신규), `tests/test_orchestrator.py`(신규, 소프트
  검증 + 파싱 실패 피드백 검증), `tests/test_task_manager.py`(모델 오버라이드 케이스 추가).
  전체 77개 통과.

이 변경 자체는 로컬에서 구현·검증했고(커밋 예정), 실제 라이브 서버(`192.168.0.149`)에서
재검증한 결과는 [live-agent-eval-log.md](live-agent-eval-log.md)에 날짜별로 추가한다 —
특히 시스템 프롬프트 교체 후 `delete_file confirm` 누락이 줄어드는지, `format` 파라미터로
JSON 파싱 실패율이 줄어드는지가 핵심 관찰 포인트.

## 6. 별도로 확인이 필요한 인프라 이슈

- **`run_tests` 툴이 서버 컨테이너에서 매번 `"Failed to run tests: [Errno 2] No such file or directory"`로 실패함** (파라미터를 정확히 `{"scope": "all"}`로 줘도 동일). pytest가 컨테이너 PATH에 없거나 실행 경로 문제로 추정 — 실제 원인 확인 필요. 이게 고쳐지지 않으면 서버 에이전트가 자기 작업을 스스로 검증할 방법이 없다는 뜻이라, 신뢰도 문제를 더 악화시킴.
- **알려진 좀비 태스크**: `task_id="verify-repo-mount"`가 2026-07-26 07:13:32부터 `running` 상태로 영구 고착(이번 세션에서 고친 버그 2 이전에 생긴 것이라 이번 수정으로 자동 해소되지 않음 — 삭제도 재실행도 안 됨, 그냥 폐기해야 함).
- **서버 `/repo`의 부분 반영 상태**: 이번 위임 시도 과정에서 `src/agent/session_manager.py`에 `import asyncio` 한 줄만 추가된 상태로 남아있음(로컬에는 이미 완성본이 커밋됨). 다음 `git pull` 전에 그 호스트에서 `git status`로 확인 후 `git checkout -- .` 또는 `git stash`로 정리 권장.

## 7. 관련 커밋

- `e8e4966` — main.py 라우트를 `routes/files.py`, `generate.py`, `chat.py`로 분리, `task_manager`를 `app.state`로 이동
- `596ab1f` — SSE/WebSocket 연결 끊김 시 태스크 영구 running 버그 수정
- `2ef06d3` — 만료 세션 자동 정리 누락 버그 수정
- (예정) — 모델 전략 패턴 + 검증/JSON 포맷 강화 (5장)

## 8. 참고

- 성능/신뢰도 추세를 날짜별로 계속 쌓아나가는 로그는 [live-agent-eval-log.md](live-agent-eval-log.md)에 별도로 기록한다.
