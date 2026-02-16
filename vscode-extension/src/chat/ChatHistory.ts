import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';

export interface ChatMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
}

export interface ChatSession {
    id: string;
    title: string;
    messages: ChatMessage[];
    createdAt: Date;
    updatedAt: Date;
}

export class ChatHistory {
    private historyPath: string;
    private currentSession: ChatSession | null = null;

    constructor(private context: vscode.ExtensionContext) {
        this.historyPath = path.join(context.globalStorageUri.fsPath, 'chat-history.json');
        this._ensureHistoryDirectory();
    }

    private _ensureHistoryDirectory() {
        const dir = path.dirname(this.historyPath);
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
    }

    /**
     * 새 세션 생성
     */
    createSession(title?: string): ChatSession {
        this.currentSession = {
            id: this._generateId(),
            title: title || `Chat ${new Date().toLocaleString()}`,
            messages: [],
            createdAt: new Date(),
            updatedAt: new Date()
        };
        return this.currentSession;
    }

    /**
     * 메시지 추가
     */
    addMessage(role: 'user' | 'assistant', content: string): ChatMessage {
        if (!this.currentSession) {
            this.createSession();
        }

        const message: ChatMessage = {
            id: this._generateId(),
            role,
            content,
            timestamp: new Date()
        };

        this.currentSession!.messages.push(message);
        this.currentSession!.updatedAt = new Date();

        return message;
    }

    /**
     * 세션 저장
     */
    async saveSession(): Promise<void> {
        if (!this.currentSession) {
            return;
        }

        try {
            const sessions = await this.loadAllSessions();
            const index = sessions.findIndex(s => s.id === this.currentSession!.id);

            if (index >= 0) {
                sessions[index] = this.currentSession;
            } else {
                sessions.push(this.currentSession);
            }

            // 최대 100개 세션만 유지
            const limitedSessions = sessions.slice(-100);

            fs.writeFileSync(
                this.historyPath,
                JSON.stringify(limitedSessions, null, 2),
                'utf-8'
            );
        } catch (error) {
            console.error('Failed to save chat history:', error);
        }
    }

    /**
     * 모든 세션 로드
     */
    async loadAllSessions(): Promise<ChatSession[]> {
        try {
            if (!fs.existsSync(this.historyPath)) {
                return [];
            }

            const data = fs.readFileSync(this.historyPath, 'utf-8');
            const sessions = JSON.parse(data);

            // Date 객체로 변환
            return sessions.map((session: any) => ({
                ...session,
                createdAt: new Date(session.createdAt),
                updatedAt: new Date(session.updatedAt),
                messages: session.messages.map((msg: any) => ({
                    ...msg,
                    timestamp: new Date(msg.timestamp)
                }))
            }));
        } catch (error) {
            console.error('Failed to load chat history:', error);
            return [];
        }
    }

    /**
     * 세션 로드
     */
    async loadSession(sessionId: string): Promise<ChatSession | null> {
        const sessions = await this.loadAllSessions();
        const session = sessions.find(s => s.id === sessionId);
        if (session) {
            this.currentSession = session;
        }
        return session || null;
    }

    /**
     * 현재 세션 가져오기
     */
    getCurrentSession(): ChatSession | null {
        return this.currentSession;
    }

    /**
     * 세션 삭제
     */
    async deleteSession(sessionId: string): Promise<void> {
        try {
            const sessions = await this.loadAllSessions();
            const filtered = sessions.filter(s => s.id !== sessionId);

            fs.writeFileSync(
                this.historyPath,
                JSON.stringify(filtered, null, 2),
                'utf-8'
            );

            if (this.currentSession?.id === sessionId) {
                this.currentSession = null;
            }
        } catch (error) {
            console.error('Failed to delete session:', error);
        }
    }

    /**
     * 모든 히스토리 삭제
     */
    async clearAll(): Promise<void> {
        try {
            if (fs.existsSync(this.historyPath)) {
                fs.unlinkSync(this.historyPath);
            }
            this.currentSession = null;
        } catch (error) {
            console.error('Failed to clear history:', error);
        }
    }

    private _generateId(): string {
        return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    }
}
