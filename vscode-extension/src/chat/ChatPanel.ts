import * as vscode from 'vscode';
import { AgentConnection } from '../connection';

interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
    codeBlocks?: CodeBlock[];
}

interface CodeBlock {
    language: string;
    code: string;
    startLine?: number;
    endLine?: number;
}

export class ChatPanel {
    public static currentPanel: ChatPanel | undefined;
    private readonly _panel: vscode.WebviewPanel;
    private readonly _extensionUri: vscode.Uri;
    private _disposables: vscode.Disposable[] = [];
    private _messages: Message[] = [];
    private _connection: AgentConnection | undefined;
    private _workspacePath: string = '';

    private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri) {
        this._panel = panel;
        this._extensionUri = extensionUri;

        // Set initial HTML content
        this._update();

        // Listen for when the panel is disposed
        this._panel.onDidDispose(() => this.dispose(), null, this._disposables);

        // Handle messages from the webview
        this._panel.webview.onDidReceiveMessage(
            async (message) => {
                await this._handleWebviewMessage(message);
            },
            null,
            this._disposables
        );

        // Setup connection event handlers
        this._setupConnectionHandlers();
    }

    private _setupConnectionHandlers() {
        if (!this._connection) {
            return;
        }

        // Listen for AI responses
        this._connection.on('file_changed', (message) => {
            const aiMessage: Message = {
                id: this._generateId(),
                role: 'assistant',
                content: `파일이 변경되었습니다: ${message.path}\n\n\`\`\`${message.language || 'text'}\n${message.new_content}\n\`\`\``,
                timestamp: new Date(),
                codeBlocks: [{
                    language: message.language || 'text',
                    code: message.new_content
                }]
            };
            this._messages.push(aiMessage);

            this._panel.webview.postMessage({
                type: 'thinking',
                show: false
            });

            this._panel.webview.postMessage({
                type: 'aiMessage',
                message: aiMessage
            });
        });

        // Listen for task completion
        this._connection.on('task_completed', (message) => {
            const aiMessage: Message = {
                id: this._generateId(),
                role: 'assistant',
                content: `✅ 작업 완료!\n\n${message.result || '성공적으로 완료되었습니다.'}`,
                timestamp: new Date()
            };
            this._messages.push(aiMessage);

            this._panel.webview.postMessage({
                type: 'thinking',
                show: false
            });

            this._panel.webview.postMessage({
                type: 'aiMessage',
                message: aiMessage
            });
        });

        // Listen for errors
        this._connection.on('error', (message) => {
            this._panel.webview.postMessage({
                type: 'thinking',
                show: false
            });

            this._panel.webview.postMessage({
                type: 'error',
                message: message.error || '오류가 발생했습니다'
            });
        });

        // Listen for thinking/progress
        this._connection.on('agent_thinking', (message) => {
            // Show streaming response
            if (message.content) {
                this._panel.webview.postMessage({
                    type: 'aiThinking',
                    content: message.content
                });
            }
        });

        // Capture workspace path on connect (both new and existing sessions)
        this._connection.on('connected', (message) => {
            if (message.workspace_path) {
                this._workspacePath = message.workspace_path;
                this._panel.webview.postMessage({
                    type: 'workspaceInfo',
                    path: this._workspacePath
                });
            }
        });

        this._connection.on('session_created', (message) => {
            if (message.workspace_path) {
                this._workspacePath = message.workspace_path;
                this._panel.webview.postMessage({
                    type: 'workspaceInfo',
                    path: this._workspacePath
                });
            }
        });
    }

    public setConnection(connection: AgentConnection) {
        this._connection = connection;
        this._setupConnectionHandlers();
    }

    public static createOrShow(extensionUri: vscode.Uri, connection?: AgentConnection) {
        const column = vscode.ViewColumn.Two;

        // If we already have a panel, show it
        if (ChatPanel.currentPanel) {
            ChatPanel.currentPanel._panel.reveal(column);
            if (connection) {
                ChatPanel.currentPanel._connection = connection;
            }
            return;
        }

        // Otherwise, create a new panel
        const panel = vscode.window.createWebviewPanel(
            'aiAgentChat',
            '🤖 AI Agent Chat',
            column,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: [
                    vscode.Uri.joinPath(extensionUri, 'media'),
                    vscode.Uri.joinPath(extensionUri, 'out')
                ]
            }
        );

        ChatPanel.currentPanel = new ChatPanel(panel, extensionUri);
        ChatPanel.currentPanel._connection = connection;
    }

    private async _handleWebviewMessage(message: any) {
        switch (message.type) {
            case 'userMessage':
                await this._handleUserMessage(message.text, message.workingDir);
                break;

            case 'browseWorkspace':
                await this._handleBrowseWorkspace();
                break;

            case 'applyCode':
                await this._applyCode(message.code, message.language);
                break;

            case 'copyCode':
                await vscode.env.clipboard.writeText(message.code);
                vscode.window.showInformationMessage('코드가 클립보드에 복사되었습니다');
                break;

            case 'clearChat':
                this._messages = [];
                this._update();
                break;

            case 'requestContext':
                const context = await this._getCurrentContext();
                this._panel.webview.postMessage({
                    type: 'contextInfo',
                    context: context
                });
                break;
        }
    }

    private async _handleBrowseWorkspace() {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        const uris = await vscode.window.showOpenDialog({
            canSelectFiles: false,
            canSelectFolders: true,
            canSelectMany: false,
            defaultUri: workspaceFolder?.uri,
            openLabel: '이 폴더를 작업 디렉토리로 사용'
        });

        if (uris && uris.length > 0) {
            let selectedPath = uris[0].fsPath;
            if (workspaceFolder) {
                const wsPath = workspaceFolder.uri.fsPath;
                if (selectedPath.startsWith(wsPath)) {
                    selectedPath = selectedPath.slice(wsPath.length).replace(/^[/\\]/, '') || '.';
                }
            }
            // Normalize to forward slashes
            selectedPath = selectedPath.replace(/\\/g, '/');
            this._panel.webview.postMessage({
                type: 'workspaceBrowseResult',
                path: selectedPath
            });
        }
    }

    private async _handleUserMessage(text: string, workingDir?: string) {
        // Add user message
        const userMessage: Message = {
            id: this._generateId(),
            role: 'user',
            content: text,
            timestamp: new Date()
        };
        this._messages.push(userMessage);

        // Show message in webview
        this._panel.webview.postMessage({
            type: 'userMessage',
            message: userMessage
        });

        // Show thinking indicator
        this._panel.webview.postMessage({
            type: 'thinking',
            show: true
        });

        try {
            // Get current context
            const context = await this._getCurrentContext();
            const dirContext = (workingDir && workingDir !== '.')
                ? `\n\n**작업 디렉토리**: \`${workingDir}\` (파일 경로는 이 디렉토리 기준 상대 경로 사용)`
                : '';
            const fullPrompt = context
                ? `${context}${dirContext}\n\n${text}`
                : dirContext
                    ? `${dirContext.trim()}\n\n${text}`
                    : text;

            // Send to AI (mock response for now, will integrate with WebSocket later)
            const response = await this._getAIResponse(fullPrompt);

            // Add AI message
            const aiMessage: Message = {
                id: this._generateId(),
                role: 'assistant',
                content: response,
                timestamp: new Date(),
                codeBlocks: this._extractCodeBlocks(response)
            };
            this._messages.push(aiMessage);

            // Hide thinking indicator
            this._panel.webview.postMessage({
                type: 'thinking',
                show: false
            });

            // Show AI response
            this._panel.webview.postMessage({
                type: 'aiMessage',
                message: aiMessage
            });

        } catch (error: any) {
            // Hide thinking indicator
            this._panel.webview.postMessage({
                type: 'thinking',
                show: false
            });

            // Show error
            this._panel.webview.postMessage({
                type: 'error',
                message: error.message || '오류가 발생했습니다'
            });
        }
    }

    private async _getAIResponse(prompt: string): Promise<string> {
        if (this._connection) {
            // Use actual WebSocket connection
            await this._connection.requestAgent(prompt);
            // Response will come through event handlers
            return 'Processing...';
        }

        // Mock response when not connected
        return `⚠️ 서버에 연결되지 않았습니다.\n\n먼저 "AI Agent: 서버 연결" 명령을 실행하세요.\n\n---\n\nMock 응답: "${prompt}"\n\n\`\`\`python\ndef example():\n    """Example function"""\n    return "Hello, World!"\n\`\`\``;
    }

    private async _getCurrentContext(): Promise<string> {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            return '';
        }

        const document = editor.document;
        const fileName = document.fileName.split(/[\\/]/).pop() || '';
        const language = document.languageId;
        const selection = editor.selection;

        let context = `📄 **현재 파일**: \`${fileName}\` (${language})`;

        if (!selection.isEmpty) {
            const selectedText = document.getText(selection);
            const startLine = selection.start.line + 1;
            const endLine = selection.end.line + 1;

            context += `\n\n**선택된 코드** (줄 ${startLine}-${endLine}):\n\`\`\`${language}\n${selectedText}\n\`\`\``;
        }

        return context;
    }

    private _extractCodeBlocks(text: string): CodeBlock[] {
        const codeBlockRegex = /```(\w+)?\n([\s\S]+?)\n```/g;
        const blocks: CodeBlock[] = [];
        let match;

        while ((match = codeBlockRegex.exec(text)) !== null) {
            blocks.push({
                language: match[1] || 'text',
                code: match[2]
            });
        }

        return blocks;
    }

    private async _applyCode(code: string, language?: string) {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('활성화된 편집기가 없습니다');
            return;
        }

        const selection = editor.selection;
        const range = selection.isEmpty
            ? new vscode.Range(0, 0, editor.document.lineCount, 0)
            : selection;

        await editor.edit(editBuilder => {
            editBuilder.replace(range, code);
        });

        vscode.window.showInformationMessage('코드가 적용되었습니다');
    }

    private _generateId(): string {
        return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    }

    private _update() {
        const webview = this._panel.webview;
        this._panel.webview.html = this._getHtmlForWebview(webview);
    }

    private _getHtmlForWebview(webview: vscode.Webview): string {
        const scriptUri = webview.asWebviewUri(
            vscode.Uri.joinPath(this._extensionUri, 'media', 'js', 'chat.js')
        );
        const styleUri = webview.asWebviewUri(
            vscode.Uri.joinPath(this._extensionUri, 'media', 'css', 'chat.css')
        );

        const nonce = this._getNonce();

        return `<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline' https://cdnjs.cloudflare.com; script-src 'nonce-${nonce}' https://cdnjs.cloudflare.com; font-src ${webview.cspSource} https://cdnjs.cloudflare.com;">
    <link href="${styleUri}" rel="stylesheet">
    <!-- Prism.js for syntax highlighting -->
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-tomorrow.min.css" rel="stylesheet">
    <title>AI Agent Chat</title>
</head>
<body>
    <div id="chat-container">
        <div id="chat-header">
            <h2>🤖 AI Coding Agent</h2>
            <div id="header-actions">
                <button id="context-btn" class="icon-btn" title="현재 컨텍스트 보기">
                    <span class="codicon codicon-info"></span>
                </button>
                <button id="clear-btn" class="icon-btn" title="채팅 초기화">
                    <span class="codicon codicon-trash"></span>
                </button>
            </div>
        </div>
        <div id="workspace-bar">
            <span class="ws-label">📁 서버:</span>
            <span id="workspace-path" title="서버 워크스페이스 경로">연결 대기 중...</span>
            <span class="ws-sep">|</span>
            <span class="ws-label">📂 작업 경로:</span>
            <input id="working-dir-input" type="text" value="." placeholder="." title="AI가 파일을 생성/수정할 디렉토리 (예: src, src/api)">
            <button id="browse-dir-btn" class="ws-browse-btn" title="VS Code에서 폴더 선택">
                <span class="codicon codicon-folder-opened"></span>
            </button>
        </div>

        <div id="messages-container">
            <div id="messages"></div>
            <div id="thinking-indicator" style="display: none;">
                <div class="thinking-dots">
                    <span class="dot"></span>
                    <span class="dot"></span>
                    <span class="dot"></span>
                </div>
                <span class="thinking-text">AI가 생각 중...</span>
            </div>
        </div>

        <div id="input-container">
            <textarea
                id="user-input"
                placeholder="메시지를 입력하세요... (Enter: 전송, Shift+Enter: 줄바꿈)"
                rows="3"
            ></textarea>
            <button id="send-btn" title="전송 (Enter)">
                <span class="codicon codicon-send"></span>
            </button>
        </div>
    </div>

    <!-- Prism.js Core -->
    <script nonce="${nonce}" src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js"></script>
    <!-- Prism.js Language Support -->
    <script nonce="${nonce}" src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-python.min.js"></script>
    <script nonce="${nonce}" src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-javascript.min.js"></script>
    <script nonce="${nonce}" src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-typescript.min.js"></script>
    <script nonce="${nonce}" src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-java.min.js"></script>
    <script nonce="${nonce}" src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-cpp.min.js"></script>
    <script nonce="${nonce}" src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-csharp.min.js"></script>
    <script nonce="${nonce}" src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-json.min.js"></script>
    <script nonce="${nonce}" src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-yaml.min.js"></script>
    <script nonce="${nonce}" src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-bash.min.js"></script>
    <!-- Chat Script -->
    <script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
    }

    private _getNonce() {
        let text = '';
        const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
        for (let i = 0; i < 32; i++) {
            text += possible.charAt(Math.floor(Math.random() * possible.length));
        }
        return text;
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
