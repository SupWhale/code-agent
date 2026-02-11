#!/bin/bash

set -e

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  AI Coding Agent - 개발 서버 시작  ${NC}"
echo -e "${GREEN}========================================${NC}"

# 프로젝트 루트 디렉토리
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# 가상환경 확인/생성
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}가상환경 생성 중...${NC}"
    python3 -m venv venv
fi

# 가상환경 활성화
echo -e "${YELLOW}가상환경 활성화 중...${NC}"
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
else
    echo "가상환경 활성화 파일을 찾을 수 없습니다."
    exit 1
fi

# 의존성 설치
if [ ! -f "venv/.installed" ]; then
    echo -e "${YELLOW}의존성 설치 중...${NC}"
    pip install -r requirements-dev.txt
    touch venv/.installed
fi

# .env 파일 로드
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
else
    echo -e "${YELLOW}경고: .env 파일이 없습니다. .env.example을 복사합니다.${NC}"
    cp .env.example .env
    export $(cat .env | grep -v '^#' | xargs)
fi

# 개발 서버 시작
echo -e "${GREEN}개발 서버 시작 중...${NC}"
echo "URL: http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
echo ""
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
