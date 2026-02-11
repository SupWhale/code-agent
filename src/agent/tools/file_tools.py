"""
File Tools for Agent

Provides file manipulation capabilities:
- ReadFileTool: Read file contents
- EditFileTool: Edit file using string replacement
- CreateFileTool: Create new file
- DeleteFileTool: Delete file
"""

import aiofiles
from pathlib import Path
from typing import Dict, Any
import logging

from .base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class ReadFileTool(BaseTool):
    """
    파일 읽기 도구

    파일 내용을 읽어서 문자열로 반환합니다.
    """

    async def execute(self, params: Dict[str, Any]) -> str:
        """
        파일 읽기

        Args:
            params: {"path": "파일 경로"}

        Returns:
            파일 내용 (문자열)

        Raises:
            ValueError: 필수 파라미터 누락
            FileNotFoundError: 파일을 찾을 수 없음
            ToolExecutionError: 파일 읽기 실패
        """
        # 파라미터 검증
        self._validate_params(params, ["path"])

        file_path = self._resolve_path(params["path"])

        self.logger.info(f"Reading file: {file_path}")

        # 파일 존재 확인
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {params['path']}")

        if not file_path.is_file():
            raise ValueError(f"Not a file: {params['path']}")

        # 파일 읽기
        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()

            self.logger.info(
                f"Successfully read file: {file_path} ({len(content)} characters)"
            )

            return content

        except UnicodeDecodeError as e:
            raise ToolExecutionError(
                f"Cannot read binary file. Use a different tool for binary files: {e}"
            )

        except Exception as e:
            raise ToolExecutionError(f"Failed to read file: {e}")


class EditFileTool(BaseTool):
    """
    파일 수정 도구 (문자열 치환)

    old_string을 new_string으로 정확히 치환합니다.
    """

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        파일 수정

        Args:
            params: {
                "path": "파일 경로",
                "old_string": "기존 문자열",
                "new_string": "새 문자열"
            }

        Returns:
            {
                "success": True,
                "changes": 변경 횟수,
                "backup": "백업 파일 경로"
            }

        Raises:
            ValueError: 필수 파라미터 누락 또는 old_string이 파일에 없음
            FileNotFoundError: 파일을 찾을 수 없음
            ToolExecutionError: 파일 수정 실패
        """
        # 파라미터 검증
        self._validate_params(params, ["path", "old_string", "new_string"])

        file_path = self._resolve_path(params["path"])
        old_string = params["old_string"]
        new_string = params["new_string"]

        self.logger.info(f"Editing file: {file_path}")

        # 파일 존재 확인
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {params['path']}")

        if not file_path.is_file():
            raise ValueError(f"Not a file: {params['path']}")

        # old_string과 new_string이 같으면 에러
        if old_string == new_string:
            raise ValueError("old_string and new_string are identical. No changes needed.")

        try:
            # 파일 읽기
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()

            # old_string 존재 확인
            if old_string not in content:
                raise ValueError(
                    f"String not found in file. Make sure old_string matches exactly "
                    f"(including whitespace, indentation, and line breaks).\n\n"
                    f"File: {params['path']}\n"
                    f"Old string:\n{old_string[:200]}{'...' if len(old_string) > 200 else ''}"
                )

            # 중복 확인 (유니크해야 함)
            count = content.count(old_string)
            if count > 1:
                raise ValueError(
                    f"String appears {count} times in file. Add more context to make it unique.\n\n"
                    f"File: {params['path']}\n"
                    f"Old string:\n{old_string[:200]}{'...' if len(old_string) > 200 else ''}"
                )

            # 백업 생성
            backup_path = file_path.with_suffix(file_path.suffix + ".backup")
            async with aiofiles.open(backup_path, "w", encoding="utf-8") as f:
                await f.write(content)

            # 치환
            new_content = content.replace(old_string, new_string, 1)

            # 파일 쓰기
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(new_content)

            self.logger.info(
                f"Successfully edited file: {file_path} (backup: {backup_path})"
            )

            return {
                "success": True,
                "changes": 1,
                "backup": str(backup_path),
                "old_size": len(content),
                "new_size": len(new_content)
            }

        except ValueError:
            raise  # ValueError는 그대로 전달

        except Exception as e:
            raise ToolExecutionError(f"Failed to edit file: {e}")


class CreateFileTool(BaseTool):
    """
    새 파일 생성 도구

    지정된 경로에 새 파일을 생성합니다.
    """

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        파일 생성

        Args:
            params: {
                "path": "파일 경로",
                "content": "파일 내용"
            }

        Returns:
            {
                "success": True,
                "path": "절대 경로",
                "size": 파일 크기 (바이트)
            }

        Raises:
            ValueError: 필수 파라미터 누락
            FileExistsError: 파일이 이미 존재
            ToolExecutionError: 파일 생성 실패
        """
        # 파라미터 검증
        self._validate_params(params, ["path", "content"])

        file_path = self._resolve_path(params["path"])
        content = params["content"]

        self.logger.info(f"Creating file: {file_path}")

        # 파일이 이미 존재하면 에러
        if file_path.exists():
            raise FileExistsError(
                f"File already exists: {params['path']}. Use edit_file to modify it."
            )

        try:
            # 디렉토리 생성 (부모 디렉토리가 없으면)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # 파일 쓰기
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(content)

            file_size = file_path.stat().st_size

            self.logger.info(
                f"Successfully created file: {file_path} ({file_size} bytes)"
            )

            return {
                "success": True,
                "path": str(file_path),
                "size": file_size
            }

        except Exception as e:
            raise ToolExecutionError(f"Failed to create file: {e}")


class DeleteFileTool(BaseTool):
    """
    파일 삭제 도구

    파일을 삭제하고 백업을 생성합니다.
    """

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        파일 삭제

        Args:
            params: {
                "path": "파일 경로",
                "confirm": True  # 안전장치 (반드시 True여야 함)
            }

        Returns:
            {
                "success": True,
                "deleted": "삭제된 파일 경로",
                "backup": "백업 파일 경로"
            }

        Raises:
            ValueError: 필수 파라미터 누락 또는 confirm이 False
            FileNotFoundError: 파일을 찾을 수 없음
            ToolExecutionError: 파일 삭제 실패
        """
        # 파라미터 검증
        self._validate_params(params, ["path", "confirm"])

        file_path = self._resolve_path(params["path"])
        confirm = params.get("confirm", False)

        # 안전장치: confirm이 True가 아니면 에러
        if not confirm:
            raise ValueError(
                "Must set confirm=true to delete file. This is a safety measure."
            )

        self.logger.warning(f"Deleting file: {file_path}")

        # 파일 존재 확인
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {params['path']}")

        if not file_path.is_file():
            raise ValueError(f"Not a file: {params['path']}")

        try:
            # 백업 경로 생성 (.deleted 확장자 추가)
            backup_path = file_path.with_suffix(file_path.suffix + ".deleted")

            # 백업이 이미 있으면 타임스탬프 추가
            if backup_path.exists():
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = file_path.with_suffix(f"{file_path.suffix}.deleted.{timestamp}")

            # 파일 이동 (삭제 대신 백업으로 이동)
            file_path.rename(backup_path)

            self.logger.warning(
                f"Successfully deleted file: {file_path} (backup: {backup_path})"
            )

            return {
                "success": True,
                "deleted": str(file_path),
                "backup": str(backup_path)
            }

        except Exception as e:
            raise ToolExecutionError(f"Failed to delete file: {e}")
