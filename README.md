# 🤖 AI Coding Agent

오픈소스 LLM(Ollama + Qwen2.5-Coder 14B)을 활용한 AI 코딩 에이전트

GPU 가속 지원 | 실시간 스트리밍 | 파일 시스템 통합 | Prometheus + Grafana 모니터링

---

## 📋 목차

- [주요 기능](#주요-기능)
- [시스템 요구사항](#시스템-요구사항)
- [빠른 시작](#빠른-시작)
- [API 문서](#api-문서)
- [개발 가이드](#개발-가이드)
- [배포 가이드](#배포-가이드)
- [모니터링](#모니터링)
- [문제 해결](#문제-해결)
- [라이선스](#라이선스)

---

## ✨ 주요 기능

### 🚀 코드 생성
- **스트리밍/논스트리밍** 응답 지원
- **다국어 지원**: Python, JavaScript, TypeScript, Go 등
- **버퍼링 최적화**: 10글자 단위 또는 줄바꿈 시 즉시 전송
- **한글 완벽 지원**: UTF-8 인코딩, Unicode 이스케이프 없음

### 📁 파일 시스템 통합
- 파일 업로드/다운로드
- 디렉토리 탐색
- 파일 읽기/쓰기/삭제
- 경로 탐색 공격 방지
- 파일 크기 제한 (100MB)

### 🔍 코드 분석
- **단일 파일 분석**: 일반, 보안, 성능, 스타일
- **프로젝트 전체 분석**: 구조, 아키텍처, 개선점

### 💬 실시간 채팅
- **WebSocket 기반**: 양방향 통신
- **대화 히스토리**: 최근 20개 메시지 유지
- **버퍼링 스트리밍**: 자연스러운 응답

### 📊 모니터링
- **Prometheus**: 메트릭 수집
- **Grafana**: 실시간 대시보드
- **Node Exporter**: 시스템 메트릭
- **커스텀 메트릭**: API 요청, 응답 시간, WebSocket 연결 등

---

## 🖥️ 시스템 요구사항

### 서버
- **OS**: Ubuntu 22.04 LTS 이상
- **CPU**: 4코어 이상 권장
- **GPU**: NVIDIA GPU (VRAM 12GB 이상 권장)
- **RAM**: 16GB 이상 (24GB 권장)
- **Storage**: 50GB 이상

### 개발 환경
- **OS**: Windows 10/11 + WSL2 (Ubuntu 22.04) 또는 Linux/macOS
- **Python**: 3.11 이상
- **Docker**: 최신 버전
- **Git**: 최신 버전

### GPU 지원
- NVIDIA Container Toolkit 설치 필요
- CUDA 호환 GPU

---

## 🚀 빠른 시작

### 1. 저장소 클론

```bash
git clone https://github.com/yourusername/coding-agent-project.git
cd coding-agent-project
```

### 2. 빠른 설정

```bash
bash quick_start.sh
```

이 스크립트는 다음을 자동으로 수행합니다:
- 환경 확인 (Python, Git, Docker)
- 서버 정보 입력 및 `.env.deploy` 생성
- `.env` 파일 생성
- 가상환경 설정 및 의존성 설치
- SSH 연결 테스트
- Git 저장소 초기화

### 3. 개발 서버 시작

```bash
make dev
```

또는

```bash
bash scripts/dev.sh
```

서비스 접속:
- **API**: http://localhost:8000
- **API 문서**: http://localhost:8000/docs
- **헬스체크**: http://localhost:8000/health

### 4. Ollama 모델 다운로드

```bash
# Ollama가 실행 중인 경우
ollama pull qwen2.5-coder:7b

# Docker 컨테이너 내부에서
docker exec ollama ollama pull qwen2.5-coder:7b
```

---

## 📚 API 문서

### 기본 엔드포인트

```bash
# 서비스 정보
GET /

# 헬스체크
GET /health

# Prometheus 메트릭
GET /metrics
```

### 코드 생성

```bash
# 스트리밍 응답
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Hello World를 출력하는 Python 함수",
    "language": "python",
    "temperature": 0.1,
    "stream": true
  }'

# 논스트리밍 응답
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "피보나치 수열 함수",
    "language": "python",
    "stream": false
  }'
```

### 파일 작업

```bash
# 파일 업로드
curl -X POST http://localhost:8000/api/v1/files/upload?path=/ \
  -F "file=@example.py"

# 파일 목록
curl http://localhost:8000/api/v1/files/list?path=/

# 파일 읽기
curl http://localhost:8000/api/v1/files/read?path=/example.py

# 파일 다운로드
curl -O http://localhost:8000/api/v1/files/download?path=/example.py

# 파일 삭제
curl -X DELETE http://localhost:8000/api/v1/files/delete?path=/example.py
```

### 코드 분석

```bash
# 파일 분석
curl -X POST http://localhost:8000/api/v1/analyze/file \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/example.py",
    "analysis_type": "security"
  }'

# 프로젝트 분석
curl -X POST http://localhost:8000/api/v1/analyze/project \
  -H "Content-Type: application/json" \
  -d '{
    "project_path": "/",
    "include_patterns": ["**/*.py"],
    "exclude_patterns": ["**/venv/**"]
  }'
```

### WebSocket 채팅

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/chat?client_id=user123');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'content') {
    console.log(data.data);
  } else if (data.type === 'done') {
    console.log('응답 완료');
  }
};

ws.send(JSON.stringify({
  message: '안녕하세요! Python으로 간단한 웹 서버를 만들고 싶어요.'
}));
```

상세한 API 문서는 `/docs` 엔드포인트에서 확인하세요.

---

## 🛠️ 개발 가이드

### 프로젝트 구조

```
coding-agent-project/
├── src/                    # 소스 코드
│   ├── main.py            # FastAPI 메인 앱
│   ├── routes/            # API 라우트
│   ├── services/          # 비즈니스 로직
│   └── utils/             # 유틸리티
├── tests/                 # 테스트
├── docker/                # Docker 설정
├── deployment/            # 배포 설정
├── scripts/               # 스크립트
└── .vscode/               # VS Code 설정
```

### 개발 워크플로우

```bash
# 1. 브랜치 생성
git checkout -b feature/your-feature

# 2. 코드 작성

# 3. 코드 포맷팅
make format

# 4. 린팅
make lint

# 5. 테스트
make test

# 6. 커밋
git add .
git commit -m "feat: your feature"

# 7. 푸시
git push origin feature/your-feature
```

### 사용 가능한 명령어

```bash
make help          # 도움말
make setup         # 초기 설정
make dev           # 개발 서버
make dev-docker    # Docker 개발 환경
make test          # 테스트
make lint          # 린팅
make format        # 포맷팅
make deploy-local  # 로컬 배포
make deploy-server # 서버 배포
make ssh           # 서버 SSH
make logs-server   # 서버 로그
make clean         # 정리
```

---

## 🚢 배포 가이드

### 로컬 Docker 배포

```bash
make deploy-local
```

서비스 접속:
- API: http://localhost:8000
- Grafana: http://localhost:3000 (admin / admin123)
- Prometheus: http://localhost:9090

### 서버 배포

```bash
# 1. 서버 정보 설정 (.env.deploy)
bash quick_start.sh

# 2. 배포
make deploy-server
```

배포 프로세스:
1. 로컬 테스트 실행
2. Git 상태 확인
3. SSH 연결 테스트
4. 서버에 백업 생성
5. 파일 동기화 (rsync)
6. Docker 이미지 빌드
7. 컨테이너 재시작
8. 헬스체크 (최대 5회 재시도)
9. 실패 시 자동 롤백

### 롤백

```bash
make rollback
```

선택 옵션:
1. Git HEAD~1로 롤백
2. 백업 파일로 롤백

---

## 📊 모니터링

### Grafana 대시보드

http://localhost:3000 접속 (admin / admin123)

**패널**:
1. 총 API 요청 수
2. 초당 요청 수 (RPS)
3. 활성 WebSocket 연결
4. API 응답 시간 (95 백분위수)
5. 모델 추론 시간
6. 파일 작업 통계
7. CPU 사용률
8. 메모리 사용률
9. 네트워크 I/O

### Prometheus

http://localhost:9090 접속

**커스텀 메트릭**:
- `api_requests_total`: API 요청 수
- `api_response_time_seconds`: 응답 시간
- `active_websockets`: WebSocket 연결
- `model_inference_time_seconds`: 추론 시간
- `file_operations_total`: 파일 작업 수

---

## 🔧 문제 해결

### Ollama 연결 실패

```bash
# Ollama 컨테이너 확인
docker ps | grep ollama

# 로그 확인
docker logs ollama

# 재시작
docker restart ollama
```

### GPU 인식 안 됨

```bash
# NVIDIA Container Toolkit 설치 확인
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi

# Docker Compose에서 GPU 설정 확인
grep -A 5 "deploy:" deployment/docker-compose.yml
```

### 헬스체크 실패

```bash
# 로그 확인
docker logs coding-agent

# 컨테이너 상태 확인
docker ps -a

# 수동 헬스체크
curl http://localhost:8000/health
```

### 포트 충돌

```bash
# 포트 사용 확인
netstat -an | grep :8000

# 다른 포트 사용 (.env 수정)
API_PORT=8001
```

더 많은 문제 해결 방법은 [SETUP.md](SETUP.md)를 참조하세요.

---

## 📝 라이선스

MIT License

---

## 🙏 기여

이슈와 PR을 환영합니다!

1. Fork
2. 브랜치 생성 (`git checkout -b feature/amazing`)
3. 커밋 (`git commit -m 'Add amazing feature'`)
4. 푸시 (`git push origin feature/amazing`)
5. Pull Request 생성

---

## 📧 문의

문제가 있거나 질문이 있으시면 Issue를 생성해주세요.

---

**Happy Coding! 🚀**
