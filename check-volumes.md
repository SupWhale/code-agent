# Docker Volume 및 Ollama 모델 확인 가이드

## 서버에서 실행할 명령어

### 1. Docker Volume 확인
```bash
# 모든 볼륨 목록 확인
docker volume ls

# ollama 관련 볼륨 찾기
docker volume ls | grep ollama
```

### 2. Ollama 컨테이너 확인
```bash
# 실행 중인 컨테이너 확인
docker ps

# 모든 컨테이너 확인 (중지된 것 포함)
docker ps -a | grep ollama
```

### 3. 기존 모델 확인 (Ollama 컨테이너가 실행 중이라면)
```bash
# Ollama 컨테이너에서 모델 목록 확인
docker exec ollama ollama list
```

---

## 결과에 따른 액션

### Case 1: Ollama 컨테이너가 실행 중이고 모델이 있는 경우
```bash
docker exec ollama ollama list
# qwen2.5-coder:14b 가 보이면 → 다시 받을 필요 없음!
```

**액션**: 그냥 새 프로젝트로 진행하면 됩니다.

---

### Case 2: Ollama 볼륨은 있지만 컨테이너가 없는 경우
```bash
docker volume ls | grep ollama
# ollama_data 또는 deployment_ollama_data 등이 보이면 → 볼륨 존재
```

**액션**: Docker Compose로 컨테이너를 시작하면 기존 모델 사용 가능
```bash
cd ~/coding-agent-project/deployment
docker compose up -d
docker exec ollama ollama list  # 모델 확인
```

---

### Case 3: Ollama 관련 아무것도 없는 경우
```bash
docker volume ls | grep ollama
# 아무것도 안 나오면 → 모델도 없음
```

**액션**: 처음부터 다시 설정
```bash
cd ~/coding-agent-project/deployment
docker compose up -d --build
# 모델 다운로드 (약 8GB, 10-30분 소요)
docker exec ollama ollama pull qwen2.5-coder:14b
```

---

## 빠른 확인 스크립트

서버에서 한 번에 확인:
```bash
echo "=== Docker Volumes ==="
docker volume ls | grep -E "ollama|deployment"

echo -e "\n=== Docker Containers ==="
docker ps -a | grep -E "ollama|coding-agent"

echo -e "\n=== Ollama Models (if running) ==="
docker exec ollama ollama list 2>/dev/null || echo "Ollama 컨테이너가 실행되지 않음"
```