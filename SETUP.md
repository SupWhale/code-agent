# 🔧 AI Coding Agent - 상세 설정 가이드

이 문서는 Windows WSL2 개발 환경부터 Linux 서버 배포까지 전체 설정 과정을 다룹니다.

---

## 📋 목차

1. [Windows 개발 환경 설정](#1-windows-개발-환경-설정)
2. [프로젝트 클론 및 초기 설정](#2-프로젝트-클론-및-초기-설정)
3. [서버 설정](#3-서버-설정)
4. [배포 설정](#4-배포-설정)
5. [첫 배포](#5-첫-배포)
6. [일일 개발 워크플로우](#6-일일-개발-워크플로우)
7. [트러블슈팅](#7-트러블슈팅)

---

## 1. Windows 개발 환경 설정

### 1.1. WSL2 설치

```powershell
# PowerShell (관리자 권한)
wsl --install
```

재부팅 후:

```powershell
# Ubuntu 22.04 설치
wsl --install -d Ubuntu-22.04

# 기본 배포판 설정
wsl --set-default Ubuntu-22.04
```

### 1.2. WSL2 Ubuntu 설정

```bash
# Ubuntu 업데이트
sudo apt update && sudo apt upgrade -y

# 필수 패키지 설치
sudo apt install -y \
    build-essential \
    curl \
    git \
    python3 \
    python3-pip \
    python3-venv
```

### 1.3. Docker Desktop 설치

1. [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/) 다운로드 및 설치
2. 설정:
   - Settings → General → "Use the WSL 2 based engine" 체크
   - Settings → Resources → WSL Integration → Ubuntu-22.04 활성화

확인:

```bash
docker --version
docker compose version
```

### 1.4. VS Code 설치

1. [VS Code](https://code.visualstudio.com/) 다운로드 및 설치
2. 확장 프로그램 설치:
   - **Remote - WSL** (필수)
   - **Python**
   - **Docker**
   - **GitLens**

WSL에서 VS Code 실행:

```bash
code ~/coding-agent-project
```

---

## 2. 프로젝트 클론 및 초기 설정

### 2.1. 저장소 클론

```bash
# WSL Ubuntu 터미널
cd ~
git clone https://github.com/yourusername/coding-agent-project.git
cd coding-agent-project
```

### 2.2. 빠른 설정 실행

```bash
bash quick_start.sh
```

이 스크립트가 대화형으로 다음을 수행합니다:

1. **환경 확인**: Python, Git, Docker
2. **서버 정보 입력**:
   - 서버 IP 주소
   - 사용자명
   - SSH 포트
   - 프로젝트 경로
3. **.env.deploy 생성**: 배포 설정
4. **.env 생성**: 환경 변수
5. **가상환경 설정**: Python venv
6. **의존성 설치**: requirements-dev.txt
7. **SSH 연결 테스트**
8. **SSH config 설정**: 별칭 추가 (선택)
9. **Git 초기화** (선택)

### 2.3. 수동 설정 (선택)

빠른 설정을 사용하지 않는 경우:

```bash
# 1. 가상환경 생성
python3 -m venv venv
source venv/bin/activate

# 2. 의존성 설치
pip install -r requirements-dev.txt

# 3. 환경 변수 파일 생성
cp .env.example .env
cp .env.deploy.example .env.deploy

# 4. .env.deploy 수정
nano .env.deploy
```

---

## 3. 서버 설정

### 3.1. Ubuntu 서버 기본 설정

```bash
# SSH로 서버 접속
ssh user@server-ip

# 시스템 업데이트
sudo apt update && sudo apt upgrade -y

# 필수 패키지
sudo apt install -y \
    curl \
    git \
    rsync
```

### 3.2. Docker 설치

```bash
# Docker 설치 스크립트
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 사용자를 docker 그룹에 추가
sudo usermod -aG docker $USER

# 재로그인 필요
exit
ssh user@server-ip

# 확인
docker --version
docker compose version
```

### 3.3. NVIDIA Container Toolkit 설치 (GPU 사용 시)

```bash
# NVIDIA Docker 저장소 추가
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
    sudo tee /etc/etc/apt/sources.list.d/nvidia-docker.list

# 설치
sudo apt update
sudo apt install -y nvidia-container-toolkit

# Docker 재시작
sudo systemctl restart docker

# 확인
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
```

### 3.4. 서버 디렉토리 생성

```bash
# 프로젝트 디렉토리
mkdir -p ~/coding-agent-project

# 백업 디렉토리
mkdir -p ~/backup
```

### 3.5. SSH 키 설정 (비밀번호 없이 접속)

로컬 (WSL):

```bash
# SSH 키 생성 (이미 있으면 건너뛰기)
ssh-keygen -t ed25519 -C "your_email@example.com"

# 서버에 공개키 복사
ssh-copy-id -p 22 user@server-ip

# 테스트
ssh user@server-ip
```

---

## 4. 배포 설정

### 4.1. .env.deploy 설정

```bash
# 로컬 (WSL)
nano .env.deploy
```

```bash
# 서버 정보
SERVER_HOST=192.168.1.100
SERVER_USER=supwhale
SERVER_PORT=22
SERVER_PATH=/home/supwhale/coding-agent-project

# 배포 설정
SKIP_TESTS=false              # 배포 전 테스트 실행 여부
BACKUP_BEFORE_DEPLOY=true     # 백업 생성 여부

# Git 설정
GIT_REMOTE=origin
GIT_BRANCH=main
```

### 4.2. .env 설정

```bash
nano .env
```

```bash
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
```

---

## 5. 첫 배포

### 5.1. 로컬 테스트

```bash
# 개발 서버 시작
make dev

# 브라우저에서 확인
# http://localhost:8000
# http://localhost:8000/docs
```

### 5.2. 로컬 Docker 테스트

```bash
# Docker 환경 시작
make deploy-local

# Ollama 모델 다운로드
docker exec ollama ollama pull qwen2.5-coder:7b

# 테스트
curl http://localhost:8000/health

# 종료
cd deployment
docker compose down
```

### 5.3. 서버 배포

```bash
# 1. Git 커밋
git add .
git commit -m "Initial deployment"

# 2. 배포 스크립트 실행
make deploy-server
```

배포 프로세스:
1. ✓ 로컬 테스트 실행
2. ✓ Git 상태 확인
3. ✓ SSH 연결 테스트
4. ✓ 서버에 백업 생성
5. ✓ 파일 동기화 (rsync)
6. ✓ Docker 이미지 빌드
7. ✓ 컨테이너 시작
8. ✓ 헬스체크

### 5.4. 서버에서 Ollama 모델 다운로드

```bash
# SSH 접속
make ssh
# 또는
ssh user@server-ip

# 모델 다운로드
cd ~/coding-agent-project/deployment
docker exec ollama ollama pull qwen2.5-coder:7b

# 확인
docker exec ollama ollama list
```

---

## 6. 일일 개발 워크플로우

### 6.1. 코드 수정

```bash
# 1. VS Code에서 WSL 열기
code ~/coding-agent-project

# 2. 브랜치 생성
git checkout -b feature/new-feature

# 3. 코드 수정

# 4. 개발 서버로 테스트
make dev
```

### 6.2. 코드 품질 검사

```bash
# 포맷팅
make format

# 린팅
make lint

# 테스트
make test
```

### 6.3. 커밋 및 배포

```bash
# 1. Git 커밋
git add .
git commit -m "feat: add new feature"

# 2. 메인 브랜치로 병합
git checkout main
git merge feature/new-feature

# 3. 서버 배포
make deploy-server
```

### 6.4. 배포 확인

```bash
# 서버 로그 확인
make logs-server

# 서버 SSH 접속
make ssh

# 서비스 상태 확인
docker ps
curl http://SERVER_IP:8000/health
```

---

## 7. 트러블슈팅

### 7.1. WSL2 관련

**문제**: WSL2가 네트워크에 연결되지 않음

```powershell
# PowerShell (관리자)
wsl --shutdown
# WSL 재시작
```

**문제**: Docker가 WSL2에서 작동하지 않음

```bash
# WSL Ubuntu
sudo service docker start

# 또는 Docker Desktop 재시작
```

### 7.2. SSH 관련

**문제**: SSH 연결 실패

```bash
# 연결 테스트
ssh -vvv user@server-ip

# 방화벽 확인 (서버)
sudo ufw status
sudo ufw allow 22/tcp
```

**문제**: SSH 키 인증 실패

```bash
# 권한 확인
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub

# 서버에서 authorized_keys 확인
cat ~/.ssh/authorized_keys
```

### 7.3. Docker 관련

**문제**: GPU가 인식되지 않음

```bash
# NVIDIA 드라이버 확인 (서버)
nvidia-smi

# NVIDIA Container Toolkit 확인
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi

# Docker Compose 로그
docker compose logs ollama
```

**문제**: 컨테이너가 시작되지 않음

```bash
# 로그 확인
docker logs coding-agent
docker logs ollama

# 컨테이너 재시작
docker compose restart

# 완전 재빌드
docker compose down
docker compose build --no-cache
docker compose up -d
```

### 7.4. Ollama 관련

**문제**: 모델 다운로드 실패

```bash
# 디스크 공간 확인
df -h

# Ollama 재시작
docker restart ollama

# 수동 다운로드
docker exec -it ollama bash
ollama pull qwen2.5-coder:7b
```

**문제**: Ollama 연결 실패

```bash
# Ollama 상태 확인
docker logs ollama

# 네트워크 확인
docker network ls
docker network inspect coding-agent-network

# 포트 확인
curl http://localhost:11434
```

### 7.5. 배포 관련

**문제**: 배포 중 헬스체크 실패

```bash
# 수동 헬스체크
ssh user@server-ip
curl http://localhost:8000/health

# 로그 확인
cd ~/coding-agent-project/deployment
docker compose logs -f coding-agent

# 롤백
make rollback
```

**문제**: rsync 동기화 실패

```bash
# rsync 테스트
rsync -avz --dry-run \
    -e "ssh -p 22" \
    ./ user@server-ip:~/coding-agent-project/

# 권한 확인 (서버)
ls -la ~/coding-agent-project
```

### 7.6. 성능 관련

**문제**: API 응답이 느림

```bash
# Grafana에서 메트릭 확인
# http://server-ip:3000

# CPU/메모리 사용률 확인
docker stats

# 워커 수 조정 (.env)
WORKERS=8
```

**문제**: GPU 메모리 부족

```bash
# GPU 사용률 확인
nvidia-smi

# 모델 크기 줄이기 (더 작은 모델 사용)
MODEL_NAME=qwen2.5-coder:7b
```

---

## 📚 추가 자료

- [FastAPI 공식 문서](https://fastapi.tiangolo.com/)
- [Ollama 공식 문서](https://ollama.ai/docs)
- [Docker 공식 문서](https://docs.docker.com/)
- [Prometheus 공식 문서](https://prometheus.io/docs/)
- [Grafana 공식 문서](https://grafana.com/docs/)

---

## 🆘 지원

문제가 해결되지 않으면:

1. GitHub Issues에서 유사한 문제 검색
2. 새 Issue 생성 (로그 포함)
3. 디버깅 정보 수집:

```bash
# 시스템 정보
uname -a
docker --version
python3 --version

# 컨테이너 상태
docker ps -a

# 로그
docker compose logs --tail=100
```

---

**설정을 완료하셨나요? [README.md](README.md)로 돌아가서 API를 사용해보세요!**
