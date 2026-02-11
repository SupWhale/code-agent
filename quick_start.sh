#!/bin/bash

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

clear
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  AI Coding Agent - 빠른 시작 가이드  ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 프로젝트 루트 디렉토리
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# 1. 환경 확인
echo -e "${BLUE}[1/9] 환경 확인 중...${NC}"

# Python 확인
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}오류: Python 3가 설치되어 있지 않습니다.${NC}"
    exit 1
fi
echo "✓ Python: $(python3 --version)"

# Git 확인
if ! command -v git &> /dev/null; then
    echo -e "${RED}오류: Git이 설치되어 있지 않습니다.${NC}"
    exit 1
fi
echo "✓ Git: $(git --version)"

# Docker 확인
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}경고: Docker가 설치되어 있지 않습니다.${NC}"
    echo "Docker 설치: https://docs.docker.com/get-docker/"
else
    echo "✓ Docker: $(docker --version)"
fi

echo ""

# 2. 서버 정보 입력
echo -e "${BLUE}[2/9] 서버 정보 입력${NC}"
echo "배포할 Linux 서버 정보를 입력하세요."
echo ""

if [ -f ".env.deploy" ]; then
    echo -e "${YELLOW}.env.deploy 파일이 이미 존재합니다.${NC}"
    read -p "새로 설정하시겠습니까? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "기존 설정을 사용합니다."
        source .env.deploy
    else
        # 새로 입력
        read -p "서버 IP 주소: " SERVER_HOST
        read -p "서버 사용자명 (기본: supwhale): " SERVER_USER
        SERVER_USER=${SERVER_USER:-supwhale}
        read -p "SSH 포트 (기본: 22): " SERVER_PORT
        SERVER_PORT=${SERVER_PORT:-22}
        read -p "서버 프로젝트 경로 (기본: /home/${SERVER_USER}/coding-agent-project): " SERVER_PATH
        SERVER_PATH=${SERVER_PATH:-/home/${SERVER_USER}/coding-agent-project}

        # .env.deploy 생성
        cat > .env.deploy << EOF
# 서버 정보
SERVER_HOST=${SERVER_HOST}
SERVER_USER=${SERVER_USER}
SERVER_PORT=${SERVER_PORT}
SERVER_PATH=${SERVER_PATH}

# 배포 설정
SKIP_TESTS=false
BACKUP_BEFORE_DEPLOY=true

# Git 설정
GIT_REMOTE=origin
GIT_BRANCH=main
EOF
        echo -e "${GREEN}.env.deploy 파일이 생성되었습니다.${NC}"
    fi
else
    read -p "서버 IP 주소: " SERVER_HOST
    read -p "서버 사용자명 (기본: supwhale): " SERVER_USER
    SERVER_USER=${SERVER_USER:-supwhale}
    read -p "SSH 포트 (기본: 22): " SERVER_PORT
    SERVER_PORT=${SERVER_PORT:-22}
    read -p "서버 프로젝트 경로 (기본: /home/${SERVER_USER}/coding-agent-project): " SERVER_PATH
    SERVER_PATH=${SERVER_PATH:-/home/${SERVER_USER}/coding-agent-project}

    # .env.deploy 생성
    cat > .env.deploy << EOF
# 서버 정보
SERVER_HOST=${SERVER_HOST}
SERVER_USER=${SERVER_USER}
SERVER_PORT=${SERVER_PORT}
SERVER_PATH=${SERVER_PATH}

# 배포 설정
SKIP_TESTS=false
BACKUP_BEFORE_DEPLOY=true

# Git 설정
GIT_REMOTE=origin
GIT_BRANCH=main
EOF
    echo -e "${GREEN}.env.deploy 파일이 생성되었습니다.${NC}"
fi

echo ""

# 3. .env 파일 생성
echo -e "${BLUE}[3/9] 환경 변수 파일 생성${NC}"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${GREEN}.env 파일이 생성되었습니다.${NC}"
else
    echo ".env 파일이 이미 존재합니다."
fi

echo ""

# 4. 가상환경 설정
echo -e "${BLUE}[4/9] Python 가상환경 설정${NC}"
if [ ! -d "venv" ]; then
    echo "가상환경 생성 중..."
    python3 -m venv venv
    echo -e "${GREEN}가상환경이 생성되었습니다.${NC}"
else
    echo "가상환경이 이미 존재합니다."
fi

# 가상환경 활성화
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
fi

echo ""

# 5. 의존성 설치
echo -e "${BLUE}[5/9] Python 의존성 설치${NC}"
pip install -q -r requirements-dev.txt
echo -e "${GREEN}의존성 설치가 완료되었습니다.${NC}"

echo ""

# 6. SSH 연결 테스트
echo -e "${BLUE}[6/9] SSH 연결 테스트${NC}"
if ssh -o ConnectTimeout=5 -p "${SERVER_PORT}" "${SERVER_USER}@${SERVER_HOST}" "echo 'SSH 연결 성공'" 2>/dev/null; then
    echo -e "${GREEN}✓ SSH 연결 성공${NC}"
else
    echo -e "${YELLOW}⚠ SSH 연결 실패${NC}"
    echo "SSH 키를 설정하지 않았다면 다음을 실행하세요:"
    echo "  ssh-copy-id -p ${SERVER_PORT} ${SERVER_USER}@${SERVER_HOST}"
fi

echo ""

# 7. SSH config 설정
echo -e "${BLUE}[7/9] SSH 설정${NC}"
SSH_CONFIG="$HOME/.ssh/config"
if [ -f "$SSH_CONFIG" ]; then
    if grep -q "Host coding-agent-server" "$SSH_CONFIG"; then
        echo "SSH config에 이미 설정되어 있습니다."
    else
        read -p "SSH config에 별칭을 추가하시겠습니까? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            cat >> "$SSH_CONFIG" << EOF

# AI Coding Agent Server
Host coding-agent-server
    HostName ${SERVER_HOST}
    User ${SERVER_USER}
    Port ${SERVER_PORT}
EOF
            echo -e "${GREEN}SSH config에 'coding-agent-server' 별칭이 추가되었습니다.${NC}"
            echo "이제 'ssh coding-agent-server'로 접속할 수 있습니다."
        fi
    fi
fi

echo ""

# 8. Git 초기화
echo -e "${BLUE}[8/9] Git 저장소 초기화${NC}"
if [ ! -d ".git" ]; then
    read -p "Git 저장소를 초기화하시겠습니까? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git init
        git add .
        git commit -m "Initial commit"
        echo -e "${GREEN}Git 저장소가 초기화되었습니다.${NC}"
    fi
else
    echo "Git 저장소가 이미 초기화되어 있습니다."
fi

echo ""

# 9. 완료
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  설정이 완료되었습니다!  ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}다음 단계:${NC}"
echo ""
echo "1. 개발 서버 시작:"
echo "   ${YELLOW}make dev${NC}"
echo "   또는"
echo "   ${YELLOW}bash scripts/dev.sh${NC}"
echo ""
echo "2. 로컬에서 Docker로 테스트:"
echo "   ${YELLOW}make deploy-local${NC}"
echo ""
echo "3. 서버에 배포:"
echo "   ${YELLOW}make deploy-server${NC}"
echo ""
echo "4. 도움말:"
echo "   ${YELLOW}make help${NC}"
echo ""
echo -e "${BLUE}유용한 명령어:${NC}"
echo "  - 테스트 실행: ${YELLOW}make test${NC}"
echo "  - 코드 포맷팅: ${YELLOW}make format${NC}"
echo "  - 서버 SSH: ${YELLOW}make ssh${NC} 또는 ${YELLOW}ssh coding-agent-server${NC}"
echo "  - 서버 로그: ${YELLOW}make logs-server${NC}"
echo ""
echo -e "${GREEN}행복한 코딩 되세요! 🚀${NC}"
