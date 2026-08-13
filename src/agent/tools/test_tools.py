"""
Test and Command Tools for Agent

Provides test execution and command running capabilities:
- RunTestsTool: Run pytest tests
- RunCommandTool: Run allowed shell commands
"""

import asyncio
import subprocess
import sys
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

    # pytest 종료 코드 중 "테스트가 아예 하나도 실행되지 않았다"를 뜻하는 것들.
    # 5 = 수집된 테스트 없음(디렉토리가 비었거나 -k 필터가 아무것도 매칭 못 함),
    # 4 = 사용법 오류 — 실제로는 tests 디렉토리 자체가 없을 때 대부분 여기로 온다.
    # 둘 다 "코드가 틀렸다"가 아니라 "검증할 수단이 없었다"는 뜻이므로 실패와
    # 구분해야 한다. 예전에는 exit_code != 0을 전부 success=False로 뭉갰는데,
    # 그러면 모델이 자기 수정이 잘못된 걸로 오해해 멀쩡한 코드를 계속 고치며
    # max_iterations(20)까지 헛돌다 task_failed로 끝났다 — 테스트가 없는
    # 워크스페이스에서 6회 중 5회 재현(2026-08-13).
    _NO_TESTS_EXIT_CODES = frozenset({4, 5})

    _OUTCOME_MESSAGES = {
        "no_tests": (
            "테스트가 하나도 실행되지 않았습니다 (테스트 파일이 없거나 필터가 "
            "아무것도 매칭하지 못했습니다). 이것은 코드 수정이 잘못됐다는 뜻이 "
            "아니라 검증할 테스트가 없다는 뜻입니다. 같은 수정을 반복하지 마세요. "
            "테스트를 새로 작성하거나, 요청받은 수정이 끝났다면 finish를 호출하세요."
        ),
        "failed": (
            "테스트가 실행되었고 일부가 실패했습니다. stdout의 실패 내역을 보고 "
            "원인을 고치세요."
        ),
        "error": (
            "pytest 실행 자체가 비정상 종료했습니다. stderr를 확인하세요."
        ),
    }

    @classmethod
    def _classify(cls, exit_code: int) -> str:
        """pytest 종료 코드를 outcome으로 분류한다."""
        if exit_code == 0:
            return "passed"
        if exit_code in cls._NO_TESTS_EXIT_CODES:
            return "no_tests"
        if exit_code == 1:
            return "failed"
        # 2(중단), 3(내부 오류) 등
        return "error"

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
                "success": True/False,   # 테스트가 실제로 돌아서 전부 통과했을 때만 True
                "outcome": "passed" | "failed" | "no_tests" | "error",
                "exit_code": 종료 코드,
                "stdout": 표준 출력,
                "stderr": 표준 에러,
                "message": 사람이 읽는 설명 (outcome이 passed가 아닐 때),
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

        # pytest 명령 구성 — 그냥 "pytest"가 아니라 "python -m pytest"로 실행해야
        # cwd(워크스페이스 루트)가 sys.path에 들어가서 `from src.foo import bar`처럼
        # 워크스페이스 루트 기준 임포트가 conftest.py 없이도 동작한다. 이 저장소
        # 자신을 테스트할 땐 루트의 conftest.py가 이미 sys.path를 잡아줘서 안
        # 드러났지만, 에이전트가 만드는 새 워크스페이스엔 그런 conftest.py가 없다.
        cmd = [sys.executable, "-m", "pytest", "-v", "--tb=short"]

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

            exit_code = result["exit_code"]
            outcome = self._classify(exit_code)
            success = outcome == "passed"

            self.logger.info(
                f"Tests completed: outcome={outcome}, "
                f"passed={summary['passed']}, "
                f"failed={summary['failed']}, "
                f"errors={summary['errors']}"
            )

            response = {
                "success": success,
                "outcome": outcome,
                "exit_code": exit_code,
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "summary": summary
            }

            message = self._OUTCOME_MESSAGES.get(outcome)
            if message:
                response["message"] = message

            return response

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
