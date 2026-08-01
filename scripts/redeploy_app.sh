#!/bin/bash
# LAN 서버에서 coding-agent만 최신 커밋으로 재배포한다 (ollama/모니터링 스택은 안 건드림).
#
# scripts/deploy.sh는 매번 docker compose down으로 전체 스택(ollama 포함)을 내렸다
# 올린다 — 코드 한 줄만 바뀐 일상적인 재배포에도 Ollama가 모델을 다시 로드해야 하고
# Grafana/Prometheus도 잠깐 끊긴다. 이 스크립트는 coding-agent 컨테이너만 재빌드/재기동한다.
# (실행 중이던 에이전트 태스크가 끊기는 건 coding-agent 자체가 재시작되는 이상 어느
# 방법을 쓰든 피할 수 없다 — TaskManager 상태가 프로세스 메모리에 있음.)
#
# scripts/start_nginx_selfsigned.sh(또는 실제 nginx)로 nginx를 같이 띄워둔 경우 주의:
# coding-agent를 재기동하면 컨테이너의 내부 IP가 바뀌는데, nginx는 그 IP를 자기
# 기동 시점에 딱 한 번만 resolve해서 캐시해두기 때문에 재시작 전까지는 계속 옛날
# 죽은 IP로 요청을 보내 502 Bad Gateway가 난다(docs/infrastructure.md 3.7절 — 로컬
# 재현으로 실측 확인됨). 그래서 이 스크립트는 nginx가 떠 있으면 자동으로 같이
# 재시작해서 새 IP를 다시 resolve하게 한다.
#
# 이 서버(레포가 실제로 체크아웃된 곳)에서 직접 실행 (git pull까지 포함):
#   ./scripts/redeploy_app.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [ -n "$(git status --porcelain)" ]; then
    echo -e "${YELLOW}경고: 커밋되지 않은 변경사항이 있습니다 — git pull과 충돌할 수 있습니다:${NC}"
    git status --short
    read -p "그래도 계속하시겠습니까? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "${YELLOW}git pull 중...${NC}"
git pull

cd "$PROJECT_ROOT/deployment"
COMPOSE="docker compose --env-file ../.env"

echo -e "${YELLOW}coding-agent 재빌드 중...${NC}"
$COMPOSE build coding-agent

echo -e "${YELLOW}coding-agent 재기동 중...${NC}"
$COMPOSE up -d coding-agent

if $COMPOSE ps --status running --services | grep -qx "nginx"; then
    echo -e "${YELLOW}nginx가 떠 있어 같이 재시작합니다 (coding-agent의 새 내부 IP를 다시 resolve하도록)...${NC}"
    $COMPOSE restart nginx
else
    echo -e "${YELLOW}nginx는 떠 있지 않아 건너뜁니다.${NC}"
fi

echo ""
echo -e "${GREEN}재배포 완료.${NC}"
echo "헬스체크: curl -f http://localhost:8000/health"
