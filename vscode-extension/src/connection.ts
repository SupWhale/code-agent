/**
 * WebSocket Connection Manager
 *
 * AI Agent 서버와의 WebSocket 연결을 관리합니다.
 */

import WebSocket from 'ws';
import * as vscode from 'vscode';

export interface AgentMessage {
    type: string;
    [key: string]: any;
}

export interface FileInfo {
    path: string;
    content: string;
}

export class AgentConnection {
    private ws: WebSocket | null = null;
    private sessionId: string = '';
    private reconnectAttempts = 0;
    private readonly maxReconnectAttempts = 5;
    private readonly reconnectDelay = 3000;
    private messageHandlers: Map<string, (message: AgentMessage) => void> = new Map();

    constructor(
        private serverUrl: string,
        private outputChannel: vscode.OutputChannel
    ) {}

    /**
     * 서버 연결
     */
    async connect(): Promise<void> {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.log('Already connected');
            return;
        }

        return new Promise((resolve, reject) => {
            // 세션 ID 생성
            this.sessionId = this.generateSessionId();

            // WebSocket URL 구성
            const wsUrl = `${this.serverUrl}/api/v1/vscode/ws/${this.sessionId}`;
            this.log(`Connecting to ${wsUrl}...`);

            this.ws = new WebSocket(wsUrl);

            this.ws.on('open', () => {
                this.log('Connected to AI Agent server');
                this.reconnectAttempts = 0;
                vscode.window.showInformationMessage('✅ AI Agent 서버 연결 성공!');
                resolve();
            });

            this.ws.on('message', (data: WebSocket.Data) => {
                try {
                    const message: AgentMessage = JSON.parse(data.toString());
                    this.handleMessage(message);
                } catch (error) {
                    this.log(`Failed to parse message: ${error}`);
                }
            });

            this.ws.on('error', (error) => {
                this.log(`WebSocket error: ${error.message}`);
                reject(error);
            });

            this.ws.on('close', () => {
                this.log('Connection closed');
                this.ws = null;

                // 자동 재연결
                if (this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.reconnectAttempts++;
                    this.log(`Reconnecting in ${this.reconnectDelay}ms (attempt ${this.reconnectAttempts})...`);
                    setTimeout(() => this.connect(), this.reconnectDelay);
                } else {
                    vscode.window.showErrorMessage('❌ AI Agent 서버 연결 끊김');
                }
            });

            // 타임아웃
            setTimeout(() => {
                if (this.ws && this.ws.readyState !== WebSocket.OPEN) {
                    reject(new Error('Connection timeout'));
                }
            }, 10000);
        });
    }

    /**
     * 연결 해제
     */
    disconnect(): void {
        if (this.ws) {
            this.reconnectAttempts = this.maxReconnectAttempts; // 재연결 방지
            this.ws.close();
            this.ws = null;
            this.log('Disconnected');
            vscode.window.showInformationMessage('AI Agent 연결 해제됨');
        }
    }

    /**
     * 연결 상태 확인
     */
    isConnected(): boolean {
        return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
    }

    /**
     * 메시지 전송
     */
    send(message: AgentMessage): void {
        if (!this.isConnected()) {
            throw new Error('Not connected to server');
        }

        this.ws!.send(JSON.stringify(message));
        this.log(`Sent: ${message.type}`);
    }

    /**
     * 파일 업로드
     */
    async uploadFiles(files: FileInfo[]): Promise<void> {
        this.send({
            type: 'file_upload',
            files: files
        });

        this.log(`Uploaded ${files.length} files`);
    }

    /**
     * Agent 요청
     */
    async requestAgent(userRequest: string, context?: any): Promise<void> {
        this.send({
            type: 'agent_request',
            user_request: userRequest,
            context: context || {}
        });

        this.log(`Agent request: ${userRequest}`);
    }

    /**
     * Ping (연결 유지)
     */
    ping(): void {
        this.send({ type: 'ping' });
    }

    /**
     * 메시지 핸들러 등록
     */
    on(messageType: string, handler: (message: AgentMessage) => void): void {
        this.messageHandlers.set(messageType, handler);
    }

    /**
     * 메시지 핸들러 제거
     */
    off(messageType: string): void {
        this.messageHandlers.delete(messageType);
    }

    /**
     * 메시지 처리
     */
    private handleMessage(message: AgentMessage): void {
        this.log(`Received: ${message.type}`);

        const handler = this.messageHandlers.get(message.type);
        if (handler) {
            try {
                handler(message);
            } catch (error) {
                this.log(`Handler error for ${message.type}: ${error}`);
            }
        }
    }

    /**
     * 세션 ID 생성
     */
    private generateSessionId(): string {
        return `vscode-${Date.now()}-${Math.random().toString(36).substring(7)}`;
    }

    /**
     * 로그 출력
     */
    private log(message: string): void {
        const timestamp = new Date().toLocaleTimeString();
        this.outputChannel.appendLine(`[${timestamp}] ${message}`);
    }

    /**
     * 세션 ID 조회
     */
    getSessionId(): string {
        return this.sessionId;
    }
}
