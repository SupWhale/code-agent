#!/bin/bash

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  AI Coding Agent - 서버 배포 스크립트  ${NC}"
echo -e "${GREEN}========================================${NC}"

# 프로젝트 루트 디렉토리
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# .env.deploy 파일 로드
if [ ! -f ".env.deploy" ]; then
    echo -e "${RED}오류: .env.deploy 파일을 찾을 수 없습니다.${NC}"
    echo "cp .env.deploy.example .env.deploy 로 복사한 뒤 SERVER_HOST/SERVER_USER/SERVER_PATH를 채우세요."
    exit 1
fi

source .env.deploy

# 환경 변수 확인
if [ -z "$SERVER_HOST" ] || [ -z "$SERVER_USER" ] || [ -z "$SERVER_PATH" ]; then
    echo -e "${RED}오류: 필수 환경 변수가 설정되지 않았습니다.${NC}"
    exit 1
fi

# 로컬 테스트 실행 (선택적)
if [ "${SKIP_TESTS:-false}" != "true" ]; then
    echo -e "${YELLOW}로컬 테스트 실행 중...${NC}"
    if [ -d "venv" ]; then
        source venv/bin/activate || source venv/Scripts/activate
        python -m pytest tests/ -v || {
            echo -e "${RED}테스트 실패! 배포를 중단합니다.${NC}"
            exit 1
        }
    else
        echo -e "${YELLOW}경고: venv를 찾을 수 없습니다. 테스트를 건너뜁니다.${NC}"
    fi
fi

# Git 상태 확인 — GHCR 이미지는 GitHub Actions가 push된 커밋 기준으로만 빌드하므로
# 커밋되지 않은/푸시되지 않은 변경사항은 배포되는 이미지에 반영되지 않는다.
if [ -d ".git" ]; then
    if [ -n "$(git status --porcelain)" ]; then
        echo -e "${YELLOW}경고: 커밋되지 않은 변경사항이 있습니다. 이 변경사항은 배포될 이미지에 포함되지 않습니다.${NC}"
        git status --short
        read -p "계속하시겠습니까? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

GIT_SHA=$(git rev-parse HEAD)
echo -e "${YELLOW}배포할 이미지 태그: ${GIT_SHA}${NC}"
echo "(GitHub Actions가 이 커밋에 대한 빌드를 이미 완료해 GHCR에 푸시했어야 합니다)"

# SSH 연결 테스트
echo -e "${YELLOW}SSH 연결 테스트 중...${NC}"
ssh -o ConnectTimeout=10 -p "${SERVER_PORT:-22}" "${SERVER_USER}@${SERVER_HOST}" "echo 'SSH 연결 성공'" || {
    echo -e "${RED}SSH 연결 실패!${NC}"
    exit 1
}

# 백업 생성 (선택적)
if [ "${BACKUP_BEFORE_DEPLOY:-true}" == "true" ]; then
    echo -e "${YELLOW}서버에 백업 생성 중...${NC}"
    ssh -p "${SERVER_PORT:-22}" "${SERVER_USER}@${SERVER_HOST}" "
        if [ -d '${SERVER_PATH}' ]; then
            BACKUP_DIR='${SERVER_PATH}/../backup'
            mkdir -p \$BACKUP_DIR
            BACKUP_NAME=\"coding-agent-backup-\$(date +%Y%m%d-%H%M%S).tar.gz\"
            cd '${SERVER_PATH}/..'
            tar -czf \$BACKUP_DIR/\$BACKUP_NAME -C '${SERVER_PATH}' . 2>/dev/null || true
            echo \"백업 생성: \$BACKUP_DIR/\$BACKUP_NAME\"
            # 오래된 백업 삭제 (7일 이상)
            find \$BACKUP_DIR -name 'coding-agent-backup-*.tar.gz' -mtime +7 -delete 2>/dev/null || true
        fi
    "
fi

# 파일 동기화
echo -e "${YELLOW}파일 동기화 중...${NC}"
rsync -avz --progress \
    --exclude 'venv' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.git' \
    --exclude '.pytest_cache' \
    --exclude 'deployment/workspace/*' \
    --exclude 'deployment/models/*' \
    --exclude 'deployment/backup/*' \
    --exclude '.env.local' \
    --exclude 'htmlcov' \
    --exclude '.coverage' \
    -e "ssh -p ${SERVER_PORT:-22}" \
    ./ "${SERVER_USER}@${SERVER_HOST}:${SERVER_PATH}/" || {
    echo -e "${RED}파일 동기화 실패!${NC}"
    exit 1
}

# 서버에서 배포 실행
echo -e "${YELLOW}서버에서 배포 실행 중...${NC}"
ssh -p "${SERVER_PORT:-22}" "${SERVER_USER}@${SERVER_HOST}" "
    set -e
    cd '${SERVER_PATH}/deployment'

    # .env 파일 확인
    if [ ! -f '../.env' ]; then
        echo '경고: .env 파일이 없습니다. .env.example을 복사합니다.'
        cp ../.env.example ../.env
    fi

    # alertmanager 설정 확인
    if [ ! -f 'alertmanager/alertmanager.yml' ]; then
        echo '경고: alertmanager.yml이 없습니다. alertmanager.yml.example을 복사합니다.'
        cp alertmanager/alertmanager.yml.example alertmanager/alertmanager.yml
    fi

    # 롤백용으로 현재 태그를 이전 태그로 보관
    if [ -f '.current_tag' ]; then
        cp .current_tag .previous_tag
    fi
    echo '${GIT_SHA}' > .current_tag

    # GHCR에서 태그된 이미지 pull (서버에서 소스 빌드하지 않음)
    echo '이미지 pull 중 (태그: ${GIT_SHA})...'
    IMAGE_TAG='${GIT_SHA}' docker compose --env-file ../.env pull coding-agent

    # 컨테이너 재시작
    echo '컨테이너 재시작 중...'
    IMAGE_TAG='${GIT_SHA}' docker compose --env-file ../.env up -d

    # 잠시 대기
    sleep 10
"

# 헬스체크
echo -e "${YELLOW}헬스체크 수행 중...${NC}"
MAX_RETRIES=5
RETRY_DELAY=5

for i in $(seq 1 $MAX_RETRIES); do
    echo "시도 $i/$MAX_RETRIES..."

    if ssh -p "${SERVER_PORT:-22}" "${SERVER_USER}@${SERVER_HOST}" "
        curl -f http://localhost:8000/health > /dev/null 2>&1
    "; then
        echo -e "${GREEN}헬스체크 성공!${NC}"
        break
    fi

    if [ $i -eq $MAX_RETRIES ]; then
        echo -e "${RED}헬스체크 실패! 이전 태그로 자동 롤백합니다.${NC}"

        # 롤백 — 이미지 태그만 이전 것으로 되돌린다 (파일시스템을 건드리지 않음)
        ssh -p "${SERVER_PORT:-22}" "${SERVER_USER}@${SERVER_HOST}" "
            set -e
            cd '${SERVER_PATH}/deployment'
            if [ -f '.previous_tag' ]; then
                PREV_TAG=\$(cat .previous_tag)
                echo \"이전 태그로 롤백: \$PREV_TAG\"
                IMAGE_TAG=\"\$PREV_TAG\" docker compose --env-file ../.env pull coding-agent
                IMAGE_TAG=\"\$PREV_TAG\" docker compose --env-file ../.env up -d
                echo \"\$PREV_TAG\" > .current_tag
            else
                echo '이전 태그 기록이 없어 자동 롤백할 수 없습니다. scripts/rollback.sh로 수동 확인하세요.'
            fi
        "

        exit 1
    fi

    echo "대기 중... (${RETRY_DELAY}초)"
    sleep $RETRY_DELAY
done

# 배포 완료
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  배포가 성공적으로 완료되었습니다!  ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "서비스 URL:"
echo "  - API: http://${SERVER_HOST}:8000"
echo "  - Docs: http://${SERVER_HOST}:8000/docs"
echo ""
echo "Grafana/Prometheus/Alertmanager는 호스트에 포트를 게시하지 않습니다 (docs/infrastructure.md 참고)."
echo "확인이 필요하면 서버에 SSH로 접속해 컨테이너 안에서 직접 조회하세요, 예:"
echo "  docker compose --env-file ../.env exec grafana wget -qO- http://localhost:3000/api/health"
echo ""
echo "로그 확인:"
echo "  ssh -p ${SERVER_PORT:-22} ${SERVER_USER}@${SERVER_HOST}"
echo "  cd ${SERVER_PATH}/deployment"
echo "  docker compose --env-file ../.env logs -f coding-agent"
