#!/bin/bash

set -e

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  AI Coding Agent - 로컬 Docker 배포  ${NC}"
echo -e "${GREEN}========================================${NC}"

# 프로젝트 루트 디렉토리
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT/deployment"

# .env 파일 확인
if [ ! -f "../.env" ]; then
    echo -e "${YELLOW}.env 파일 생성 중...${NC}"
    cp ../.env.example ../.env
fi

# 워크스페이스 디렉토리 생성
mkdir -p workspace models

# Docker Compose 실행
echo -e "${YELLOW}Docker Compose 시작 중...${NC}"
docker compose down
docker compose build
docker compose up -d

# 잠시 대기
echo -e "${YELLOW}서비스 초기화 대기 중...${NC}"
sleep 15

# 헬스체크
echo -e "${YELLOW}헬스체크 수행 중...${NC}"
for i in {1..5}; do
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}배포 성공!${NC}"
        echo ""
        echo "서비스 URL:"
        echo "  - API: http://localhost:8000"
        echo "  - Docs: http://localhost:8000/docs"
        echo "  - Grafana: http://localhost:3000 (admin / admin123)"
        echo "  - Prometheus: http://localhost:9090"
        echo ""
        echo "Ollama 모델 다운로드:"
        echo "  docker exec ollama ollama pull qwen2.5-coder:7b"
        exit 0
    fi
    echo "시도 $i/5..."
    sleep 5
done

echo -e "${YELLOW}헬스체크 실패. 로그를 확인하세요:${NC}"
echo "docker compose logs -f coding-agent"
