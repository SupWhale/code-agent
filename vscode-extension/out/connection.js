"use strict";
/**
 * WebSocket Connection Manager
 *
 * AI Agent 서버와의 WebSocket 연결을 관리합니다.
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
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.AgentConnection = void 0;
const ws_1 = __importDefault(require("ws"));
const vscode = __importStar(require("vscode"));
class AgentConnection {
    constructor(serverUrl, outputChannel) {
        this.serverUrl = serverUrl;
        this.outputChannel = outputChannel;
        this.ws = null;
        this.sessionId = '';
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000;
        this.messageHandlers = new Map();
    }
    /**
     * 서버 연결
     */
    async connect() {
        if (this.ws && this.ws.readyState === ws_1.default.OPEN) {
            this.log('Already connected');
            return;
        }
        return new Promise((resolve, reject) => {
            // 세션 ID 생성
            this.sessionId = this.generateSessionId();
            // WebSocket URL 구성
            const wsUrl = `${this.serverUrl}/api/v1/vscode/ws/${this.sessionId}`;
            this.log(`Connecting to ${wsUrl}...`);
            this.ws = new ws_1.default(wsUrl);
            this.ws.on('open', () => {
                this.log('Connected to AI Agent server');
                this.reconnectAttempts = 0;
                vscode.window.showInformationMessage('✅ AI Agent 서버 연결 성공!');
                resolve();
            });
            this.ws.on('message', (data) => {
                try {
                    const message = JSON.parse(data.toString());
                    this.handleMessage(message);
                }
                catch (error) {
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
                }
                else {
                    vscode.window.showErrorMessage('❌ AI Agent 서버 연결 끊김');
                }
            });
            // 타임아웃
            setTimeout(() => {
                if (this.ws && this.ws.readyState !== ws_1.default.OPEN) {
                    reject(new Error('Connection timeout'));
                }
            }, 10000);
        });
    }
    /**
     * 연결 해제
     */
    disconnect() {
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
    isConnected() {
        return this.ws !== null && this.ws.readyState === ws_1.default.OPEN;
    }
    /**
     * 메시지 전송
     */
    send(message) {
        if (!this.isConnected()) {
            throw new Error('Not connected to server');
        }
        this.ws.send(JSON.stringify(message));
        this.log(`Sent: ${message.type}`);
    }
    /**
     * 파일 업로드
     */
    async uploadFiles(files) {
        this.send({
            type: 'file_upload',
            files: files
        });
        this.log(`Uploaded ${files.length} files`);
    }
    /**
     * Agent 요청
     */
    async requestAgent(userRequest, context) {
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
    ping() {
        this.send({ type: 'ping' });
    }
    /**
     * 메시지 핸들러 등록
     */
    on(messageType, handler) {
        this.messageHandlers.set(messageType, handler);
    }
    /**
     * 메시지 핸들러 제거
     */
    off(messageType) {
        this.messageHandlers.delete(messageType);
    }
    /**
     * 메시지 처리
     */
    handleMessage(message) {
        this.log(`Received: ${message.type}`);
        const handler = this.messageHandlers.get(message.type);
        if (handler) {
            try {
                handler(message);
            }
            catch (error) {
                this.log(`Handler error for ${message.type}: ${error}`);
            }
        }
    }
    /**
     * 세션 ID 생성
     */
    generateSessionId() {
        return `vscode-${Date.now()}-${Math.random().toString(36).substring(7)}`;
    }
    /**
     * 로그 출력
     */
    log(message) {
        const timestamp = new Date().toLocaleTimeString();
        this.outputChannel.appendLine(`[${timestamp}] ${message}`);
    }
    /**
     * 세션 ID 조회
     */
    getSessionId() {
        return this.sessionId;
    }
}
exports.AgentConnection = AgentConnection;
//# sourceMappingURL=connection.js.map