"""
Test and Command Tools for Agent

Provides test execution and command running capabilities:
- RunTestsTool: Run pytest tests
- RunCommandTool: Run allowed shell commands
"""

import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
import logging

from .base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class RunTestsTool(BaseTool):
    """
    테스트 실행 도구

    pytest를 사용하여 테스트를 실행합니다.
    """

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        테스트 실행

        Args:
            params: {
                "scope": "all" | "directory" | "file" | "filter" (기본값: "all"),
                "path": "테스트 경로" (scope가 directory/file일 때),
                "filter": "테스트 필터" (scope가 filter일 때, pytest -k),
                "timeout": 제한 시간(초) (선택, 기본값: 60)
            }

        Returns:
            {
                "success": True/False,
                "exit_code": 종료 코드,
                "stdout": 표준 출력,
                "stderr": 표준 에러,
                "summary": {
                    "passed": 통과 수,
                    "failed": 실패 수,
                    "errors": 에러 수
                }
            }

        Raises:
            ValueError: 잘못된 파라미터
            ToolExecutionError: 테스트 실행 실패
        """
        scope = params.get("scope", "all")
        path = params.get("path")
        test_filter = params.get("filter")
        timeout = params.get("timeout", 60)

        self.logger.info(f"Running tests (scope={scope}, timeout={timeout}s)")

        # pytest 명령 구성
        cmd = ["pytest", "-v", "--tb=short"]

        if scope == "all":
            # 전체 테스트
            if self.workspace_path:
                cmd.append(str(self.workspace_path / "tests"))
            else:
                cmd.append("tests")

        elif scope == "directory" or scope == "file":
            if not path:
                raise ValueError(f"'path' parameter is required for scope={scope}")

            test_path = self._resolve_path(path)

            if not test_path.exists():
                raise FileNotFoundError(f"Test path not found: {path}")

            cmd.append(str(test_path))

        elif scope == "filter":
            if not test_filter:
                raise ValueError("'filter' parameter is required for scope=filter")

            cmd.extend(["-k", test_filter])

            # 테스트 디렉토리 추가
            if self.workspace_path:
                cmd.append(str(self.workspace_path / "tests"))
            else:
                cmd.append("tests")

        else:
            raise ValueError(
                f"Invalid scope: {scope}. Must be 'all', 'directory', 'file', or 'filter'"
            )

        try:
            # pytest 실행
            result = await self._run_command(
                cmd,
                timeout=timeout,
                cwd=str(self.workspace_path) if self.workspace_path else None
            )

            # 결과 파싱
            summary = self._parse_pytest_output(result["stdout"])

            success = result["exit_code"] == 0

            self.logger.info(
                f"Tests completed: "
                f"passed={summary['passed']}, "
                f"failed={summary['failed']}, "
                f"errors={summary['errors']}"
            )

            return {
                "success": success,
                "exit_code": result["exit_code"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "summary": summary
            }

        except asyncio.TimeoutError:
            raise ToolExecutionError(f"Test execution timed out after {timeout}s")

        except Exception as e:
            raise ToolExecutionError(f"Failed to run tests: {e}")

    def _parse_pytest_output(self, output: str) -> Dict[str, int]:
        """pytest 출력에서 결과 요약 추출"""
        import re

        # "= 5 passed, 2 failed in 1.23s =" 같은 형식 찾기
        match = re.search(
            r"=+\s*(\d+)\s+passed|=+\s*(\d+)\s+failed|=+\s*(\d+)\s+error",
            output
        )

        passed = 0
        failed = 0
        errors = 0

        # 더 정확한 파싱
        passed_match = re.search(r"(\d+)\s+passed", output)
        failed_match = re.search(r"(\d+)\s+failed", output)
        error_match = re.search(r"(\d+)\s+error", output)

        if passed_match:
            passed = int(passed_match.group(1))
        if failed_match:
            failed = int(failed_match.group(1))
        if error_match:
            errors = int(error_match.group(1))

        return {
            "passed": passed,
            "failed": failed,
            "errors": errors
        }

    async def _run_command(
        self,
        cmd: list,
        timeout: int,
        cwd: Optional[str] = None
    ) -> Dict[str, Any]:
        """비동기 명령 실행"""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            return {
                "exit_code": process.returncode,
                "stdout": stdout.decode("utf-8", errors="ignore"),
                "stderr": stderr.decode("utf-8", errors="ignore")
            }

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise


class RunCommandTool(BaseTool):
    """
    명령 실행 도구

    허용된 명령만 실행합니다.
    SecurityValidator와 함께 사용해야 합니다.
    """

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        명령 실행

        Args:
            params: {
                "command": "실행할 명령",
                "timeout": 제한 시간(초) (선택, 기본값: 30)
            }

        Returns:
            {
                "success": True/False,
                "exit_code": 종료 코드,
                "stdout": 표준 출력,
                "stderr": 표준 에러
            }

        Raises:
            ValueError: 필수 파라미터 누락
            ToolExecutionError: 명령 실행 실패
        """
        # 파라미터 검증
        self._validate_params(params, ["command"])

        command = params["command"]
        timeout = params.get("timeout", 30)

        self.logger.info(f"Running command: {command}")

        # 명령어 파싱 (간단한 방식)
        cmd_parts = command.split()

        try:
            # 명령 실행
            result = await self._run_command(
                cmd_parts,
                timeout=timeout,
                cwd=str(self.workspace_path) if self.workspace_path else None
            )

            success = result["exit_code"] == 0

            if success:
                self.logger.info(f"Command completed successfully")
            else:
                self.logger.warning(
                    f"Command failed with exit code {result['exit_code']}"
                )

            return {
                "success": success,
                "exit_code": result["exit_code"],
                "stdout": result["stdout"],
                "stderr": result["stderr"]
            }

        except asyncio.TimeoutError:
            raise ToolExecutionError(f"Command timed out after {timeout}s")

        except FileNotFoundError:
            raise ToolExecutionError(
                f"Command not found: {cmd_parts[0]}. "
                f"Make sure it's installed and in PATH."
            )

        except Exception as e:
            raise ToolExecutionError(f"Failed to run command: {e}")

    async def _run_command(
        self,
        cmd: list,
        timeout: int,
        cwd: Optional[str] = None
    ) -> Dict[str, Any]:
        """비동기 명령 실행"""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            return {
                "exit_code": process.returncode,
                "stdout": stdout.decode("utf-8", errors="ignore"),
                "stderr": stderr.decode("utf-8", errors="ignore")
            }

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise
