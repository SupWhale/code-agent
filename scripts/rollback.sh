#!/bin/bash

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}  AI Coding Agent - 롤백 스크립트  ${NC}"
echo -e "${YELLOW}========================================${NC}"

# 프로젝트 루트 디렉토리
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# .env.deploy 파일 로드
if [ ! -f ".env.deploy" ]; then
    echo -e "${RED}오류: .env.deploy 파일을 찾을 수 없습니다.${NC}"
    exit 1
fi

source .env.deploy

# Git 롤백인지 백업 롤백인지 선택
echo "롤백 방법을 선택하세요:"
echo "1) Git HEAD~1로 롤백"
echo "2) 백업 파일로 롤백"
read -p "선택 (1 or 2): " -n 1 -r
echo

if [[ $REPLY == "1" ]]; then
    # Git 롤백
    echo -e "${YELLOW}Git HEAD~1로 롤백 중...${NC}"

    ssh -p "${SERVER_PORT:-22}" "${SERVER_USER}@${SERVER_HOST}" "
        set -e
        cd '${SERVER_PATH}'

        # 현재 컨테이너 중지
        cd deployment
        docker-compose down

        # Git 롤백
        cd ..
        git reset --hard HEAD~1

        # 컨테이너 재시작
        cd deployment
        docker-compose build coding-agent
        docker-compose up -d

        sleep 10
    "

elif [[ $REPLY == "2" ]]; then
    # 백업 롤백
    echo -e "${YELLOW}백업 파일로 롤백 중...${NC}"

    ssh -p "${SERVER_PORT:-22}" "${SERVER_USER}@${SERVER_HOST}" "
        set -e

        # 백업 목록 조회
        BACKUP_DIR='${SERVER_PATH}/../backup'
        BACKUPS=\$(ls -t \$BACKUP_DIR/coding-agent-backup-*.tar.gz 2>/dev/null)

        if [ -z \"\$BACKUPS\" ]; then
            echo '백업 파일이 없습니다.'
            exit 1
        fi

        echo '사용 가능한 백업:'
        echo \"\$BACKUPS\" | nl

        # 최신 백업 사용
        LATEST_BACKUP=\$(echo \"\$BACKUPS\" | head -1)
        echo \"복원할 백업: \$LATEST_BACKUP\"

        # 현재 컨테이너 중지
        cd '${SERVER_PATH}/deployment'
        docker-compose down

        # 백업 복원
        cd '${SERVER_PATH}'
        rm -rf src/ docker/ deployment/ scripts/
        tar -xzf \$LATEST_BACKUP

        # 컨테이너 재시작
        cd deployment
        docker-compose build coding-agent
        docker-compose up -d

        sleep 10
    "
else
    echo -e "${RED}잘못된 선택입니다.${NC}"
    exit 1
fi

# 헬스체크
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

echo -e "${RED}롤백 후 헬스체크 실패!${NC}"
exit 1
