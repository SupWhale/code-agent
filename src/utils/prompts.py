"""Prompt file loader

프롬프트 텍스트를 파이썬 소스에 하드코딩하지 않고 저장소의 prompts/ 디렉토리
아래 파일로 분리 관리하기 위한 공용 로더. (시스템 프롬프트처럼 배포 환경마다
경로를 바꿔야 하는 경우는 여기 대신 main.py의 SYSTEM_PROMPT_PATH처럼 별도로
설정 가능한 경로를 쓴다 — 이 로더는 저장소에 고정으로 번들되는 프롬프트용.)
"""

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


@lru_cache(maxsize=None)
def load_prompt(relative_path: str) -> str:
    """prompts/ 디렉토리 기준 상대 경로로 프롬프트 파일을 읽어온다.

    Args:
        relative_path: prompts/ 아래 상대 경로 (예: "generate/analyze_general.txt")

    Returns:
        파일 내용 (양끝 공백 제거)

    Raises:
        FileNotFoundError: 파일이 없는 경우
    """
    path = PROMPTS_DIR / relative_path
    return path.read_text(encoding="utf-8").strip()
