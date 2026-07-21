#!/bin/bash
# Let's Encrypt 인증서 최초 발급 (더미 인증서 부트스트랩 + webroot 방식)
#
# nginx는 443에서 실제 인증서 파일이 있어야 기동되므로, 먼저 더미 인증서로
# nginx를 띄운 뒤 80번 포트의 ACME 챌린지 경로로 실제 인증서를 발급받고 재시작한다.
#
# 사전 준비:
#   - .env에 DOMAIN, LETSENCRYPT_EMAIL 설정
#   - DOMAIN이 이 서버의 공인 IP를 가리키는 DNS A 레코드가 이미 전파되어 있어야 함
#   - 80/443 포트가 외부에서 도달 가능해야 함 (방화벽/보안그룹 확인)
#
# 사용법: ./scripts/init_letsencrypt.sh

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT/deployment"

if [ ! -f "../.env" ]; then
    echo "오류: ../.env 파일이 없습니다. .env.example을 복사해 값을 채우세요."
    exit 1
fi

set -a
source ../.env
set +a

if [ -z "$DOMAIN" ] || [ -z "$LETSENCRYPT_EMAIL" ]; then
    echo "오류: .env에 DOMAIN, LETSENCRYPT_EMAIL을 설정하세요."
    exit 1
fi

COMPOSE="docker compose --env-file ../.env"

echo "1/5: 더미 인증서 생성 중 (nginx가 최초 기동할 수 있도록)..."
$COMPOSE run --rm --entrypoint "sh -c \"mkdir -p /etc/letsencrypt/live/$DOMAIN && \
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout /etc/letsencrypt/live/$DOMAIN/privkey.pem \
    -out /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
    -subj '/CN=localhost'\"" certbot

echo "2/5: nginx 기동..."
$COMPOSE up -d nginx

echo "3/5: 더미 인증서 삭제..."
$COMPOSE run --rm --entrypoint "sh -c \"rm -rf /etc/letsencrypt/live/$DOMAIN /etc/letsencrypt/archive/$DOMAIN /etc/letsencrypt/renewal/$DOMAIN.conf\"" certbot

echo "4/5: 실제 인증서 발급 요청 중..."
$COMPOSE run --rm --entrypoint "certbot certonly --webroot -w /var/www/certbot \
    --email $LETSENCRYPT_EMAIL -d $DOMAIN \
    --rsa-key-size 4096 --agree-tos --non-interactive" certbot

echo "5/5: nginx 재시작 (실제 인증서 반영)..."
$COMPOSE restart nginx

echo ""
echo "완료. https://$DOMAIN 으로 접속해 확인하세요."
echo "certbot 컨테이너가 12시간마다 자동으로 갱신을 시도합니다 (docker compose up -d certbot)."
