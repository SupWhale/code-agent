# 프로젝트 루트를 sys.path에 올려 `src` 패키지를 임포트 가능하게 한다.
import os

# src.main은 임포트 시점에 Settings()를 fail-fast로 검증한다. 테스트 실행 시
# API_KEYS 없이도 임포트가 가능하도록 기본값을 개발 모드로 맞춘다.
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("WORKSPACE_PATH", os.path.dirname(os.path.abspath(__file__)))
