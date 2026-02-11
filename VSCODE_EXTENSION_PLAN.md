# VS Code Extension 구현 계획

AI Coding Agent를 VS Code에서 바로 사용할 수 있는 Extension 구현 계획입니다.

---

## 🎯 목표

**사용자가 VS Code에서:**
1. 파일을 선택하고 "AI Agent로 수정" 명령 실행
2. 서버의 AI Agent가 실시간으로 코드 분석 및 수정
3. 수정 내용을 VS Code에서 바로 확인 및 적용

---

## 🏗️ 아키텍처

```
┌─────────────────────────────────────────┐
│     VS Code (클라이언트 PC)              │
│  ┌──────────────────────────────────┐   │
│  │  VS Code Extension               │   │
│  │  ┌──────────┐   ┌─────────────┐ │   │
│  │  │ UI Panel │   │ File Watcher│ │   │
│  │  └────┬─────┘   └──────┬──────┘ │   │
│  │       │                 │        │   │
│  │  ┌────▼─────────────────▼──────┐ │   │
│  │  │   WebSocket Client         │ │   │
│  │  └────────────┬─────────────────┘ │   │
│  └───────────────┼───────────────────┘   │
└──────────────────┼───────────────────────┘
                   │ WebSocket (실시간 통신)
                   │
┌──────────────────▼───────────────────────┐
│     서버 (Docker Container)              │
│  ┌──────────────────────────────────┐   │
│  │  FastAPI Backend                 │   │
│  │  ┌─────────────────────────────┐ │   │
│  │  │ WebSocket Handler           │ │   │
│  │  │  - 파일 수신/전송            │ │   │
│  │  │  - 실시간 이벤트 스트리밍    │ │   │
│  │  └─────────┬───────────────────┘ │   │
│  │            │                     │   │
│  │  ┌─────────▼───────────────────┐ │   │
│  │  │ Session Manager             │ │   │
│  │  │  - 클라이언트별 workspace    │ │   │
│  │  │  - 파일 동기화               │ │   │
│  │  └─────────┬───────────────────┘ │   │
│  │            │                     │   │
│  │  ┌─────────▼───────────────────┐ │   │
│  │  │ Agent Orchestrator          │ │   │
│  │  │  (기존 시스템)               │ │   │
│  │  └─────────────────────────────┘ │   │
│  └──────────────────────────────────┘   │
└──────────────────────────────────────────┘
```

---

## 📋 Phase 1: 서버 확장 (Week 1)

### 1.1 Session Manager 구현

**파일**: `src/agent/session_manager.py`

```python
class ClientSession:
    """클라이언트 세션 관리"""
    session_id: str
    workspace_path: Path  # 임시 workspace
    files: Dict[str, str]  # 파일명 -> 내용
    last_activity: datetime

class SessionManager:
    """여러 클라이언트 세션 관리"""
    def create_session(client_id: str) -> ClientSession
    def get_session(session_id: str) -> ClientSession
    def update_file(session_id: str, file_path: str, content: str)
    def get_file(session_id: str, file_path: str) -> str
    def cleanup_expired_sessions()  # 30분 후 자동 삭제
```

**기능:**
- 각 클라이언트마다 격리된 임시 workspace 생성
- 파일 버전 관리 (변경 전/후 비교)
- 세션 타임아웃 (30분 비활동 시 삭제)

### 1.2 WebSocket API 확장

**파일**: `src/routes/vscode.py`

**새 엔드포인트:**
```python
@router.websocket("/ws/vscode/{session_id}")
async def vscode_websocket(websocket: WebSocket, session_id: str):
    """VS Code Extension용 WebSocket"""

    # 메시지 타입:
    # 1. file_upload: 클라이언트 → 서버
    # 2. file_download: 서버 → 클라이언트
    # 3. agent_request: 작업 요청
    # 4. agent_event: 실시간 이벤트
    # 5. diff: 변경 사항 (unified diff format)
```

**프로토콜 메시지:**
```json
// 1. 파일 업로드
{
  "type": "file_upload",
  "files": [
    {"path": "src/main.py", "content": "..."},
    {"path": "tests/test.py", "content": "..."}
  ]
}

// 2. Agent 요청
{
  "type": "agent_request",
  "user_request": "src/main.py에 타입 힌트 추가",
  "context": {
    "active_file": "src/main.py",
    "selection": {"start": 10, "end": 20}
  }
}

// 3. Agent 이벤트 (서버 → 클라이언트)
{
  "type": "agent_event",
  "event": {
    "type": "action_start",
    "tool": "edit_file",
    "params": {"path": "src/main.py"}
  }
}

// 4. 변경 사항 (서버 → 클라이언트)
{
  "type": "file_changed",
  "path": "src/main.py",
  "diff": "--- a/src/main.py\n+++ b/src/main.py\n...",
  "content": "..."  // 전체 내용
}

// 5. 완료
{
  "type": "task_completed",
  "result": {
    "files_modified": ["src/main.py"],
    "message": "타입 힌트 추가 완료"
  }
}
```

### 1.3 파일 동기화 도구

**새 도구**: `src/agent/tools/sync_tools.py`

```python
class SyncFileTool(BaseTool):
    """세션 파일 읽기/쓰기"""

    async def execute(self, params):
        # session_id를 통해 클라이언트별 파일 접근
        session = session_manager.get_session(params["session_id"])
        file_content = session.get_file(params["path"])
        return file_content

class DiffTool(BaseTool):
    """변경 사항을 unified diff로 생성"""

    async def execute(self, params):
        old_content = params["old_content"]
        new_content = params["new_content"]
        diff = unified_diff(old_content, new_content)
        return diff
```

---

## 📋 Phase 2: VS Code Extension 개발 (Week 2-3)

### 2.1 프로젝트 구조

```
vscode-extension/
├── package.json          # Extension 메타데이터
├── src/
│   ├── extension.ts      # Entry point
│   ├── connection.ts     # WebSocket 연결
│   ├── fileSync.ts       # 파일 동기화
│   ├── ui/
│   │   ├── panel.ts      # Side panel UI
│   │   ├── statusBar.ts  # 상태 표시
│   │   └── diffView.ts   # Diff 뷰어
│   └── commands/
│       ├── askAgent.ts   # "Ask AI Agent"
│       ├── applyChanges.ts
│       └── settings.ts
├── webview/              # UI (React)
│   ├── index.html
│   ├── app.tsx
│   └── components/
└── resources/
    └── icons/
```

### 2.2 핵심 기능

#### 2.2.1 연결 관리

**파일**: `src/connection.ts`

```typescript
export class AgentConnection {
  private ws: WebSocket;
  private sessionId: string;

  async connect(serverUrl: string): Promise<void> {
    // WebSocket 연결
    this.sessionId = uuid();
    this.ws = new WebSocket(`${serverUrl}/ws/vscode/${this.sessionId}`);

    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      this.handleMessage(message);
    };
  }

  async uploadFiles(files: FileInfo[]): Promise<void> {
    // 현재 workspace의 파일들을 서버로 전송
    this.ws.send(JSON.stringify({
      type: "file_upload",
      files: files
    }));
  }

  async requestAgent(userRequest: string, context: any): Promise<void> {
    this.ws.send(JSON.stringify({
      type: "agent_request",
      user_request: userRequest,
      context: context
    }));
  }

  private handleMessage(message: any): void {
    switch (message.type) {
      case "agent_event":
        this.onAgentEvent(message.event);
        break;
      case "file_changed":
        this.onFileChanged(message);
        break;
      case "task_completed":
        this.onTaskCompleted(message.result);
        break;
    }
  }
}
```

#### 2.2.2 UI Panel

**파일**: `src/ui/panel.ts`

```typescript
export class AgentPanel {
  private panel: vscode.WebviewPanel;

  constructor(private connection: AgentConnection) {
    // Side panel 생성
    this.panel = vscode.window.createWebviewPanel(
      'aiAgentPanel',
      'AI Coding Agent',
      vscode.ViewColumn.Two,
      { enableScripts: true }
    );

    // React UI 로드
    this.panel.webview.html = this.getWebviewContent();
  }

  // 사용자 입력 받기
  async askAgent(): Promise<void> {
    const userRequest = await vscode.window.showInputBox({
      prompt: "AI Agent에게 요청할 작업을 입력하세요",
      placeHolder: "예: 이 함수에 타입 힌트를 추가해줘"
    });

    if (userRequest) {
      // 현재 활성 파일과 선택 영역 전달
      const editor = vscode.window.activeTextEditor;
      const context = {
        active_file: editor?.document.fileName,
        selection: editor?.selection
      };

      await this.connection.requestAgent(userRequest, context);
    }
  }

  // 실시간 이벤트 표시
  showEvent(event: AgentEvent): void {
    this.panel.webview.postMessage({
      command: 'agent-event',
      event: event
    });
  }
}
```

#### 2.2.3 변경 사항 적용

**파일**: `src/commands/applyChanges.ts`

```typescript
export async function applyChanges(
  filePath: string,
  newContent: string,
  diff: string
): Promise<void> {

  // 1. Diff 뷰어로 변경 사항 표시
  const userApproved = await showDiffView(filePath, diff);

  if (userApproved) {
    // 2. 파일 업데이트
    const uri = vscode.Uri.file(filePath);
    const edit = new vscode.WorkspaceEdit();

    const document = await vscode.workspace.openTextDocument(uri);
    const fullRange = new vscode.Range(
      document.positionAt(0),
      document.positionAt(document.getText().length)
    );

    edit.replace(uri, fullRange, newContent);
    await vscode.workspace.applyEdit(edit);

    vscode.window.showInformationMessage(
      `✅ ${path.basename(filePath)} 수정 완료!`
    );
  }
}

async function showDiffView(filePath: string, diff: string): Promise<boolean> {
  // VS Code의 diff viewer 사용
  const originalUri = vscode.Uri.file(filePath);
  const modifiedUri = vscode.Uri.file(filePath + '.ai-modified');

  // Diff 표시
  await vscode.commands.executeCommand(
    'vscode.diff',
    originalUri,
    modifiedUri,
    `AI Agent 변경사항: ${path.basename(filePath)}`
  );

  // 사용자 승인 요청
  const choice = await vscode.window.showQuickPick(
    ['적용', '취소'],
    { placeHolder: '변경사항을 적용하시겠습니까?' }
  );

  return choice === '적용';
}
```

### 2.3 Commands 등록

**파일**: `package.json`

```json
{
  "contributes": {
    "commands": [
      {
        "command": "aiAgent.connect",
        "title": "AI Agent: 서버 연결"
      },
      {
        "command": "aiAgent.ask",
        "title": "AI Agent: 코드 수정 요청"
      },
      {
        "command": "aiAgent.askSelection",
        "title": "AI Agent: 선택 영역 수정"
      },
      {
        "command": "aiAgent.explain",
        "title": "AI Agent: 코드 설명"
      }
    ],
    "menus": {
      "editor/context": [
        {
          "command": "aiAgent.askSelection",
          "when": "editorHasSelection",
          "group": "aiAgent"
        }
      ]
    },
    "configuration": {
      "title": "AI Coding Agent",
      "properties": {
        "aiAgent.serverUrl": {
          "type": "string",
          "default": "ws://localhost:8000",
          "description": "AI Agent 서버 URL"
        },
        "aiAgent.autoApply": {
          "type": "boolean",
          "default": false,
          "description": "변경사항 자동 적용 (확인 없이)"
        }
      }
    }
  }
}
```

---

## 📋 Phase 3: 통합 및 테스트 (Week 4)

### 3.1 통합 시나리오

**시나리오 1: 단일 파일 수정**
```
1. VS Code에서 파일 열기 (main.py)
2. Cmd+Shift+P → "AI Agent: 코드 수정 요청"
3. 입력: "타입 힌트 추가해줘"
4. Agent가 분석 및 수정
5. Diff 뷰어로 변경사항 확인
6. "적용" 클릭 → 파일 업데이트
```

**시나리오 2: 선택 영역 수정**
```
1. 코드 일부 선택 (함수 하나)
2. 우클릭 → "AI Agent: 선택 영역 수정"
3. 입력: "이 함수 리팩토링해줘"
4. Agent가 해당 함수만 수정
5. 변경사항 적용
```

**시나리오 3: 프로젝트 전체 분석**
```
1. "AI Agent: 서버 연결"
2. 전체 프로젝트 파일 업로드
3. 입력: "프로젝트의 모든 함수에 docstring 추가"
4. Agent가 여러 파일 순차적으로 수정
5. 각 파일별로 diff 확인 및 적용
```

### 3.2 보안 고려사항

**클라이언트 보안:**
```typescript
// 민감한 파일 필터링
const BLOCKED_FILES = [
  '.env', '.env.*',
  '*.key', '*.pem',
  'credentials.*',
  'secrets.*'
];

function shouldUploadFile(filePath: string): boolean {
  return !BLOCKED_FILES.some(pattern =>
    minimatch(filePath, pattern)
  );
}
```

**서버 보안:**
```python
# 세션 격리
# - 각 클라이언트마다 독립된 workspace
# - 다른 세션의 파일 접근 불가

# 파일 크기 제한
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB
MAX_TOTAL_SIZE = 10 * 1024 * 1024  # 10MB per session

# Rate limiting
# - 클라이언트당 분당 10 요청 제한
```

### 3.3 에러 처리

**연결 끊김:**
```typescript
// 자동 재연결
private reconnect(): void {
  this.reconnectAttempts++;
  if (this.reconnectAttempts < MAX_RETRIES) {
    setTimeout(() => this.connect(), RETRY_DELAY);
  }
}
```

**타임아웃:**
```typescript
// 30초 타임아웃
const timeout = setTimeout(() => {
  this.ws.close();
  vscode.window.showErrorMessage(
    'AI Agent 응답 시간 초과'
  );
}, 30000);
```

---

## 📊 구현 일정

| Week | Task | Deliverable |
|------|------|-------------|
| 1 | 서버 확장 | SessionManager, WebSocket API |
| 2 | Extension 기본 구조 | 연결, 파일 동기화 |
| 3 | UI 및 Commands | Panel, Diff viewer |
| 4 | 통합 테스트 | E2E 테스트, 문서 |

---

## 🎯 최종 사용자 경험

**설치:**
```bash
# VS Code Marketplace에서 설치
# 또는
code --install-extension ai-coding-agent.vsix
```

**사용:**
```
1. Settings에서 서버 URL 설정
2. Cmd+Shift+P → "AI Agent: 서버 연결"
3. 코드 선택 후 우클릭 → "AI Agent: 선택 영역 수정"
4. 요청 입력: "리팩토링해줘"
5. Diff 확인 후 적용
```

**실시간 피드백:**
```
[Status Bar]  🤖 AI Agent 작동 중... (2/5 파일)

[Side Panel]
📝 진행 상황
  ✅ main.py 분석 완료
  ⏳ utils.py 수정 중...
  ⏸️  test.py 대기 중
```

---

## 💡 향후 개선 사항

### Phase 2 기능
- **Chat UI**: 대화형 인터페이스
- **History**: 이전 수정 내역 확인
- **Undo**: AI 수정 되돌리기
- **Snippets**: 자주 쓰는 요청 저장

### Phase 3 기능
- **Team Sharing**: 팀원과 Agent 공유
- **Custom Tools**: 사용자 정의 도구 추가
- **Ollama 로컬 실행**: 서버 없이 로컬 사용

---

## 📦 기술 스택

**서버:**
- Python 3.11+
- FastAPI
- WebSocket
- Ollama

**Extension:**
- TypeScript
- VS Code Extension API
- React (WebView UI)
- WebSocket Client

---

## 🚀 시작하기

다음 단계로 진행할 준비가 되셨나요?

1. **Phase 1 시작**: 서버 SessionManager 구현
2. **Extension 템플릿**: VS Code Extension 프로젝트 생성
3. **프로토타입**: 기본 연결 및 파일 동기화

어떤 것부터 시작할까요?
