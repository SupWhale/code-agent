# 배포 가이드 (Deployment Guide)

리눅스 Docker 서버에서 AI Coding Agent를 배포하는 방법입니다.

---

## 📋 사전 요구사항

### 1. 하드웨어
- **GPU**: NVIDIA GPU (VRAM 12GB+ 권장)
- **CPU**: 4 cores 이상
- **RAM**: 16GB 이상
- **Storage**: 50GB 이상 (모델 파일 포함)

### 2. 소프트웨어
- Ubuntu 22.04 LTS (또는 다른 Linux 배포판)
- Docker 20.10+
- Docker Compose 2.0+
- NVIDIA Container Toolkit (GPU 사용 시)

---

## 🚀 배포 단계

### 1단계: 저장소 클론

```bash
# 프로젝트 클론
git clone <repository-url> coding-agent
cd coding-agent
```

### 2단계: 환경 변수 설정

```bash
# .env 파일 생성
cd deployment
cat > .env << 'EOF'
# Grafana 관리자 비밀번호
GRAFANA_ADMIN_PASSWORD=your_secure_password_here

# Ollama 설정
OLLAMA_HOST=http://ollama:11434
MODEL_NAME=qwen2.5-coder:14b

# API 설정
API_PORT=8000
LOG_LEVEL=INFO
MAX_FILE_SIZE=104857600
WORKERS=4

# Workspace
WORKSPACE_PATH=/workspace
EOF
```

### 3단계: 필요한 디렉토리 생성

```bash
# deployment 디렉토리에서
mkdir -p workspace
mkdir -p workspace/src
mkdir -p workspace/tests
mkdir -p models

# 퍼미션 설정
chmod -R 777 workspace
chmod -R 777 models
```

### 4단계: Docker Compose 빌드 및 실행

```bash
# deployment 디렉토리에서
docker-compose build

# 서비스 시작
docker-compose up -d

# 로그 확인
docker-compose logs -f coding-agent
```

### 5단계: Ollama 모델 다운로드

```bash
# Ollama 컨테이너 접속
docker exec -it ollama bash

# 모델 다운로드 (컨테이너 내부에서)
ollama pull qwen2.5-coder:14b

# 확인
ollama list

# 종료
exit
```

### 6단계: 헬스체크 확인

```bash
# API 헬스체크
curl http://localhost:8000/health

# Swagger UI 접속
curl http://localhost:8000/docs

# Ollama 확인
curl http://localhost:11434/api/tags
```

---

## 🔧 서비스 관리

### 상태 확인
```bash
docker-compose ps
```

### 로그 확인
```bash
# 전체 로그
docker-compose logs

# 특정 서비스 로그 (실시간)
docker-compose logs -f coding-agent
docker-compose logs -f ollama
```

### 재시작
```bash
# 전체 재시작
docker-compose restart

# 특정 서비스 재시작
docker-compose restart coding-agent
```

### 중지
```bash
docker-compose stop
```

### 완전 삭제 (데이터 포함)
```bash
docker-compose down -v
```

---

## 📊 모니터링

### Prometheus
- URL: http://localhost:9090
- 메트릭 확인 가능

### Grafana
- URL: http://localhost:3000
- 로그인: admin / (설정한 비밀번호)
- 대시보드 자동 프로비저닝됨

### Node Exporter
- URL: http://localhost:9100/metrics
- 시스템 메트릭 수집

---

## 🧪 API 테스트

### 1. 작업 생성
```bash
curl -X POST "http://localhost:8000/api/v1/agent/task" \
  -H "Content-Type: application/json" \
  -d '{
    "user_request": "src 디렉토리의 파일 목록을 보여줘",
    "workspace_path": "/workspace"
  }'
```

### 2. 작업 조회
```bash
# task_id는 위에서 받은 것 사용
curl "http://localhost:8000/api/v1/agent/task/{task_id}"
```

### 3. 작업 실행 (SSE)
```bash
curl -N "http://localhost:8000/api/v1/agent/task/{task_id}/execute"
```

### 4. 작업 목록
```bash
curl "http://localhost:8000/api/v1/agent/tasks"
```

---

## 🔒 보안 고려사항

### 1. 방화벽 설정
```bash
# 필요한 포트만 개방
sudo ufw allow 80/tcp    # Nginx (프로덕션)
sudo ufw allow 443/tcp   # HTTPS (프로덕션)
sudo ufw allow 8000/tcp  # API (개발 시에만)
```

### 2. SSL/TLS 설정
```bash
# Let's Encrypt 인증서 발급
# deployment/nginx/nginx.conf에서 SSL 설정 활성화
```

### 3. 환경 변수 보안
- `.env` 파일은 절대 Git에 커밋하지 마세요
- 프로덕션 비밀번호는 강력하게 설정하세요

### 4. Workspace 격리
- Docker volume으로 workspace 격리됨
- 경로 탐색 공격 방지 기능 내장

---

## 🐛 트러블슈팅

### 문제 1: Ollama 모델이 느림
```bash
# GPU 사용 확인
docker exec ollama nvidia-smi

# GPU 메모리 확인
docker stats ollama
```

**해결**: GPU가 인식되지 않으면 NVIDIA Container Toolkit 재설치

### 문제 2: Agent 시스템 초기화 실패
```bash
# 로그 확인
docker-compose logs coding-agent | grep "ERROR"
```

**주요 원인**:
- Ollama 서버가 시작되지 않음
- Workspace 경로 권한 문제

**해결**:
```bash
# Workspace 권한 재설정
chmod -R 777 deployment/workspace

# Ollama 재시작
docker-compose restart ollama
docker-compose restart coding-agent
```

### 문제 3: 포트 충돌
```bash
# 사용 중인 포트 확인
sudo netstat -tulpn | grep LISTEN
```

**해결**: docker-compose.yml에서 포트 변경

### 문제 4: 메모리 부족
```bash
# 메모리 사용량 확인
docker stats
```

**해결**:
- docker-compose.yml에서 WORKERS 수 줄이기
- 더 작은 모델 사용 (qwen2.5-coder:7b)

---

## 📦 업데이트

### 코드 업데이트
```bash
# 최신 코드 가져오기
git pull origin main

# 재빌드 및 재시작
docker-compose build coding-agent
docker-compose up -d coding-agent
```

### 모델 업데이트
```bash
# 새 모델 다운로드
docker exec -it ollama ollama pull qwen2.5-coder:latest

# 환경 변수 업데이트 후 재시작
docker-compose restart coding-agent
```

---

## 🔄 백업 및 복구

### 백업
```bash
# Prometheus 데이터
docker run --rm -v deployment_prometheus-data:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/prometheus-backup.tar.gz /data

# Grafana 데이터
docker run --rm -v deployment_grafana-data:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/grafana-backup.tar.gz /data

# Ollama 모델
tar czf models-backup.tar.gz deployment/models/
```

### 복구
```bash
# Volume 복구
docker run --rm -v deployment_prometheus-data:/data -v $(pwd):/backup \
  ubuntu tar xzf /backup/prometheus-backup.tar.gz -C /

# 모델 복구
tar xzf models-backup.tar.gz
```

---

## 📈 성능 최적화

### 1. Worker 수 조정
```yaml
# docker-compose.yml
environment:
  - WORKERS=8  # CPU 코어 수에 맞춰 조정
```

### 2. Ollama GPU 설정
```yaml
# docker-compose.yml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all  # 모든 GPU 사용
```

### 3. Redis 캐싱 추가 (선택사항)
```yaml
# docker-compose.yml에 Redis 서비스 추가
redis:
  image: redis:alpine
  ports:
    - "6379:6379"
```

---

## ✅ 배포 체크리스트

- [ ] Git 저장소 클론
- [ ] 환경 변수 설정 (.env 파일)
- [ ] 필요한 디렉토리 생성 및 권한 설정
- [ ] Docker Compose 빌드
- [ ] 서비스 시작
- [ ] Ollama 모델 다운로드
- [ ] 헬스체크 확인
- [ ] API 테스트 실행
- [ ] 모니터링 대시보드 확인
- [ ] 방화벽 설정
- [ ] SSL/TLS 설정 (프로덕션)
- [ ] 백업 스크립트 설정

---

## 📞 지원

문제가 발생하면:
1. 로그 확인: `docker-compose logs`
2. GitHub Issues에 보고
3. [README_AGENT.md](./README_AGENT.md) 참조

---

**배포 완료!** 🎉

이제 `http://your-server:8000/docs`에서 API를 사용할 수 있습니다.
