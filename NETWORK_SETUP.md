# 네트워크 연결 구조

## 🌐 전체 아키텍처

```
[클라이언트 PC]                    [서버 PC: 192.168.0.149]
┌─────────────────────┐           ┌────────────────────────────────┐
│                     │           │                                │
│  VS Code            │           │  Docker Network                │
│  Extension          │           │  ┌──────────────────────────┐  │
│                     │ WebSocket │  │  coding-agent            │  │
│                     │───────────┼─>│  (FastAPI)               │  │
│                     │    :8000  │  │  Port: 8000              │  │
└─────────────────────┘           │  └───────────┬──────────────┘  │
                                  │              │ HTTP           │
  ws://192.168.0.149:8000         │              │ :11434         │
                                  │  ┌───────────▼──────────────┐  │
                                  │  │  ollama                  │  │
                                  │  │  (AI Model)              │  │
                                  │  │  Port: 11434             │  │
                                  │  └──────────────────────────┘  │
                                  │                                │
                                  └────────────────────────────────┘
```

## 🔌 연결 단계

### 1. 클라이언트 → 서버 (WebSocket)

**프로토콜**: WebSocket
**URL**: `ws://192.168.0.149:8000/api/v1/vscode/ws/{session_id}`

```typescript
// VS Code Extension (connection.ts)
const wsUrl = `ws://192.168.0.149:8000/api/v1/vscode/ws/${sessionId}`;
this.ws = new WebSocket(wsUrl);
```

### 2. 서버 FastAPI → Docker Ollama (HTTP)

**프로토콜**: HTTP
**URL**: `http://ollama:11434` (Docker 내부 네트워크)

```python
# src/main.py
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Docker Compose에서:
# OLLAMA_HOST=http://ollama:11434
```

## ⚙️ 설정 방법

### VS Code Extension 설정

#### 로컬 개발 (같은 컴퓨터)
```json
{
  "aiAgent.serverUrl": "ws://localhost:8000"
}
```

#### 원격 서버 (다른 컴퓨터)
```json
{
  "aiAgent.serverUrl": "ws://192.168.0.149:8000"
}
```

**설정 방법**:
1. VS Code에서 `Ctrl+,` (설정)
2. "ai agent server" 검색
3. `Server Url` 필드에 입력

### 서버 실행

#### Docker Compose (프로덕션)
```bash
cd deployment
docker compose up -d

# 포트 확인
# - 8000: FastAPI (외부 접속 허용)
# - 11434: Ollama (Docker 내부만)
```

#### 직접 실행 (개발)
```bash
# Ollama 먼저 실행 (Docker 또는 로컬)
docker run -d -p 11434:11434 ollama/ollama

# FastAPI 서버
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

## 🔥 방화벽 설정

### Windows (서버 PC)

```powershell
# 포트 8000 허용 (PowerShell 관리자 권한)
New-NetFirewallRule -DisplayName "AI Coding Agent" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 8000 `
  -Action Allow
```

**GUI 방법**:
1. `Windows Defender 방화벽` 열기
2. `고급 설정` 클릭
3. `인바운드 규칙` → `새 규칙`
4. `포트` → `TCP` → `특정 로컬 포트: 8000`
5. `연결 허용` → 이름: "AI Coding Agent"

### Linux (서버 PC)

```bash
# ufw (Ubuntu/Debian)
sudo ufw allow 8000/tcp

# firewalld (CentOS/RHEL)
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

## 🧪 연결 테스트

### 1. 서버 헬스 체크

```bash
# 서버 PC에서
curl http://localhost:8000/health

# 클라이언트 PC에서
curl http://192.168.0.149:8000/health
```

**예상 결과**:
```json
{
  "status": "healthy",
  "timestamp": "2026-02-16T12:00:00.000Z"
}
```

### 2. WebSocket 연결 테스트

```bash
# wscat 설치 (Node.js 필요)
npm install -g wscat

# 연결 테스트
wscat -c ws://192.168.0.149:8000/api/v1/vscode/ws/test-session
```

**예상 결과**:
```json
{"type":"session_created","session_id":"test-session"}
{"type":"connected","session_id":"test-session"}
```

### 3. Ollama 연결 테스트

```bash
# 서버 PC에서 (Docker 내부)
docker exec -it coding-agent curl http://ollama:11434/api/version

# 또는 서버 PC에서 (외부)
curl http://localhost:11434/api/version
```

## 🔍 문제 해결

### 클라이언트가 서버에 연결 안 됨

**증상**: VS Code Extension에서 "연결 실패"

**확인사항**:
1. 서버가 실행 중인가?
   ```bash
   docker ps | grep coding-agent
   ```

2. 포트가 열려있는가?
   ```bash
   netstat -an | grep 8000
   ```

3. 방화벽이 허용하는가?
   ```bash
   # Windows
   netsh advfirewall firewall show rule name="AI Coding Agent"

   # Linux
   sudo ufw status | grep 8000
   ```

4. 올바른 IP 주소인가?
   ```bash
   # 서버 PC에서 IP 확인
   ipconfig  # Windows
   ip addr   # Linux
   ```

### FastAPI가 Ollama에 연결 안 됨

**증상**: "Failed to connect to Ollama"

**확인사항**:
1. Ollama 컨테이너 실행 중인가?
   ```bash
   docker ps | grep ollama
   ```

2. Docker 네트워크가 올바른가?
   ```bash
   docker network inspect coding-agent-network
   ```

3. 환경변수가 올바른가?
   ```bash
   docker exec coding-agent env | grep OLLAMA
   # OLLAMA_HOST=http://ollama:11434
   ```

### WebSocket 연결이 자주 끊김

**원인**: Nginx 또는 프록시 타임아웃

**해결**:
```nginx
# nginx.conf
location /api/v1/vscode/ws/ {
    proxy_pass http://coding-agent:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400;  # 24시간
}
```

## 📊 포트 요약

| 서비스 | 포트 | 외부 접속 | 용도 |
|--------|------|----------|------|
| **FastAPI** | 8000 | ✅ 허용 | VS Code Extension 연결 |
| **Ollama** | 11434 | ❌ 내부만 | AI 모델 실행 |
| **Prometheus** | 9090 | ⚠️ 선택 | 메트릭 수집 |
| **Grafana** | 3000 | ⚠️ 선택 | 대시보드 |
| **Nginx** | 80, 443 | ⚠️ 선택 | 리버스 프록시 |

## 🔒 보안 고려사항

### 프로덕션 환경

1. **HTTPS/WSS 사용**
   ```nginx
   # Let's Encrypt 인증서 사용
   server {
       listen 443 ssl;
       ssl_certificate /etc/letsencrypt/live/your-domain/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/your-domain/privkey.pem;
   }
   ```

2. **CORS 제한**
   ```python
   # src/main.py - 특정 origin만 허용
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["http://192.168.0.*"],  # 로컬 네트워크만
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )
   ```

3. **인증 추가**
   - API Key 또는 JWT 토큰
   - VS Code Extension에서 인증 정보 저장

### 개발 환경

현재 설정 (allow_origins=["*"])은 개발에만 적합합니다.

## 🎯 추천 설정

### 홈/사무실 네트워크
```
클라이언트 PC: 192.168.0.100
서버 PC: 192.168.0.149
서버 URL: ws://192.168.0.149:8000
```

### VPN 환경
```
VPN IP: 10.0.0.149
서버 URL: ws://10.0.0.149:8000
```

### 클라우드 서버
```
공인 IP: 1.2.3.4
도메인: ai-agent.example.com
서버 URL: wss://ai-agent.example.com (HTTPS 필수)
```

---

**이제 `192.168.0.149:8000`으로 연결하면 원격 서버의 AI Agent를 사용할 수 있습니다!** 🎉
