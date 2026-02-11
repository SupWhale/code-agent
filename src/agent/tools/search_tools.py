"""
Search Tools for Agent

Provides file and code search capabilities:
- ListFilesTool: List files in directory
- SearchCodeTool: Search code content (grep-like)
"""

from pathlib import Path
from typing import Dict, Any, List
import re
import logging

from .base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class ListFilesTool(BaseTool):
    """
    파일 목록 도구

    디렉토리의 파일과 하위 디렉토리를 나열합니다.
    """

    async def execute(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        파일 목록 조회

        Args:
            params: {
                "path": "디렉토리 경로" (기본값: "."),
                "pattern": "파일 패턴" (선택, 예: "*.py"),
                "recursive": True/False (선택, 기본값: False)
            }

        Returns:
            [
                {
                    "name": "파일명",
                    "path": "상대 경로",
                    "type": "file" | "directory",
                    "size": 파일 크기 (bytes, 파일인 경우만)
                },
                ...
            ]

        Raises:
            ValueError: 잘못된 파라미터
            FileNotFoundError: 디렉토리를 찾을 수 없음
            ToolExecutionError: 파일 목록 조회 실패
        """
        # 기본값 설정
        path = params.get("path", ".")
        pattern = params.get("pattern")
        recursive = params.get("recursive", False)

        dir_path = self._resolve_path(path)

        self.logger.info(
            f"Listing files in: {dir_path} "
            f"(pattern={pattern}, recursive={recursive})"
        )

        # 디렉토리 존재 확인
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")

        if not dir_path.is_dir():
            raise ValueError(f"Not a directory: {path}")

        try:
            files = []

            if recursive:
                # 재귀적 탐색
                if pattern:
                    # 패턴이 있으면 glob 사용
                    for item in dir_path.rglob(pattern):
                        files.append(self._file_info(item, dir_path))
                else:
                    # 패턴 없으면 모든 파일/디렉토리
                    for item in dir_path.rglob("*"):
                        files.append(self._file_info(item, dir_path))
            else:
                # 현재 디렉토리만
                if pattern:
                    # 패턴이 있으면 glob 사용
                    for item in dir_path.glob(pattern):
                        files.append(self._file_info(item, dir_path))
                else:
                    # 패턴 없으면 모든 파일/디렉토리
                    for item in dir_path.iterdir():
                        files.append(self._file_info(item, dir_path))

            # 정렬: 디렉토리 먼저, 그 다음 이름순
            files.sort(key=lambda x: (x["type"] != "directory", x["name"]))

            self.logger.info(f"Found {len(files)} items")

            return files

        except Exception as e:
            raise ToolExecutionError(f"Failed to list files: {e}")

    def _file_info(self, path: Path, base_path: Path) -> Dict[str, Any]:
        """파일/디렉토리 정보 추출"""
        try:
            relative_path = path.relative_to(base_path)
        except ValueError:
            # base_path 밖에 있는 경우 (symlink 등)
            relative_path = path

        info = {
            "name": path.name,
            "path": str(relative_path),
            "type": "directory" if path.is_dir() else "file"
        }

        # 파일이면 크기 추가
        if path.is_file():
            try:
                info["size"] = path.stat().st_size
            except:
                info["size"] = 0

        return info


class SearchCodeTool(BaseTool):
    """
    코드 검색 도구 (grep-like)

    파일 내용에서 패턴을 검색합니다.
    """

    async def execute(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        코드 검색

        Args:
            params: {
                "pattern": "검색 패턴",
                "path": "검색 경로" (기본값: "."),
                "regex": True/False (선택, 기본값: False),
                "file_pattern": "파일 패턴" (선택, 예: "*.py"),
                "ignore_case": True/False (선택, 기본값: False)
            }

        Returns:
            [
                {
                    "file": "파일 경로",
                    "line": 라인 번호,
                    "content": "라인 내용",
                    "match": "매칭된 부분"
                },
                ...
            ]

        Raises:
            ValueError: 필수 파라미터 누락
            FileNotFoundError: 경로를 찾을 수 없음
            ToolExecutionError: 검색 실패
        """
        # 파라미터 검증
        self._validate_params(params, ["pattern"])

        pattern_str = params["pattern"]
        path = params.get("path", ".")
        use_regex = params.get("regex", False)
        file_pattern = params.get("file_pattern", "*")
        ignore_case = params.get("ignore_case", False)

        search_path = self._resolve_path(path)

        self.logger.info(
            f"Searching for pattern '{pattern_str}' in {search_path} "
            f"(regex={use_regex}, file_pattern={file_pattern})"
        )

        # 경로 존재 확인
        if not search_path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        try:
            # 정규식 패턴 컴파일
            if use_regex:
                flags = re.IGNORECASE if ignore_case else 0
                try:
                    pattern = re.compile(pattern_str, flags)
                except re.error as e:
                    raise ValueError(f"Invalid regex pattern: {e}")
            else:
                # 일반 문자열 검색용 정규식
                escaped = re.escape(pattern_str)
                flags = re.IGNORECASE if ignore_case else 0
                pattern = re.compile(escaped, flags)

            results = []

            # 검색할 파일 목록
            if search_path.is_file():
                files = [search_path]
            else:
                # 디렉토리면 재귀적으로 파일 찾기
                files = list(search_path.rglob(file_pattern))
                # 파일만 필터링
                files = [f for f in files if f.is_file()]

            # 각 파일에서 검색
            for file_path in files:
                try:
                    # 텍스트 파일만 읽기
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, start=1):
                            match = pattern.search(line)
                            if match:
                                try:
                                    relative_path = file_path.relative_to(self.workspace_path)
                                except ValueError:
                                    relative_path = file_path

                                results.append({
                                    "file": str(relative_path),
                                    "line": line_num,
                                    "content": line.rstrip("\n"),
                                    "match": match.group(0)
                                })

                                # 결과가 너무 많으면 제한 (100개)
                                if len(results) >= 100:
                                    self.logger.warning("Search results limited to 100")
                                    break

                except (UnicodeDecodeError, PermissionError):
                    # 바이너리 파일이나 권한 없는 파일은 스킵
                    continue

                if len(results) >= 100:
                    break

            self.logger.info(f"Found {len(results)} matches")

            return results

        except ValueError:
            raise  # ValueError는 그대로 전달

        except Exception as e:
            raise ToolExecutionError(f"Failed to search code: {e}")
