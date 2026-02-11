/**
 * File Synchronization
 *
 * VS Code workspace 파일을 서버와 동기화합니다.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import { AgentConnection, FileInfo } from './connection';

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

export class FileSync {
    constructor(
        private connection: AgentConnection,
        private outputChannel: vscode.OutputChannel
    ) {}

    /**
     * 현재 워크스페이스의 모든 파일 업로드
     */
    async uploadWorkspace(): Promise<number> {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            throw new Error('No workspace folder open');
        }

        this.log('Collecting workspace files...');

        // 설정에서 최대 파일 크기 가져오기
        const config = vscode.workspace.getConfiguration('aiAgent');
        const maxFileSize = config.get<number>('maxFileSize', 1048576);

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
    async uploadActiveFile(): Promise<void> {
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
    async uploadSelection(): Promise<{ file: string; selection: string }> {
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
    private async findWorkspaceFiles(
        workspaceUri: vscode.Uri,
        maxFileSize: number
    ): Promise<FileInfo[]> {
        const files: FileInfo[] = [];

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

            } catch (error) {
                this.log(`Failed to read ${uri.fsPath}: ${error}`);
            }
        }

        return files;
    }

    /**
     * 차단된 파일인지 확인
     */
    private isBlocked(filePath: string): boolean {
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
    private getRelativePath(baseUri: vscode.Uri, targetUri: vscode.Uri): string {
        const relative = path.relative(baseUri.fsPath, targetUri.fsPath);
        return relative.replace(/\\/g, '/'); // Windows 경로를 Unix 스타일로 변환
    }

    /**
     * 로그 출력
     */
    private log(message: string): void {
        const timestamp = new Date().toLocaleTimeString();
        this.outputChannel.appendLine(`[${timestamp}] ${message}`);
    }
}
