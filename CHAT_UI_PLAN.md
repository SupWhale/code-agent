# Chat UI 구현 계획

## 개요

VS Code Extension에 시각적 채팅 인터페이스를 추가하여 사용자 경험을 개선합니다.

## 구현 방식: Webview Panel

### 선택 이유
- **완전한 커스터마이징**: HTML/CSS/JS로 자유로운 디자인
- **풍부한 UI**: 코드 블록, 버튼, 이미지 등 다양한 요소
- **VS Code API 통합**: 파일 편집, Diff 뷰어 등과 연동
- **크로스 플랫폼**: Windows, Mac, Linux 모두 지원

## 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    VS Code Window                        │
├──────────────┬──────────────────────────────────────────┤
│              │                                          │
│  Activity    │  Editor Area                            │
│  Bar         │  ┌────────────────────────────────┐    │
│  ┌──┐        │  │  main.py                      │    │
│  │📁│        │  │  def hello():                 │    │
│  │🔍│        │  │      print("Hello")           │    │
│  │🤖│ ◄─────┐│  └────────────────────────────────┘    │
│  └──┘       ││                                         │
│             ││  ┌────────────────────────────────┐    │
│             ││  │  AI Chat Panel (Webview)      │    │
│             ││  │  ┌──────────────────────────┐ │    │
│             ││  │  │ 👤 함수에 docstring 추가 │ │    │
│             ││  │  │                          │ │    │
│             ││  │  │ 🤖 네, 추가하겠습니다   │ │    │
│             ││  │  │ ```python                │ │    │
│             ││  │  │ def hello():             │ │    │
│             ││  │  │     """Say hello"""      │ │    │
│             ││  │  │ ```                      │ │    │
│             ││  │  │ [Apply] [Reject]         │ │    │
│             ││  │  └──────────────────────────┘ │    │
│             ││  │  [Type message...      ] [>] │    │
│             ││  └────────────────────────────────┘    │
│             │└──────────────────────────────────────────┤
│             │                                          │
└──────────────┴──────────────────────────────────────────┘
```

## Phase 1: 기본 채팅 UI (1-2일)

### 1.1 Webview Panel 생성

**파일**: `src/chat/ChatPanel.ts`

```typescript
import * as vscode from 'vscode';

export class ChatPanel {
    public static currentPanel: ChatPanel | undefined;
    private readonly _panel: vscode.WebviewPanel;
    private _disposables: vscode.Disposable[] = [];

    private constructor(panel: vscode.WebviewPanel) {
        this._panel = panel;
        this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
        this._update();
    }

    public static createOrShow(extensionUri: vscode.Uri) {
        const column = vscode.ViewColumn.Two;

        if (ChatPanel.currentPanel) {
            ChatPanel.currentPanel._panel.reveal(column);
            return;
        }

        const panel = vscode.window.createWebviewPanel(
            'aiAgentChat',
            'AI Agent Chat',
            column,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: [
                    vscode.Uri.joinPath(extensionUri, 'media')
                ]
            }
        );

        ChatPanel.currentPanel = new ChatPanel(panel);
    }

    private _update() {
        const webview = this._panel.webview;
        this._panel.title = 'AI Agent Chat';
        this._panel.webview.html = this._getHtmlForWebview(webview);
    }

    private _getHtmlForWebview(webview: vscode.Webview): string {
        return `<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Agent Chat</title>
    <style>
        ${this._getCss()}
    </style>
</head>
<body>
    <div id="chat-container">
        <div id="messages"></div>
        <div id="input-container">
            <textarea id="user-input" placeholder="메시지를 입력하세요..."></textarea>
            <button id="send-btn">전송</button>
        </div>
    </div>
    <script>
        ${this._getJavaScript()}
    </script>
</body>
</html>`;
    }

    private _getCss(): string {
        return `
            body {
                padding: 0;
                margin: 0;
                font-family: var(--vscode-font-family);
                color: var(--vscode-foreground);
                background-color: var(--vscode-editor-background);
            }
            #chat-container {
                display: flex;
                flex-direction: column;
                height: 100vh;
            }
            #messages {
                flex: 1;
                overflow-y: auto;
                padding: 16px;
            }
            .message {
                margin-bottom: 16px;
                padding: 12px;
                border-radius: 8px;
            }
            .user-message {
                background-color: var(--vscode-input-background);
                margin-left: 20%;
            }
            .ai-message {
                background-color: var(--vscode-editor-inactiveSelectionBackground);
                margin-right: 20%;
            }
            .message-header {
                font-weight: bold;
                margin-bottom: 8px;
            }
            .message-content {
                line-height: 1.5;
            }
            #input-container {
                display: flex;
                padding: 16px;
                border-top: 1px solid var(--vscode-panel-border);
            }
            #user-input {
                flex: 1;
                padding: 8px;
                border: 1px solid var(--vscode-input-border);
                background-color: var(--vscode-input-background);
                color: var(--vscode-input-foreground);
                font-family: var(--vscode-font-family);
                resize: none;
            }
            #send-btn {
                margin-left: 8px;
                padding: 8px 16px;
                background-color: var(--vscode-button-background);
                color: var(--vscode-button-foreground);
                border: none;
                cursor: pointer;
            }
            #send-btn:hover {
                background-color: var(--vscode-button-hoverBackground);
            }
            code {
                background-color: var(--vscode-textCodeBlock-background);
                padding: 2px 4px;
                border-radius: 3px;
            }
            pre {
                background-color: var(--vscode-textCodeBlock-background);
                padding: 12px;
                border-radius: 4px;
                overflow-x: auto;
            }
        `;
    }

    private _getJavaScript(): string {
        return `
            const vscode = acquireVsCodeApi();
            const messagesDiv = document.getElementById('messages');
            const userInput = document.getElementById('user-input');
            const sendBtn = document.getElementById('send-btn');

            // 메시지 전송
            function sendMessage() {
                const text = userInput.value.trim();
                if (!text) return;

                // 사용자 메시지 표시
                addMessage('user', text);
                userInput.value = '';

                // Extension에 메시지 전송
                vscode.postMessage({
                    type: 'userMessage',
                    text: text
                });
            }

            // 메시지 추가
            function addMessage(sender, content) {
                const messageDiv = document.createElement('div');
                messageDiv.className = \`message \${sender}-message\`;

                const header = document.createElement('div');
                header.className = 'message-header';
                header.textContent = sender === 'user' ? '👤 You' : '🤖 AI Agent';

                const contentDiv = document.createElement('div');
                contentDiv.className = 'message-content';
                contentDiv.innerHTML = formatContent(content);

                messageDiv.appendChild(header);
                messageDiv.appendChild(contentDiv);
                messagesDiv.appendChild(messageDiv);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }

            // 마크다운 간단 렌더링
            function formatContent(text) {
                // 코드 블록
                text = text.replace(/\`\`\`(\\w+)?\\n([\\s\\S]+?)\\n\`\`\`/g,
                    '<pre><code>$2</code></pre>');
                // 인라인 코드
                text = text.replace(/\`([^\`]+)\`/g, '<code>$1</code>');
                // 줄바꿈
                text = text.replace(/\\n/g, '<br>');
                return text;
            }

            // Extension으로부터 메시지 수신
            window.addEventListener('message', event => {
                const message = event.data;
                switch (message.type) {
                    case 'aiResponse':
                        addMessage('ai', message.text);
                        break;
                }
            });

            // 이벤트 리스너
            sendBtn.addEventListener('click', sendMessage);
            userInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
        `;
    }

    public dispose() {
        ChatPanel.currentPanel = undefined;
        this._panel.dispose();
        while (this._disposables.length) {
            const disposable = this._disposables.pop();
            if (disposable) {
                disposable.dispose();
            }
        }
    }
}
```

### 1.2 Extension에 통합

**파일**: `src/extension.ts` 수정

```typescript
import { ChatPanel } from './chat/ChatPanel';

export function activate(context: vscode.ExtensionContext) {
    // 기존 코드...

    // 채팅 패널 열기 명령어
    const showChatCommand = vscode.commands.registerCommand(
        'aiAgent.showChat',
        () => {
            ChatPanel.createOrShow(context.extensionUri);
        }
    );

    context.subscriptions.push(showChatCommand);
}
```

### 1.3 package.json 업데이트

```json
{
  "contributes": {
    "commands": [
      {
        "command": "aiAgent.showChat",
        "title": "AI Agent: 채팅 열기",
        "icon": "$(comment-discussion)"
      }
    ]
  }
}
```

## Phase 2: WebSocket 연동 (1일)

### 2.1 메시지 전송/수신

```typescript
// ChatPanel.ts
private setupMessageHandlers() {
    this._panel.webview.onDidReceiveMessage(
        async (message) => {
            switch (message.type) {
                case 'userMessage':
                    // AI에게 요청
                    await this.sendToAI(message.text);
                    break;
            }
        },
        null,
        this._disposables
    );
}

private async sendToAI(userMessage: string) {
    // WebSocket으로 AI에게 전송
    const response = await connection.requestAgent(userMessage);

    // AI 응답을 Webview에 전달
    this._panel.webview.postMessage({
        type: 'aiResponse',
        text: response
    });
}
```

### 2.2 스트리밍 응답

```typescript
// 실시간 스트리밍
connection.on('message', (data) => {
    if (data.type === 'agent_thinking') {
        this._panel.webview.postMessage({
            type: 'aiThinking',
            text: data.content
        });
    }
});
```

## Phase 3: 고급 기능 (2-3일)

### 3.1 코드 블록 처리

```javascript
// chatView.js
function formatCodeBlock(language, code) {
    return `
        <div class="code-block">
            <div class="code-header">
                <span>${language}</span>
                <button class="copy-btn" onclick="copyCode(this)">복사</button>
                <button class="apply-btn" onclick="applyCode(this)">적용</button>
            </div>
            <pre><code class="language-${language}">${escapeHtml(code)}</code></pre>
        </div>
    `;
}

function applyCode(btn) {
    const codeBlock = btn.closest('.code-block');
    const code = codeBlock.querySelector('code').textContent;

    vscode.postMessage({
        type: 'applyCode',
        code: code
    });
}
```

### 3.2 Diff 뷰어 통합

```typescript
// Extension에서 처리
case 'applyCode':
    const editor = vscode.window.activeTextEditor;
    if (editor) {
        const edit = new vscode.WorkspaceEdit();
        const fullRange = new vscode.Range(
            editor.document.positionAt(0),
            editor.document.positionAt(editor.document.getText().length)
        );
        edit.replace(editor.document.uri, fullRange, message.code);

        // Diff 표시
        await vscode.commands.executeCommand('vscode.diff',
            editor.document.uri,
            newUri,
            'Original ↔ AI Modified'
        );
    }
    break;
```

### 3.3 파일 컨텍스트

```typescript
// 현재 파일 정보를 채팅에 자동 추가
function getCurrentContext(): string {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return '';

    const fileName = path.basename(editor.document.fileName);
    const language = editor.document.languageId;
    const selection = editor.selection;

    let context = `📄 파일: ${fileName} (${language})`;

    if (!selection.isEmpty) {
        const selectedText = editor.document.getText(selection);
        context += `\n\n선택된 코드:\n\`\`\`${language}\n${selectedText}\n\`\`\``;
    }

    return context;
}
```

### 3.4 히스토리 관리

```typescript
interface ChatHistory {
    timestamp: Date;
    user: string;
    ai: string;
}

class ChatHistoryManager {
    private history: ChatHistory[] = [];

    add(user: string, ai: string) {
        this.history.push({
            timestamp: new Date(),
            user,
            ai
        });
        this.save();
    }

    save() {
        const storageUri = vscode.Uri.joinPath(
            context.globalStorageUri,
            'chat-history.json'
        );
        fs.writeFileSync(storageUri.fsPath, JSON.stringify(this.history));
    }

    load() {
        // 저장된 히스토리 불러오기
    }
}
```

## Phase 4: UI 개선 (1-2일)

### 4.1 Syntax Highlighting

```html
<!-- Prism.js 또는 Highlight.js 사용 -->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-tomorrow.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js"></script>
```

### 4.2 타이핑 애니메이션

```javascript
function typeWriter(element, text, speed = 30) {
    let i = 0;
    element.textContent = '';

    const timer = setInterval(() => {
        if (i < text.length) {
            element.textContent += text.charAt(i);
            i++;
        } else {
            clearInterval(timer);
        }
    }, speed);
}
```

### 4.3 로딩 인디케이터

```css
.thinking-indicator {
    display: flex;
    gap: 4px;
}

.thinking-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: var(--vscode-foreground);
    animation: bounce 1.4s infinite ease-in-out;
}

@keyframes bounce {
    0%, 80%, 100% { transform: scale(0); }
    40% { transform: scale(1); }
}
```

## 기술 스택

- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Communication**: VS Code Webview API, PostMessage
- **Styling**: VS Code CSS Variables (테마 자동 적용)
- **Syntax Highlighting**: Prism.js 또는 Highlight.js
- **Markdown**: Marked.js (옵션)

## 장점

1. **네이티브 통합**: VS Code 테마 자동 적용
2. **실시간 통신**: WebSocket을 통한 스트리밍 응답
3. **풍부한 UI**: 코드 블록, 버튼, Diff 등
4. **히스토리 관리**: 과거 대화 저장 및 검색
5. **컨텍스트 인식**: 현재 파일/선택 영역 자동 포함

## 다음 단계

1. Phase 1 구현 (기본 채팅 UI)
2. 테스트 및 피드백
3. Phase 2-4 순차 구현
4. 성능 최적화 및 버그 수정

---

**예상 소요 시간**: 5-7일
**우선순위**: High (UX 개선의 핵심 기능)
