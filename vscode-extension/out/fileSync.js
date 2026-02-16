"use strict";
/**
 * File Synchronization
 *
 * VS Code workspace 파일을 서버와 동기화합니다.
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
exports.FileSync = void 0;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
// 차단된 파일 패턴
const BLOCKED_PATTERNS = [
    '.env',
    '.env.*',
    '*.key',
    '*.pem',
    '**/node_modules/**',
    '**/.git/**',
    '**/__pycache__/**',
    '**/.venv/**',
    '**/venv/**',
    '*.pyc',
    '*.pyo'
];
class FileSync {
    constructor(connection, outputChannel) {
        this.connection = connection;
        this.outputChannel = outputChannel;
    }
    /**
     * 현재 워크스페이스의 모든 파일 업로드
     */
    async uploadWorkspace() {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            throw new Error('No workspace folder open');
        }
        this.log('Collecting workspace files...');
        // 설정에서 최대 파일 크기 가져오기
        const config = vscode.workspace.getConfiguration('aiAgent');
        const maxFileSize = config.get('maxFileSize', 1048576);
        // 파일 찾기
        const files = await this.findWorkspaceFiles(workspaceFolder.uri, maxFileSize);
        if (files.length === 0) {
            this.log('No files to upload');
            return 0;
        }
        this.log(`Uploading ${files.length} files...`);
        // 파일 업로드
        await this.connection.uploadFiles(files);
        vscode.window.showInformationMessage(`✅ ${files.length}개 파일 업로드 완료`);
        return files.length;
    }
    /**
     * 현재 활성 파일 업로드
     */
    async uploadActiveFile() {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            throw new Error('No active editor');
        }
        const document = editor.document;
        const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
        if (!workspaceFolder) {
            throw new Error('File is not in workspace');
        }
        const relativePath = this.getRelativePath(workspaceFolder.uri, document.uri);
        const content = document.getText();
        await this.connection.uploadFiles([{
                path: relativePath,
                content: content
            }]);
        this.log(`Uploaded: ${relativePath}`);
        vscode.window.showInformationMessage(`✅ ${path.basename(relativePath)} 업로드 완료`);
    }
    /**
     * 선택 영역의 파일 업로드
     */
    async uploadSelection() {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            throw new Error('No active editor');
        }
        const document = editor.document;
        const selection = editor.selection;
        const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
        if (!workspaceFolder) {
            throw new Error('File is not in workspace');
        }
        const relativePath = this.getRelativePath(workspaceFolder.uri, document.uri);
        const fullContent = document.getText();
        const selectedText = document.getText(selection);
        // 전체 파일 업로드
        await this.connection.uploadFiles([{
                path: relativePath,
                content: fullContent
            }]);
        this.log(`Uploaded with selection: ${relativePath}`);
        return {
            file: relativePath,
            selection: selectedText
        };
    }
    /**
     * 워크스페이스 파일 찾기
     */
    async findWorkspaceFiles(workspaceUri, maxFileSize) {
        const files = [];
        // 파일 패턴 설정
        const includePattern = '**/*.{py,js,ts,jsx,tsx,json,md,txt,yaml,yml,toml,ini}';
        const excludePattern = `{${BLOCKED_PATTERNS.join(',')}}`;
        // 파일 검색
        const uris = await vscode.workspace.findFiles(includePattern, excludePattern, 100);
        for (const uri of uris) {
            try {
                // 파일 크기 확인
                const stat = await vscode.workspace.fs.stat(uri);
                if (stat.size > maxFileSize) {
                    this.log(`Skipped (too large): ${uri.fsPath}`);
                    continue;
                }
                // 차단된 패턴 확인
                if (this.isBlocked(uri.fsPath)) {
                    continue;
                }
                // 파일 읽기
                const document = await vscode.workspace.openTextDocument(uri);
                const relativePath = this.getRelativePath(workspaceUri, uri);
                files.push({
                    path: relativePath,
                    content: document.getText()
                });
            }
            catch (error) {
                this.log(`Failed to read ${uri.fsPath}: ${error}`);
            }
        }
        return files;
    }
    /**
     * 차단된 파일인지 확인
     */
    isBlocked(filePath) {
        const normalizedPath = filePath.replace(/\\/g, '/');
        for (const pattern of BLOCKED_PATTERNS) {
            const regexPattern = pattern
                .replace(/\./g, '\\.')
                .replace(/\*/g, '.*')
                .replace(/\?/g, '.');
            const regex = new RegExp(regexPattern);
            if (regex.test(normalizedPath)) {
                return true;
            }
        }
        return false;
    }
    /**
     * 상대 경로 계산
     */
    getRelativePath(baseUri, targetUri) {
        const relative = path.relative(baseUri.fsPath, targetUri.fsPath);
        return relative.replace(/\\/g, '/'); // Windows 경로를 Unix 스타일로 변환
    }
    /**
     * 로그 출력
     */
    log(message) {
        const timestamp = new Date().toLocaleTimeString();
        this.outputChannel.appendLine(`[${timestamp}] ${message}`);
    }
}
exports.FileSync = FileSync;
//# sourceMappingURL=fileSync.js.map