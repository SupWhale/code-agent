"use strict";
/**
 * AI Coding Agent VS Code Extension
 *
 * Entry point
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const connection_1 = require("./connection");
const fileSync_1 = require("./fileSync");
const path = __importStar(require("path"));
let connection = null;
let fileSync = null;
let outputChannel = null;
let statusBarItem = null;
function activate(context) {
    console.log('AI Coding Agent extension activated');
    // Output channel 생성
    outputChannel = vscode.window.createOutputChannel('AI Coding Agent');
    context.subscriptions.push(outputChannel);
    // Status bar item 생성
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.text = '$(plug) AI Agent';
    statusBarItem.tooltip = 'Click to connect to AI Agent server';
    statusBarItem.command = 'aiAgent.connect';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);
    // Commands 등록
    context.subscriptions.push(vscode.commands.registerCommand('aiAgent.connect', connectCommand));
    context.subscriptions.push(vscode.commands.registerCommand('aiAgent.disconnect', disconnectCommand));
    context.subscriptions.push(vscode.commands.registerCommand('aiAgent.ask', askCommand));
    context.subscriptions.push(vscode.commands.registerCommand('aiAgent.askSelection', askSelectionCommand));
    context.subscriptions.push(vscode.commands.registerCommand('aiAgent.uploadFiles', uploadFilesCommand));
    // 자동 연결 확인
    const config = vscode.workspace.getConfiguration('aiAgent');
    const autoConnect = config.get('autoConnect', false);
    if (autoConnect) {
        connectCommand();
    }
}
function deactivate() {
    if (connection) {
        connection.disconnect();
    }
}
/**
 * 서버 연결 Command
 */
async function connectCommand() {
    try {
        if (connection && connection.isConnected()) {
            vscode.window.showInformationMessage('Already connected to AI Agent');
            return;
        }
        // 설정에서 서버 URL 가져오기
        const config = vscode.workspace.getConfiguration('aiAgent');
        const serverUrl = config.get('serverUrl', 'ws://localhost:8000');
        outputChannel.show();
        outputChannel.appendLine('Connecting to AI Agent server...');
        // 연결 생성
        connection = new connection_1.AgentConnection(serverUrl, outputChannel);
        fileSync = new fileSync_1.FileSync(connection, outputChannel);
        // 이벤트 핸들러 등록
        setupEventHandlers();
        // 연결
        await connection.connect();
        // Status bar 업데이트
        statusBarItem.text = '$(check) AI Agent';
        statusBarItem.tooltip = 'Connected to AI Agent server';
        statusBarItem.command = 'aiAgent.disconnect';
        // 자동 업로드
        const autoUpload = config.get('autoUpload', true);
        if (autoUpload) {
            const count = await fileSync.uploadWorkspace();
            outputChannel.appendLine(`Uploaded ${count} files`);
        }
    }
    catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        vscode.window.showErrorMessage(`Failed to connect: ${errorMessage}`);
        outputChannel.appendLine(`Connection error: ${errorMessage}`);
    }
}
/**
 * 연결 해제 Command
 */
function disconnectCommand() {
    if (connection) {
        connection.disconnect();
        connection = null;
        fileSync = null;
        // Status bar 업데이트
        statusBarItem.text = '$(plug) AI Agent';
        statusBarItem.tooltip = 'Click to connect to AI Agent server';
        statusBarItem.command = 'aiAgent.connect';
    }
}
/**
 * 코드 수정 요청 Command
 */
async function askCommand() {
    if (!connection || !connection.isConnected()) {
        vscode.window.showErrorMessage('Not connected to AI Agent. Connect first.');
        return;
    }
    // 사용자 입력 받기
    const userRequest = await vscode.window.showInputBox({
        prompt: 'AI Agent에게 요청할 작업을 입력하세요',
        placeHolder: '예: 이 파일에 타입 힌트를 추가해줘',
        ignoreFocusOut: true
    });
    if (!userRequest) {
        return;
    }
    try {
        // 현재 활성 파일 업로드
        if (vscode.window.activeTextEditor) {
            await fileSync.uploadActiveFile();
        }
        // 컨텍스트 정보
        const editor = vscode.window.activeTextEditor;
        const context = editor ? {
            active_file: path.basename(editor.document.fileName),
            language: editor.document.languageId
        } : {};
        // Agent 요청
        await connection.requestAgent(userRequest, context);
        vscode.window.showInformationMessage(`🤖 AI Agent 작업 시작...`);
    }
    catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        vscode.window.showErrorMessage(`Failed: ${errorMessage}`);
    }
}
/**
 * 선택 영역 수정 Command
 */
async function askSelectionCommand() {
    if (!connection || !connection.isConnected()) {
        vscode.window.showErrorMessage('Not connected to AI Agent. Connect first.');
        return;
    }
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.selection.isEmpty) {
        vscode.window.showErrorMessage('No text selected');
        return;
    }
    // 사용자 입력 받기
    const userRequest = await vscode.window.showInputBox({
        prompt: '선택한 코드에 대한 요청을 입력하세요',
        placeHolder: '예: 이 함수를 리팩토링해줘',
        ignoreFocusOut: true
    });
    if (!userRequest) {
        return;
    }
    try {
        // 선택 영역과 파일 업로드
        const { file, selection } = await fileSync.uploadSelection();
        // 컨텍스트 정보
        const context = {
            active_file: file,
            selection: selection,
            language: editor.document.languageId,
            selection_range: {
                start: editor.selection.start.line,
                end: editor.selection.end.line
            }
        };
        // Agent 요청
        await connection.requestAgent(userRequest, context);
        vscode.window.showInformationMessage(`🤖 선택 영역 수정 시작...`);
    }
    catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        vscode.window.showErrorMessage(`Failed: ${errorMessage}`);
    }
}
/**
 * 파일 업로드 Command
 */
async function uploadFilesCommand() {
    if (!connection || !connection.isConnected()) {
        vscode.window.showErrorMessage('Not connected to AI Agent. Connect first.');
        return;
    }
    try {
        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'Uploading files to AI Agent...',
            cancellable: false
        }, async (progress) => {
            const count = await fileSync.uploadWorkspace();
            progress.report({ message: `${count} files uploaded` });
        });
    }
    catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        vscode.window.showErrorMessage(`Failed to upload: ${errorMessage}`);
    }
}
/**
 * 이벤트 핸들러 설정
 */
function setupEventHandlers() {
    if (!connection)
        return;
    // 연결 성공
    connection.on('connected', (message) => {
        outputChannel.appendLine(`Connected: session=${message.session_id}`);
    });
    // Agent 이벤트
    connection.on('agent_event', (message) => {
        const event = message.event;
        outputChannel.appendLine(`[Agent] ${event.type}: ${JSON.stringify(event)}`);
        // 진행 상황 표시
        if (event.type === 'reasoning') {
            vscode.window.setStatusBarMessage(`🤖 ${event.content}`, 3000);
        }
        else if (event.type === 'action_start') {
            vscode.window.setStatusBarMessage(`⚡ ${event.tool}...`, 3000);
        }
    });
    // 파일 변경
    connection.on('file_changed', async (message) => {
        try {
            const filePath = message.path;
            const newContent = message.content;
            outputChannel.appendLine(`File changed: ${filePath}`);
            // 파일 업데이트 (diff 확인 후)
            const config = vscode.workspace.getConfiguration('aiAgent');
            const showDiff = config.get('showDiff', true);
            if (showDiff) {
                await showDiffAndApply(filePath, newContent);
            }
            else {
                await applyChanges(filePath, newContent);
            }
        }
        catch (error) {
            outputChannel.appendLine(`Failed to apply changes: ${error}`);
        }
    });
    // 작업 완료
    connection.on('task_completed', (message) => {
        const result = message.result;
        vscode.window.showInformationMessage(`✅ ${result.message || 'Task completed'}`);
        outputChannel.appendLine(`Task completed: ${JSON.stringify(result)}`);
    });
    // 작업 실패
    connection.on('task_failed', (message) => {
        vscode.window.showErrorMessage(`❌ Task failed: ${message.error}`);
        outputChannel.appendLine(`Task failed: ${message.error}`);
    });
    // 에러
    connection.on('error', (message) => {
        vscode.window.showErrorMessage(`Error: ${message.error}`);
        outputChannel.appendLine(`Error: ${message.error}`);
    });
    // Ping 자동 응답
    setInterval(() => {
        if (connection && connection.isConnected()) {
            connection.ping();
        }
    }, 30000); // 30초마다
}
/**
 * Diff 표시 후 변경사항 적용
 */
async function showDiffAndApply(filePath, newContent) {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) {
        return;
    }
    const fullPath = path.join(workspaceFolder.uri.fsPath, filePath);
    const uri = vscode.Uri.file(fullPath);
    // 원본 파일 열기
    const originalDoc = await vscode.workspace.openTextDocument(uri);
    const originalContent = originalDoc.getText();
    // 임시 파일 생성 (변경된 내용)
    const tempUri = uri.with({ scheme: 'untitled', path: uri.path + '.ai-modified' });
    // Diff 표시
    await vscode.commands.executeCommand('vscode.diff', uri, tempUri, `AI Agent 변경사항: ${path.basename(filePath)}`);
    // 임시 문서에 새 내용 쓰기
    const tempDoc = await vscode.workspace.openTextDocument(tempUri);
    const edit = new vscode.WorkspaceEdit();
    edit.insert(tempUri, new vscode.Position(0, 0), newContent);
    await vscode.workspace.applyEdit(edit);
    // 사용자 확인
    const choice = await vscode.window.showQuickPick(['적용', '취소'], { placeHolder: '변경사항을 적용하시겠습니까?' });
    if (choice === '적용') {
        await applyChanges(filePath, newContent);
    }
}
/**
 * 변경사항 적용
 */
async function applyChanges(filePath, newContent) {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) {
        return;
    }
    const fullPath = path.join(workspaceFolder.uri.fsPath, filePath);
    const uri = vscode.Uri.file(fullPath);
    // 파일 업데이트
    const edit = new vscode.WorkspaceEdit();
    const document = await vscode.workspace.openTextDocument(uri);
    const fullRange = new vscode.Range(document.positionAt(0), document.positionAt(document.getText().length));
    edit.replace(uri, fullRange, newContent);
    await vscode.workspace.applyEdit(edit);
    // 저장
    await document.save();
    vscode.window.showInformationMessage(`✅ ${path.basename(filePath)} 수정 완료!`);
}
//# sourceMappingURL=extension.js.map