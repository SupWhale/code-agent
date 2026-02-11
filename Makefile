.PHONY: help setup dev dev-docker test lint format deploy-server deploy-local rollback ssh logs-server clean

help:
	@echo "AI Coding Agent - Makefile 명령어"
	@echo ""
	@echo "사용 가능한 명령어:"
	@echo "  make help          - 도움말 출력"
	@echo "  make setup         - 초기 설정 (가상환경, 의존성, .env)"
	@echo "  make dev           - 개발 서버 시작"
	@echo "  make dev-docker    - Docker 개발 환경 시작"
	@echo "  make test          - 테스트 실행"
	@echo "  make lint          - 코드 린팅 (flake8 + mypy)"
	@echo "  make format        - 코드 포맷팅 (black + isort)"
	@echo "  make deploy-server - 서버에 배포"
	@echo "  make deploy-local  - 로컬 Docker 배포"
	@echo "  make rollback      - 롤백 실행"
	@echo "  make ssh           - 서버 SSH 접속"
	@echo "  make logs-server   - 서버 로그 확인"
	@echo "  make clean         - 임시 파일 정리"

setup:
	@echo "초기 설정 중..."
	@if [ ! -d "venv" ]; then \
		echo "가상환경 생성 중..."; \
		python3 -m venv venv; \
	fi
	@echo "의존성 설치 중..."
	@if [ -f "venv/bin/activate" ]; then \
		. venv/bin/activate && pip install -r requirements-dev.txt; \
	elif [ -f "venv/Scripts/activate" ]; then \
		. venv/Scripts/activate && pip install -r requirements-dev.txt; \
	fi
	@if [ ! -f ".env" ]; then \
		echo ".env 파일 생성 중..."; \
		cp .env.example .env; \
	fi
	@echo "설정 완료!"

dev:
	@bash scripts/dev.sh

dev-docker:
	@echo "Docker 개발 환경 시작 중..."
	@cd docker && docker-compose -f docker-compose.dev.yml up --build

test:
	@echo "테스트 실행 중..."
	@if [ -f "venv/bin/activate" ]; then \
		. venv/bin/activate && python -m pytest tests/ -v; \
	elif [ -f "venv/Scripts/activate" ]; then \
		. venv/Scripts/activate && python -m pytest tests/ -v; \
	fi

lint:
	@echo "린팅 실행 중..."
	@if [ -f "venv/bin/activate" ]; then \
		. venv/bin/activate && flake8 src/ tests/ --max-line-length=120 && mypy src/; \
	elif [ -f "venv/Scripts/activate" ]; then \
		. venv/Scripts/activate && flake8 src/ tests/ --max-line-length=120 && mypy src/; \
	fi

format:
	@echo "코드 포맷팅 중..."
	@if [ -f "venv/bin/activate" ]; then \
		. venv/bin/activate && black src/ tests/ && isort src/ tests/; \
	elif [ -f "venv/Scripts/activate" ]; then \
		. venv/Scripts/activate && black src/ tests/ && isort src/ tests/; \
	fi

deploy-server:
	@bash scripts/deploy_to_server.sh

deploy-local:
	@bash scripts/deploy.sh

rollback:
	@bash scripts/rollback.sh

ssh:
	@if [ -f ".env.deploy" ]; then \
		. .env.deploy && ssh -p $${SERVER_PORT:-22} $${SERVER_USER}@$${SERVER_HOST}; \
	else \
		echo "오류: .env.deploy 파일이 없습니다."; \
	fi

logs-server:
	@if [ -f ".env.deploy" ]; then \
		. .env.deploy && ssh -p $${SERVER_PORT:-22} $${SERVER_USER}@$${SERVER_HOST} "cd $${SERVER_PATH}/deployment && docker-compose logs -f coding-agent"; \
	else \
		echo "오류: .env.deploy 파일이 없습니다."; \
	fi

clean:
	@echo "임시 파일 정리 중..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf htmlcov/ .coverage 2>/dev/null || true
	@echo "정리 완료!"
