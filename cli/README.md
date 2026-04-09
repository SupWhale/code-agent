# code-agent CLI 사용 가이드

맥 터미널에서 AI 코딩 에이전트 서버에 연결해 코드 작업을 요청하고, 파일을 관리하는 CLI 도구입니다.

---

## 목차

1. [설치 및 실행](#1-설치-및-실행)
2. [빠른 시작](#2-빠른-시작)
3. [명령어 레퍼런스](#3-명령어-레퍼런스)
   - [status](#status)
   - [session](#session)
   - [files](#files)
   - [ask](#ask)
   - [chat](#chat)
   - [config](#config)
4. [chat 모드 슬래시 커맨드](#4-chat-모드-슬래시-커맨드)
5. [설정 파일](#5-설정-파일)
6. [자동 제외 규칙](#6-자동-제외-규칙-sync--local-ls)

---

## 1. 설치 및 실행

### 실행 파일 사용 (권장)

프로젝트 루트의 `agent` 파일을 직접 실행합니다. **최초 1회 자동으로 의존성을 설치**하며, 이후 실행부터는 바로 시작됩니다.

```bash
./agent --help
```

### 어디서든 실행하고 싶다면

```bash
# /usr/local/bin에 심링크 생성 (sudo 필요)
sudo ln -sf "$(pwd)/agent" /usr/local/bin/agent

# 이후 어느 경로에서도 사용 가능
agent --help
```

### 요구 사항

- Python 3.9 이상
- 에이전트 서버 실행 중 (`http://192.168.0.149:8000` 기본값)

---

## 2. 빠른 시작

```bash
# 1. 서버 연결 확인
./agent status

# 2. 세션 생성
./agent session new

# 3. 작업할 프로젝트 파일을 서버에 동기화
./agent files sync ~/myproject

# 4. 에이전트에게 작업 요청
./agent ask "main.py의 버그를 찾아서 수정해줘"

# 5. 대화형 모드로 계속 작업
./agent chat
```

---

## 3. 명령어 레퍼런스

### status

서버 연결 상태, 사용 중인 모델, 현재 세션 정보를 출력합니다.

```bash
./agent status
```

출력 예시:
```
┌─────────────────────────────────┐
│         code-agent 상태         │
│  서버      http://192.168.0.149  │
│  서버 상태 OK                   │
│  모델      qwen2.5-coder:7b     │
│  세션      abc-1234             │
│  workspace /tmp/sessions/abc    │
│  파일 수   12                   │
└─────────────────────────────────┘
```

---

### session

세션은 서버 워크스페이스와 연결되는 작업 단위입니다. 세션마다 독립된 파일 공간이 할당됩니다.

#### session list

서버에 존재하는 전체 세션 목록을 표로 출력합니다. 현재 선택된 세션에는 `▶` 표시가 붙습니다.

```bash
./agent session list
```

#### session new

새 세션을 생성하고 현재 세션으로 설정합니다.

```bash
./agent session new              # ID 자동 생성
./agent session new my-project   # ID 직접 지정
```

#### session select

기존 세션으로 전환합니다. 인자를 생략하면 번호로 선택하는 대화형 모드로 진입합니다.

```bash
./agent session select           # 대화형 선택
./agent session select abc-1234  # ID 직접 지정
```

#### session info

현재 세션의 상세 정보(ID, workspace 경로, 파일 수, 생성일 등)를 출력합니다.

```bash
./agent session info
```

#### session delete

현재 세션과 서버의 워크스페이스 파일을 삭제합니다. 삭제 전 확인을 요청합니다.

```bash
./agent session delete
```

---

### files

서버 워크스페이스의 파일을 관리하고, 로컬 파일을 서버에 올립니다.

#### files ls

서버 워크스페이스의 파일 목록을 트리 형식으로 출력합니다.

```bash
./agent files ls           # 전체 목록
./agent files ls src/      # src/ 하위만 필터
```

#### files show

서버에 있는 파일의 내용을 신택스 하이라이팅과 함께 출력합니다.

```bash
./agent files show src/main.py
./agent files show config.json --no-lines   # 줄 번호 숨기기
```

#### files upload

로컬 파일 하나 또는 여러 개를 서버 워크스페이스에 업로드합니다.

```bash
./agent files upload src/main.py
./agent files upload src/main.py src/utils.py
./agent files upload src/main.py --base .   # 현재 경로 기준 상대 경로 유지
```

`--base` 옵션을 사용하면 경로 구조를 유지한 채 업로드합니다.

```bash
# --base 없음: main.py 로 업로드
./agent files upload src/main.py

# --base . : src/main.py 로 업로드 (경로 유지)
./agent files upload src/main.py --base .
```

#### files local-ls

로컬 디렉토리의 파일 구조를 트리로 출력합니다. 서버에 전송하지 않습니다.

```bash
./agent files local-ls                  # 현재 디렉토리
./agent files local-ls ~/myproject
./agent files local-ls . --depth 2      # 깊이 2단계까지만
```

`.gitignore` 패턴과 기본 제외 목록(`.git`, `node_modules` 등)이 자동 적용됩니다.

#### files sync

로컬 디렉토리 전체를 서버 워크스페이스에 동기화합니다. 전송 전 파일 목록을 미리 보여주고 확인을 요청합니다.

```bash
./agent files sync                       # 현재 디렉토리
./agent files sync ~/myproject
./agent files sync . --max-size 1000     # 최대 1MB 이하 파일만
./agent files sync . --dry-run           # 실제 전송 없이 대상 파일만 확인
```

자동 제외 항목은 [아래](#6-자동-제외-규칙-sync--local-ls)를 참고하세요.

---

### ask

에이전트에게 작업을 한 번에 요청하고 결과를 스트리밍으로 출력합니다.

```bash
./agent ask "main.py의 버그를 찾아서 수정해줘"
./agent ask "테스트 코드가 없는 함수에 pytest 테스트를 추가해줘"
./agent ask "코드를 분석하고 개선할 부분을 알려줘"
```

에이전트의 추론 과정, 사용하는 도구, 파일 변경 내역이 실시간으로 출력됩니다.

```
╭─ 요청 ────────────────────────────────╮
│ main.py의 버그를 찾아서 수정해줘       │
╰───────────────────────────────────────╯
▶ 작업 시작 — ID: abc-1234-...
◎ 추론: main.py를 먼저 읽어 문제를 파악합니다.
  → read_file(path='main.py')
  ✓ read_file 완료
  → edit_file(path='main.py', ...)
  ✓ edit_file 완료
  ↺ 파일 변경: main.py
╭─ 완료 ────────────────────────────────╮
│ 32번째 줄의 NullPointerException ...   │
╰───────────────────────────────────────╯
```

---

### chat

대화형 인터랙티브 모드입니다. 여러 요청을 연속으로 보낼 수 있으며, 슬래시 커맨드로 파일 관리도 가능합니다.

```bash
./agent chat
```

진입 후:
```
> main.py를 분석해줘
> 방금 수정한 파일 보여줘
> /files
> /show src/main.py
> exit
```

종료: `exit`, `quit`, `q`, 또는 `Ctrl+C`

---

### config

CLI 설정을 조회하거나 변경합니다. 설정은 `~/.config/code-agent/config.json`에 저장됩니다.

#### config show

현재 설정 전체를 출력합니다.

```bash
./agent config show
```

#### config set

설정 값을 변경합니다.

```bash
./agent config set server_url http://192.168.0.149:8000
./agent config set server_url http://localhost:8000      # 로컬로 전환
```

| 키 | 설명 | 기본값 |
|----|------|--------|
| `server_url` | 에이전트 서버 주소 | `http://192.168.0.149:8000` |
| `session_id` | 현재 세션 ID | (자동 저장) |
| `workspace_path` | 현재 세션 workspace 경로 | (자동 저장) |

---

## 4. chat 모드 슬래시 커맨드

`chat` 모드에서 `/`로 시작하는 커맨드를 사용할 수 있습니다.

| 커맨드 | 설명 |
|--------|------|
| `/files` | 서버 워크스페이스 파일 목록 (트리) |
| `/show <path>` | 서버 파일 내용 출력 |
| `/local ls [dir]` | 로컬 디렉토리 파일 구조 출력 |
| `/sync [dir]` | 로컬 디렉토리를 서버에 동기화 |
| `/status` | 서버 연결 상태 확인 |
| `/help` | 슬래시 커맨드 목록 |

예시:
```
> /local ls ~/myproject    ← 로컬 파일 트리 확인
> /sync ~/myproject        ← 서버에 동기화
> 방금 올린 파일 중 main.py 버그 수정해줘
> /show main.py            ← 수정된 파일 확인
```

---

## 5. 설정 파일

설정은 `~/.config/code-agent/config.json`에 JSON 형식으로 저장됩니다.

```json
{
  "server_url": "http://192.168.0.149:8000",
  "session_id": "abc-1234",
  "workspace_path": "/tmp/sessions/abc-1234"
}
```

직접 편집하거나 `./agent config set` 명령으로 변경할 수 있습니다.

---

## 6. 자동 제외 규칙 (sync / local-ls)

`files sync`와 `files local-ls` 실행 시 다음 항목은 자동으로 제외됩니다.

**기본 제외 디렉토리**

| 이름 | 설명 |
|------|------|
| `.git` | Git 저장소 메타데이터 |
| `.venv`, `venv` | Python 가상환경 |
| `__pycache__` | Python 캐시 |
| `node_modules` | Node.js 패키지 |
| `.pytest_cache`, `.mypy_cache` | 테스트/타입 캐시 |
| `dist`, `build`, `.next` | 빌드 결과물 |

**바이너리 파일 확장자**

`.png` `.jpg` `.gif` `.pdf` `.zip` `.tar` `.gz` `.exe` `.pyc` `.woff` `.mp4` 등

**크기 초과 파일**

기본 500KB 초과 파일 (`--max-size` 옵션으로 조정 가능)

**`.gitignore` 패턴**

대상 디렉토리의 `.gitignore` 파일이 있으면 해당 패턴도 자동 적용됩니다.
