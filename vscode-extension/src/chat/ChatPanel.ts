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
                await this._handleUserMessage(message.text);
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

    private async _handleUserMessage(text: string) {
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
            const fullPrompt = context ? `${context}\n\n${text}` : text;

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
        // TODO: Integrate with actual WebSocket connection
        // For now, return a mock response
        if (this._connection) {
            // Use actual connection when available
            // return await this._connection.requestAgent(prompt);
        }

        // Mock response for testing
        return `AI 응답: "${prompt}"에 대한 답변입니다.\n\n예시 코드:\n\`\`\`python\ndef example():\n    """Example function"""\n    return "Hello, World!"\n\`\`\``;
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
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">
    <link href="${styleUri}" rel="stylesheet">
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
