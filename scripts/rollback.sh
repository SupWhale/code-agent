#!/bin/bash
# 서버에 배포된 coding-agent 이미지를 이전 태그(또는 직접 지정한 태그)로 되돌린다.
# 파일시스템을 건드리지 않고 이미지 태그만 바꿔 재기동하므로 git reset/rm -rf 방식보다 안전하다.
# scripts/deploy_to_server.sh가 배포마다 deployment/.current_tag, .previous_tag를 기록해둔다.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}  AI Coding Agent - 롤백 스크립트  ${NC}"
echo -e "${YELLOW}========================================${NC}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [ ! -f ".env.deploy" ]; then
    echo -e "${RED}오류: .env.deploy 파일을 찾을 수 없습니다.${NC}"
    echo "cp .env.deploy.example .env.deploy 로 복사한 뒤 SERVER_HOST/SERVER_USER/SERVER_PATH를 채우세요."
    exit 1
fi

source .env.deploy

if [ -z "$SERVER_HOST" ] || [ -z "$SERVER_USER" ] || [ -z "$SERVER_PATH" ]; then
    echo -e "${RED}오류: 필수 환경 변수가 설정되지 않았습니다.${NC}"
    exit 1
fi

echo "롤백 방법을 선택하세요:"
echo "1) 이전 태그로 롤백 (직전 배포 시점)"
echo "2) 특정 태그(커밋 SHA) 직접 지정"
read -p "선택 (1 or 2): " -n 1 -r
echo

if [[ $REPLY == "1" ]]; then
    TAG_SOURCE='cat .previous_tag'
elif [[ $REPLY == "2" ]]; then
    read -p "롤백할 이미지 태그(커밋 SHA)를 입력하세요: " TARGET_TAG
    if [ -z "$TARGET_TAG" ]; then
        echo -e "${RED}태그를 입력하지 않았습니다.${NC}"
        exit 1
    fi
    TAG_SOURCE="echo $TARGET_TAG"
else
    echo -e "${RED}잘못된 선택입니다.${NC}"
    exit 1
fi

echo -e "${YELLOW}서버에서 롤백 실행 중...${NC}"
ssh -p "${SERVER_PORT:-22}" "${SERVER_USER}@${SERVER_HOST}" "
    set -e
    cd '${SERVER_PATH}/deployment'

    if [ ! -f '.previous_tag' ] && [ '$REPLY' == '1' ]; then
        echo '롤백할 이전 태그 기록이 없습니다 (.previous_tag 없음). scripts/deploy_to_server.sh로 최소 1회 배포된 이력이 필요합니다.'
        exit 1
    fi

    ROLLBACK_TAG=\$($TAG_SOURCE)
    echo \"롤백 대상 태그: \$ROLLBACK_TAG\"

    IMAGE_TAG=\"\$ROLLBACK_TAG\" docker compose --env-file ../.env pull coding-agent
    IMAGE_TAG=\"\$ROLLBACK_TAG\" docker compose --env-file ../.env up -d

    # 현재/이전 태그 갱신 (롤백도 하나의 배포로 취급)
    if [ -f '.current_tag' ]; then
        cp .current_tag .previous_tag
    fi
    echo \"\$ROLLBACK_TAG\" > .current_tag

    sleep 10
"

echo -e "${YELLOW}헬스체크 수행 중...${NC}"
for i in {1..5}; do
    if ssh -p "${SERVER_PORT:-22}" "${SERVER_USER}@${SERVER_HOST}" "
        curl -f http://localhost:8000/health > /dev/null 2>&1
    "; then
        echo -e "${GREEN}롤백 성공!${NC}"
        exit 0
    fi
    echo "시도 $i/5..."
    sleep 5
done

echo -e "${RED}롤백 후 헬스체크 실패! 서버 로그를 직접 확인하세요.${NC}"
exit 1
