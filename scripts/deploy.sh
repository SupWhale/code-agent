#!/bin/bash

set -e

# 색상 정의
RED='\033[0;31m'
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

# alertmanager 설정 확인 (웹훅 URL이 실제 값이 아니면 알림이 전송되지 않음 — .env처럼 커밋되지 않음)
if [ ! -f "alertmanager/alertmanager.yml" ]; then
    echo -e "${YELLOW}alertmanager.yml 생성 중 (webhook URL을 직접 채워주세요)...${NC}"
    cp alertmanager/alertmanager.yml.example alertmanager/alertmanager.yml
fi

# DOMAIN 미설정 시 LAN/로컬 테스트로 간주해 nginx/certbot(TLS)는 제외하고 기동한다.
# docker compose는 명령과 무관하게 파일 전체를 먼저 해석하므로, DOMAIN이 비어 있으면
# coding-agent만 띄우려 해도 실패한다 — 그래서 placeholder 값이라도 .env에 채워둔다.
# (실제 인증서는 발급되지 않으며, 공개 도메인이 생기면 scripts/init_letsencrypt.sh로 TLS를 별도로 붙이면 된다)
LAN_PLACEHOLDER_DOMAIN="lan-test.local"
CURRENT_DOMAIN=$(grep -E '^DOMAIN=' ../.env 2>/dev/null | head -1 | cut -d= -f2-)

SERVICES="ollama coding-agent prometheus alertmanager grafana node-exporter cadvisor"
if [ -n "$CURRENT_DOMAIN" ] && [ "$CURRENT_DOMAIN" != "$LAN_PLACEHOLDER_DOMAIN" ]; then
    echo -e "${GREEN}DOMAIN 설정 확인됨 — nginx/certbot 포함 전체 스택을 기동합니다.${NC}"
    SERVICES="$SERVICES nginx certbot"
else
    echo -e "${YELLOW}DOMAIN이 설정되어 있지 않아 LAN/로컬 테스트용으로 nginx/certbot(TLS)은 제외하고 기동합니다.${NC}"
    echo -e "${YELLOW}(공개 도메인이 생기면 .env의 DOMAIN을 실제 도메인으로 바꾸고 scripts/init_letsencrypt.sh를 실행하세요)${NC}"
    if grep -qE '^DOMAIN=' ../.env 2>/dev/null; then
        sed -i.bak "s/^DOMAIN=.*/DOMAIN=${LAN_PLACEHOLDER_DOMAIN}/" ../.env && rm -f ../.env.bak
    else
        echo "DOMAIN=${LAN_PLACEHOLDER_DOMAIN}" >> ../.env
    fi
fi

# 워크스페이스 디렉토리 생성 (컨테이너가 non-root(uid 1000)로 도므로 호스트 바인드 마운트도
# 쓰기 가능해야 한다). 예전에 root로 실행되던 컨테이너가 만든 workspace/.sessions는
# 일반 사용자 권한의 chmod로 열 수 없으므로(소유자만 변경 가능), 비어 있지 않다면
# 통째로 지우고 다시 만든다 — 세션 데이터는 어차피 임시 작업공간이라 지워도 안전하다.
mkdir -p workspace models
if [ -d "workspace/.sessions" ] && ! rm -rf workspace/.sessions 2>/dev/null; then
    echo -e "${RED}workspace/.sessions가 예전 root 소유라 일반 권한으로 정리할 수 없습니다.${NC}"
    echo -e "${RED}서버에서 다음을 한 번 실행한 뒤 다시 시도하세요:${NC}"
    echo -e "${RED}  sudo rm -rf $(pwd)/workspace/.sessions${NC}"
    exit 1
fi
chmod -R 777 workspace 2>/dev/null || true

# workspace 자체가 예전 root 소유라 위 chmod가 조용히 실패했을 수 있으니 실제로
# 쓰기 가능한지 확인한다 — 아니면 컨테이너가 기동 직후 크래시 루프에 빠지므로 여기서 미리 잡는다.
if ! touch "workspace/.write_test" 2>/dev/null; then
    echo -e "${RED}workspace 디렉토리에 쓰기 권한이 없습니다 (예전 root 소유로 추정).${NC}"
    echo -e "${RED}서버에서 다음을 한 번 실행한 뒤 다시 시도하세요:${NC}"
    echo -e "${RED}  sudo chmod -R 777 $(pwd)/workspace${NC}"
    exit 1
fi
rm -f "workspace/.write_test"

# Docker Compose 실행 (compose 파일이 deployment/에 있으므로 상위 .env를 명시적으로 지정)
echo -e "${YELLOW}Docker Compose 시작 중...${NC}"
docker compose --env-file ../.env down
docker compose --env-file ../.env build $SERVICES
docker compose --env-file ../.env up -d $SERVICES

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
        echo "  - Grafana: http://localhost:3000 (admin / .env의 GRAFANA_ADMIN_PASSWORD 값)"
        echo "  - Prometheus: http://localhost:9090"
        echo "  - Alertmanager: http://localhost:9093"
        if [[ "$SERVICES" != *"nginx"* ]]; then
            echo "  (nginx/certbot 미기동 — TLS는 DOMAIN 설정 후 scripts/init_letsencrypt.sh로 별도 진행)"
        fi
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
