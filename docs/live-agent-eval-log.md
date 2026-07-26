# 라이브 에이전트 성능 로그

> `http://192.168.0.149:8000`의 `qwen2.5-coder:7b` 기반 에이전트에게 실제 코드 작업을
> 위임할 때마다, 날짜별로 결과를 여기에 追記한다. 목적은 시간이 지나며(모델 교체, 프롬프트
> 개선, 인프라 수정 등) 신뢰도가 실제로 나아지고 있는지 추세를 볼 수 있게 하는 것.
> 배경/상세 경위는 [live-agent-self-refactor-log.md](live-agent-self-refactor-log.md) 참고.

## 기록 방법

새 항목은 아래 표에 **맨 위에** 추가한다(최신이 위로 오도록). 항목 하나 = 위임 시도 1회
(task_id 1개). 여러 번 재시도했다면 재시도마다 별도 행으로 남긴다.

| 항목 | 의미 |
|---|---|
| 날짜 | `YYYY-MM-DD` |
| task_id | 서버에 보낸 task_id |
| 작업 유형 | read-only / 한 줄 치환 / 소규모 블록 편집(≤20줄) / 신규 파일 생성 / 대규모 편집(150줄+) 등 |
| 결과 | ✅ 성공(직접 검증 완료) / ❌ 실패 / ⚠️ 부분 성공 |
| `finish` 자체보고 | 실제 결과와 일치했는지 (일치 / **거짓 성공** / 정직한 실패) |
| 비고 | 실패 원인, 재시도 전략, 눈에 띄는 특이사항 |

---

## 2026-07-26

| task_id | 작업 유형 | 결과 | `finish` 자체보고 | 비고 |
|---|---|---|---|---|
| `fix-test-task-manager-file-v2` | 기존 파일 전체를 `edit_file`로 통째 교체 (~30줄, 테스트 파일) | ❌ 실패 | (3연속 LLM 파싱 실패로 태스크 자체가 죽어서 finish 도달 못함) | JSON 파싱 실패 3회, `max_failures` 도달. 결국 내가 직접 로컬 작성 |
| `fix-test-task-manager-file` | `delete_file`+`create_file` 조합, 테스트 파일 신규 작성 (~30줄) | ❌ 실패 | (동일, finish 도달 못함) | 2개 액션을 한 응답에 합쳐서 시도 → JSON 파싱 실패 3연속 |
| `delete-broken-testfile-only-v2` | `delete_file` 단일 호출, `confirm: true` 명시적으로 지시 | ❌ 실패 | **거짓 성공** | `confirm` 파라미터를 지시했음에도 계속 누락 → 툴 자체 에러, 그런데도 finish는 성공 보고 |
| `delete-broken-testfile-only` | `delete_file` 단일 호출 | ❌ 실패 | **거짓 성공** | 위와 동일 원인(confirm 누락) |
| `read-back-broken-testfile` | read-only, 파일 읽기 | ✅ 성공 | 일치 | 검증용 소규모 read_file 태스크는 항상 안정적 |
| `fix-sse-cancelled-error-bug-retry3` | `edit_file` 단일 호출, ~15줄 블록 치환 (old/new 문자열을 내가 직접 작성해 지정) | ✅ 성공 | ⚠️ 부분 (파일 수정은 맞았지만 `run_tests` 실패를 무시하고 finish) | **위임이 실제로 성공한 유일한 "코드 수정" 사례.** 로컬에서 바이트 단위로 대조 검증함 |
| `fix-sse-cancelled-error-bug-retry2` | 2개 파일(~200줄씩) 전체 내용을 프롬프트에 임베드해서 `delete_file`+`create_file` 지시 | ❌ 실패 | (3연속 LLM 파싱 실패, finish 도달 못함) | 프롬프트 자체가 너무 커서(두 파일 전체) 첫 iteration부터 JSON 파싱 실패 |
| `fix-sse-cancelled-error-bug` (1차 시도) | `edit_file`로 기존 블록 수정 + `create_file`로 새 테스트 파일 | ❌ 실패 (문법 에러 남김) | **거짓 성공** | 존재하지 않는 `TaskFailedEvent` 클래스를 환각, `task.id`(실제는 `task_id`) 오사용, 들여쓰기 깨짐. `run_tests`도 `[Errno 2] No such file or directory`로 실패했는데 무시하고 finish |
| `add-periodic-session-cleanup-fn-v2` | `edit_file` 단일 호출, ~7줄 블록(클래스 메서드, 들여쓰기 있음) 뒤에 신규 함수 추가 | ❌ 실패 | **거짓 성공** | old_string의 들여쓰기(4칸)를 빼먹고 f-string 여러 줄을 백슬래시 줄이음으로 바꿔써서 원본과 불일치. 그런데도 finish는 성공 |
| `add-periodic-session-cleanup-fn` | `edit_file` 2회(반복별로 분리 지시) — import 추가 + 함수 추가 | ⚠️ 부분 성공 | (2번째 edit은 3연속 실패로 태스크 중단, finish 도달 못함) | 1번째(import 한 줄 추가)는 성공, 2번째(함수 추가, old_string 있는데도 빈 문자열로 보냄)는 3연속 실패 |
| `verify-repo-state-2026-07-26b` | read-only, 파일 40줄 읽기 | ✅ 성공 | 일치 | main.py 리팩토링이 `/repo`에 반영 안 됐음을 확인하는 용도 |
| `read-back-broken-taskmanager` | read-only, 파일 읽기 | ✅ 성공 | 일치 | 검증용 |
| `verify-repo-mount` | read-only, list_files + read_file | ❌ 결과 불명 (좀비화) | (영구 running, 판단 불가) | 이번 세션 이전에 생성된 태스크. SSE 클라이언트(curl, 60초 타임아웃)가 끊기면서 [[sse_disconnect_stuck_task_bug]] 재현. `iteration_count: 0`인 채로 영구 고착, 이번 세션의 버그 2 수정으로도 이미 생성된 이 태스크 자체는 해소 안 됨 |

**이날의 요약:** 총 14회 위임/검증 시도 중, 실제 "코드 수정"을 목적으로 한 시도는 8회였고 그중 명확히 성공한 건 1회(`fix-sse-cancelled-error-bug-retry3`)뿐. read-only 검증 태스크(4회)는 전부 성공. `finish`의 자체 성공 보고와 실제 결과가 일치한 적은 read-only 태스크를 빼면 딱 1번(그마저도 `run_tests` 실패는 무시했으니 완전히 정직하진 않았음) — 나머지는 거짓 성공 아니면 태스크 자체가 죽어서 finish에 도달하지 못함. 상세 분석은 [live-agent-self-refactor-log.md](live-agent-self-refactor-log.md) 4장 참고.
