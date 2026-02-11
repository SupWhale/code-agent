"""
Security Validator for Agent Actions

Validates all agent actions to prevent security vulnerabilities:
- Path traversal attacks
- Command injection
- Access to sensitive files
- File size limits
"""

from pathlib import Path
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """보안 위반 예외"""
    pass


class SecurityValidator:
    """
    에이전트 액션 보안 검증기

    모든 파일 접근, 명령 실행 등을 검증하여 보안 위협을 방지합니다.
    """

    # 허용된 경로 (workspace 기준 상대 경로)
    ALLOWED_PATHS = [
        "src",
        "tests",
        "prompts",
        "scripts"
    ]

    # 차단된 경로 패턴
    BLOCKED_PATHS = [
        ".env",
        ".env.local",
        ".env.production",
        ".git",
        ".gitignore",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".pytest_cache",
        ".mypy_cache",
        "*.pyc",
        "*.pyo",
        "*.key",
        "*.pem",
        "*.secret",
        "credentials",
        "secrets"
    ]

    # 허용된 명령어 (첫 단어만)
    ALLOWED_COMMANDS = [
        "pytest",
        "python",
        "python3",
        "pip",
        "pip3",
        "black",
        "ruff",
        "mypy",
        "pylint",
        "flake8",
        "isort"
    ]

    # 위험한 명령 패턴
    DANGEROUS_PATTERNS = [
        "rm -rf",
        "sudo",
        "chmod",
        "chown",
        "mv /",
        "dd if=",
        ">",  # 리다이렉션
        ">>",
        "|",  # 파이프 (일부 허용 가능하지만 기본은 차단)
        "&&",
        "||",
        ";",
        "`",  # 명령 치환
        "$(",
        "curl",
        "wget",
        "nc",
        "netcat"
    ]

    # 파일 크기 제한
    MAX_FILE_READ_SIZE = 1024 * 1024  # 1MB
    MAX_FILE_WRITE_SIZE = 500 * 1024  # 500KB

    def __init__(self, workspace_path: str, strict_mode: bool = True):
        """
        Args:
            workspace_path: 작업 디렉토리 절대 경로
            strict_mode: 엄격 모드 (True면 허용 목록에 없으면 차단)
        """
        self.workspace_path = Path(workspace_path).resolve()
        self.strict_mode = strict_mode

        if not self.workspace_path.exists():
            raise ValueError(f"Workspace path does not exist: {workspace_path}")

        if not self.workspace_path.is_dir():
            raise ValueError(f"Workspace path is not a directory: {workspace_path}")

        logger.info(f"SecurityValidator initialized for workspace: {self.workspace_path}")

    def validate_action(
        self,
        tool_name: str,
        params: Dict[str, Any],
        workspace_path: str = None
    ) -> None:
        """
        액션 보안 검증

        Args:
            tool_name: 도구 이름
            params: 파라미터 딕셔너리
            workspace_path: 작업 디렉토리 (선택, 지정하지 않으면 self.workspace_path 사용)

        Raises:
            SecurityError: 보안 위반 시
        """
        workspace = Path(workspace_path).resolve() if workspace_path else self.workspace_path

        # 파일 관련 도구
        if tool_name in ["read_file", "edit_file", "create_file", "delete_file"]:
            path = params.get("path")
            if not path:
                raise SecurityError(f"{tool_name}: 'path' parameter is required")
            self.validate_file_path(path, workspace)

        # 검색 도구
        elif tool_name in ["list_files", "search_code"]:
            path = params.get("path", ".")
            self.validate_file_path(path, workspace)

        # 명령 실행
        elif tool_name == "run_command":
            command = params.get("command")
            if not command:
                raise SecurityError("run_command: 'command' parameter is required")
            self.validate_command(command)

        # 테스트
        elif tool_name == "run_tests":
            if "path" in params:
                self.validate_file_path(params["path"], workspace)

        # 기타 도구는 검증 불필요 (ask_user, finish, report_error 등)

        logger.debug(f"Security validation passed for {tool_name}")

    def validate_file_path(self, path: str, workspace_path: Path = None) -> None:
        """
        파일 경로 검증

        Args:
            path: 파일 경로
            workspace_path: 작업 디렉토리 (선택)

        Raises:
            SecurityError: 보안 위반 시
        """
        if not path:
            raise SecurityError("Path cannot be empty")

        workspace = workspace_path or self.workspace_path

        # 절대 경로 해석
        if Path(path).is_absolute():
            target = Path(path).resolve()
        else:
            target = (workspace / path).resolve()

        # 1. Workspace 밖으로 나가는지 체크
        try:
            relative_path = target.relative_to(workspace)
        except ValueError:
            raise SecurityError(
                f"Path traversal detected: '{path}' is outside workspace"
            )

        # 2. 차단 경로 체크
        path_str = str(relative_path)

        for blocked in self.BLOCKED_PATHS:
            # 와일드카드 패턴 (*.pyc)
            if blocked.startswith("*"):
                if path_str.endswith(blocked[1:]):
                    raise SecurityError(
                        f"Access denied to blocked file type: {path}"
                    )
            # 일반 패턴
            elif blocked in path_str or path_str.startswith(blocked):
                raise SecurityError(
                    f"Access denied to blocked path: {path}"
                )

        # 3. 엄격 모드: 허용 경로 체크
        if self.strict_mode:
            is_allowed = False

            # 허용 목록 확인
            for allowed in self.ALLOWED_PATHS:
                allowed_full = (workspace / allowed).resolve()

                # target이 allowed_full 하위에 있는지 확인
                try:
                    target.relative_to(allowed_full)
                    is_allowed = True
                    break
                except ValueError:
                    continue

            # workspace 루트는 허용 (list_files 등에서 사용)
            if target == workspace:
                is_allowed = True

            if not is_allowed:
                raise SecurityError(
                    f"Path not in allowed directories "
                    f"({', '.join(self.ALLOWED_PATHS)}): {path}"
                )

        logger.debug(f"File path validation passed: {path}")

    def validate_command(self, command: str) -> None:
        """
        명령어 검증

        Args:
            command: 실행할 명령어

        Raises:
            SecurityError: 보안 위반 시
        """
        if not command:
            raise SecurityError("Command cannot be empty")

        # 위험한 패턴 먼저 체크 (세미콜론, 파이프 등)
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in command:
                raise SecurityError(
                    f"Dangerous pattern detected in command: '{pattern}'"
                )

        # 첫 단어 (명령어) 추출
        cmd_parts = command.split()
        cmd = cmd_parts[0]

        # 허용 명령어 확인
        if cmd not in self.ALLOWED_COMMANDS:
            raise SecurityError(
                f"Command not allowed: '{cmd}'. "
                f"Allowed commands: {', '.join(self.ALLOWED_COMMANDS)}"
            )

        logger.debug(f"Command validation passed: {command}")

    def validate_file_size(self, file_path: Path, operation: str = "read") -> None:
        """
        파일 크기 검증

        Args:
            file_path: 파일 경로 (Path 객체)
            operation: 작업 유형 ("read" 또는 "write")

        Raises:
            SecurityError: 파일 크기가 제한을 초과하는 경우
        """
        if not file_path.exists():
            return  # 파일이 없으면 크기 체크 불필요

        if not file_path.is_file():
            return  # 디렉토리면 스킵

        file_size = file_path.stat().st_size

        if operation == "read":
            max_size = self.MAX_FILE_READ_SIZE
        elif operation == "write":
            max_size = self.MAX_FILE_WRITE_SIZE
        else:
            raise ValueError(f"Invalid operation: {operation}")

        if file_size > max_size:
            raise SecurityError(
                f"File size ({file_size} bytes) exceeds limit "
                f"({max_size} bytes) for {operation} operation"
            )

        logger.debug(f"File size validation passed: {file_path} ({file_size} bytes)")

    def is_safe_path(self, path: str, workspace_path: Path = None) -> bool:
        """
        경로가 안전한지 확인 (예외 발생 없이)

        Args:
            path: 파일 경로
            workspace_path: 작업 디렉토리 (선택)

        Returns:
            안전하면 True, 아니면 False
        """
        try:
            self.validate_file_path(path, workspace_path)
            return True
        except SecurityError:
            return False

    def is_safe_command(self, command: str) -> bool:
        """
        명령어가 안전한지 확인 (예외 발생 없이)

        Args:
            command: 명령어

        Returns:
            안전하면 True, 아니면 False
        """
        try:
            self.validate_command(command)
            return True
        except SecurityError:
            return False
