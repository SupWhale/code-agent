# 🚀 서버 배포 가이드

## 서버에서 실행할 명령어 (순서대로)

### 1. 프로젝트 디렉토리로 이동
```bash
cd ~/coding-agent-project
```

### 2. .env 파일 생성
```bash
cat > .env << 'EOF'
# Ollama 설정
OLLAMA_HOST=http://ollama:11434
MODEL_NAME=qwen2.5-coder:7b

# API 설정
API_PORT=8000
LOG_LEVEL=INFO
WORKERS=4

# 파일 시스템
WORKSPACE_PATH=/workspace
MAX_FILE_SIZE=104857600

# Grafana
GRAFANA_ADMIN_PASSWORD=admin123
EOF
```

### 3. deployment 디렉토리로 이동
```bash
cd deployment
```

### 4. models 디렉토리 생성
```bash
mkdir -p models workspace
```

### 5. 기존 컨테이너 정리 (있다면)
```bash
docker compose down
```

### 6. Docker 이미지 빌드
```bash
# 캐시 없이 빌드 (권장)
docker compose build --no-cache

# 또는 일반 빌드
docker compose build
```

### 7. 컨테이너 시작
```bash
docker compose up -d
```

### 8. 컨테이너 상태 확인
```bash
docker ps
```

다음과 같이 5개 컨테이너가 실행되어야 합니다:
- coding-agent
- ollama
- nginx
- prometheus
- grafana
- node-exporter

### 9. 로그 확인
```bash
# 모든 로그
docker compose logs -f

# coding-agent 로그만
docker compose logs -f coding-agent

# 로그 종료: Ctrl+C
```

### 10. Ollama 모델 다운로드
```bash
# 모델 다운로드 (약 8-10GB, 10-30분 소요)
docker exec ollama ollama pull qwen2.5-coder:7b

# 모델 확인
docker exec ollama ollama list
```

### 11. API 헬스체크
```bash
# 로컬에서
curl http://localhost:8000/health

# 응답 예시:
# {"status":"healthy","ollama_status":"connected"}
```

---

## 🔧 문제 해결

### 빌드 에러 발생 시
```bash
# 1. 더 자세한 로그와 함께 빌드
docker compose build --no-cache --progress=plain 2>&1 | tee build.log

# 2. 로그 파일 확인
cat build.log

# 3. 특정 부분만 확인
tail -100 build.log
```

### 컨테이너 시작 실패 시
```bash
# 로그 확인
docker compose logs coding-agent
docker compose logs ollama

# 컨테이너 상태 확인
docker ps -a

# 재시작
docker compose restart
```

### 포트 충돌 발생 시
```bash
# 포트 사용 확인
sudo netstat -tulpn | grep -E "8000|3000|9090|11434"

# 또는
sudo lsof -i :8000
sudo lsof -i :3000
sudo lsof -i :11434
```

---

## ✅ 배포 완료 체크리스트

- [ ] .env 파일 생성 완료
- [ ] Docker Compose 빌드 성공
- [ ] 5개 컨테이너 모두 실행 중
- [ ] Ollama 모델 다운로드 완료
- [ ] API 헬스체크 성공
- [ ] 외부에서 API 접근 가능

---

## 🌐 서비스 접근 URL

서버 IP를 `192.168.1.157`로 가정:

- **API**: http://192.168.1.157:8000
- **API 문서**: http://192.168.1.157:8000/docs
- **Grafana**: http://192.168.1.157:3000 (admin / admin123)
- **Prometheus**: http://192.168.1.157:9090

---

## 🔄 서비스 관리 명령어

```bash
# 서비스 시작
docker compose up -d

# 서비스 중지
docker compose down

# 서비스 재시작
docker compose restart

# 특정 서비스만 재시작
docker compose restart coding-agent

# 로그 확인
docker compose logs -f

# 리소스 사용량 확인
docker stats
```