#!/bin/bash
# LAN 테스트 배포에서 nginx만 추가로 띄운다 (실제 도메인/Let's Encrypt 인증서 없이).
#
# scripts/deploy.sh는 .env의 DOMAIN이 비어있거나 placeholder(lan-test.local)면
# nginx/certbot을 SERVICES 목록에서 아예 빼고 기동한다 — LAN 환경에 TLS를 강제하지
# 않기 위함이다. 그런데 nginx의 실제 리버스 프록시 동작(타임아웃, 인증 헤더 전달,
# location 라우팅 등)을 LAN에서 검증하려면 nginx가 최소한 기동은 되어야 하는데,
# nginx.conf.template이 인증서 파일(/etc/letsencrypt/live/${DOMAIN}/...)을 하드코딩하고
# 있어서 그마저도 없으면 443을 아예 못 연다. 실제 Let's Encrypt 인증서는 공인 도메인과
# 80/443 외부 도달성이 필요해 LAN에서는 발급받을 수 없으므로, 자체 서명(self-signed)
# 더미 인증서로 nginx만 띄운다.
#
# scripts/init_letsencrypt.sh와의 차이:
#   - init_letsencrypt.sh: 더미 인증서 → 실제 Let's Encrypt 인증서로 교체까지 진행
#     (공인 도메인 + 80/443 외부 도달성 필수)
#   - 이 스크립트: 더미 인증서인 채로 유지 (LAN 테스트 전용). 클라이언트는 인증서
#     검증을 꺼야 한다 (예: curl -k, 브라우저 경고 무시).
#
# 사전 준비: scripts/deploy.sh를 한 번 실행해 .env에 DOMAIN이 채워져 있어야 한다
#            (실제 도메인일 필요 없음 — placeholder라도 상관없음).
#
# 사용법: ./scripts/start_nginx_selfsigned.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT/deployment"

if [ ! -f "../.env" ]; then
    echo -e "${RED}오류: ../.env 파일이 없습니다. 먼저 scripts/deploy.sh를 한 번 실행하세요.${NC}"
    exit 1
fi

set -a
source ../.env
set +a

if [ -z "$DOMAIN" ]; then
    echo -e "${RED}오류: .env에 DOMAIN이 비어 있습니다. scripts/deploy.sh를 먼저 실행해${NC}"
    echo -e "${RED}placeholder 값이라도 채우거나, 직접 DOMAIN=lan-test.local 같은 값을 넣으세요.${NC}"
    exit 1
fi

COMPOSE="docker compose --env-file ../.env"

# nginx는 upstream(coding-agent:8000) 호스트명을 기동 시점에 딱 한 번만 정적으로
# resolve한다 — coding-agent가 아직 안 떠 있으면 "host not found in upstream" emerg
# 에러로 계속 crash-loop에 빠지고, 나중에 coding-agent를 띄워도 nginx를 재시작하기
# 전까진 저절로 복구되지 않는다(실측 확인됨). 그래서 미리 확인하고 명확히 실패시킨다.
if ! $COMPOSE ps --status running --services | grep -qx "coding-agent"; then
    echo -e "${RED}오류: coding-agent가 실행 중이 아닙니다.${NC}"
    echo -e "${RED}nginx는 coding-agent 호스트명을 기동 시점에 한 번만 resolve하므로, coding-agent가${NC}"
    echo -e "${RED}먼저 떠 있어야 합니다. scripts/deploy.sh를 먼저 실행하세요.${NC}"
    exit 1
fi

# 이미 인증서가 있으면(진짜 Let's Encrypt 인증서일 수도 있음) 덮어쓰지 않는다 —
# init_letsencrypt.sh로 실제 인증서를 발급받은 뒤 실수로 이 스크립트를 다시 돌려
# 자체 서명으로 되돌리는 사고를 방지.
echo -e "${YELLOW}기존 인증서 존재 여부 확인 중...${NC}"
if $COMPOSE run --rm --entrypoint "sh -c \"test -f /etc/letsencrypt/live/$DOMAIN/fullchain.pem\"" certbot >/dev/null 2>&1; then
    echo -e "${YELLOW}이미 인증서가 존재합니다(진짜 Let's Encrypt 인증서일 수 있음) — 새로 만들지 않고 넘어갑니다.${NC}"
else
    echo -e "${YELLOW}자체 서명 더미 인증서 생성 중 (DOMAIN=$DOMAIN)...${NC}"
    $COMPOSE run --rm --entrypoint "sh -c \"mkdir -p /etc/letsencrypt/live/$DOMAIN && \
      openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
        -keyout /etc/letsencrypt/live/$DOMAIN/privkey.pem \
        -out /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
        -subj '/CN=$DOMAIN'\"" certbot
fi

echo -e "${YELLOW}nginx 기동 중...${NC}"
$COMPOSE up -d nginx

echo ""
echo -e "${GREEN}nginx가 자체 서명 인증서로 떠 있습니다.${NC}"
echo "  - https://$DOMAIN/health (또는 서버 IP) — 인증서가 자체 서명이라 클라이언트가"
echo "    인증서 검증을 꺼야 합니다 (curl -k, 브라우저는 경고 무시)"
echo "  - 실제 공인 도메인이 생기면 scripts/init_letsencrypt.sh로 진짜 인증서로 교체하세요"
echo "  - 이 인증서는 자체 서명이라 certbot 자동 갱신 루프('docker compose up -d certbot')는"
echo "    필요 없습니다 (갱신해봤자 여전히 신뢰 안 되는 인증서일 뿐입니다)"
