"""
Tests for SecurityValidator

Tests security validation for:
- Path traversal prevention
- Command injection prevention
- File size limits
- Blocked paths
"""

import pytest
from pathlib import Path
import tempfile
import os

from src.agent.security.validator import SecurityValidator, SecurityError


@pytest.fixture
def temp_workspace():
    """임시 작업 디렉토리 생성"""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # 허용된 디렉토리 생성
        (workspace / "src").mkdir()
        (workspace / "tests").mkdir()
        (workspace / "prompts").mkdir()

        # 차단된 디렉토리 생성
        (workspace / ".git").mkdir()
        (workspace / "node_modules").mkdir()

        # 테스트 파일 생성
        (workspace / "src" / "test.py").write_text("print('hello')")
        (workspace / ".env").write_text("SECRET=123")

        yield workspace


@pytest.fixture
def validator(temp_workspace):
    """SecurityValidator 인스턴스 생성"""
    return SecurityValidator(str(temp_workspace), strict_mode=True)


class TestFilePathValidation:
    """파일 경로 검증 테스트"""

    def test_valid_path_in_src(self, validator, temp_workspace):
        """허용된 경로 (src/) 접근 - 성공"""
        validator.validate_file_path("src/test.py", temp_workspace)

    def test_valid_path_in_tests(self, validator, temp_workspace):
        """허용된 경로 (tests/) 접근 - 성공"""
        validator.validate_file_path("tests/test_file.py", temp_workspace)

    def test_path_traversal_blocked(self, validator, temp_workspace):
        """경로 탐색 공격 차단 - 실패"""
        with pytest.raises(SecurityError, match="outside workspace"):
            validator.validate_file_path("../../etc/passwd", temp_workspace)

    def test_blocked_path_env(self, validator, temp_workspace):
        """차단된 경로 (.env) 접근 - 실패"""
        with pytest.raises(SecurityError, match="blocked path"):
            validator.validate_file_path(".env", temp_workspace)

    def test_blocked_path_git(self, validator, temp_workspace):
        """차단된 경로 (.git) 접근 - 실패"""
        with pytest.raises(SecurityError, match="blocked path"):
            validator.validate_file_path(".git/config", temp_workspace)

    def test_blocked_path_node_modules(self, validator, temp_workspace):
        """차단된 경로 (node_modules) 접근 - 실패"""
        with pytest.raises(SecurityError, match="blocked path"):
            validator.validate_file_path("node_modules/package.json", temp_workspace)

    def test_blocked_file_type_pyc(self, validator, temp_workspace):
        """차단된 파일 타입 (*.pyc) 접근 - 실패"""
        with pytest.raises(SecurityError, match="blocked file type"):
            validator.validate_file_path("src/test.pyc", temp_workspace)

    def test_strict_mode_disallowed_path(self, validator, temp_workspace):
        """엄격 모드: 허용 목록에 없는 경로 - 실패"""
        # 'scripts'는 허용 목록에 있지만, 'config'는 없음
        with pytest.raises(SecurityError, match="not in allowed directories"):
            validator.validate_file_path("config/settings.py", temp_workspace)

    def test_absolute_path_in_workspace(self, validator, temp_workspace):
        """절대 경로 (workspace 내부) - 성공"""
        abs_path = temp_workspace / "src" / "test.py"
        validator.validate_file_path(str(abs_path), temp_workspace)

    def test_absolute_path_outside_workspace(self, validator, temp_workspace):
        """절대 경로 (workspace 외부) - 실패"""
        with pytest.raises(SecurityError, match="outside workspace"):
            validator.validate_file_path("/etc/passwd", temp_workspace)

    def test_workspace_root_allowed(self, validator, temp_workspace):
        """Workspace 루트는 허용"""
        validator.validate_file_path(".", temp_workspace)


class TestCommandValidation:
    """명령어 검증 테스트"""

    def test_allowed_command_pytest(self, validator):
        """허용된 명령어 (pytest) - 성공"""
        validator.validate_command("pytest tests/test_user.py")

    def test_allowed_command_python(self, validator):
        """허용된 명령어 (python) - 성공"""
        validator.validate_command("python -m pytest")

    def test_allowed_command_black(self, validator):
        """허용된 명령어 (black) - 성공"""
        validator.validate_command("black src/")

    def test_disallowed_command_rm(self, validator):
        """차단된 명령어 (rm) - 실패 (위험한 패턴으로 잡힘)"""
        with pytest.raises(SecurityError, match="Dangerous pattern"):
            validator.validate_command("rm -rf /")

    def test_disallowed_command_sudo(self, validator):
        """차단된 명령어 (sudo) - 실패 (위험한 패턴으로 잡힘)"""
        with pytest.raises(SecurityError, match="Dangerous pattern"):
            validator.validate_command("sudo apt-get install")

    def test_dangerous_pattern_rm_rf(self, validator):
        """위험한 패턴 (rm -rf) - 실패"""
        # pytest 명령어라도 rm -rf가 포함되면 차단
        with pytest.raises(SecurityError, match="Dangerous pattern"):
            validator.validate_command("pytest && rm -rf /tmp")

    def test_dangerous_pattern_pipe(self, validator):
        """위험한 패턴 (파이프 |) - 실패"""
        with pytest.raises(SecurityError, match="Dangerous pattern"):
            validator.validate_command("pytest | grep failed")

    def test_dangerous_pattern_semicolon(self, validator):
        """위험한 패턴 (세미콜론 ;) - 실패"""
        with pytest.raises(SecurityError, match="Dangerous pattern"):
            validator.validate_command("pytest; echo done")

    def test_dangerous_pattern_command_substitution(self, validator):
        """위험한 패턴 (명령 치환 $()) - 실패"""
        with pytest.raises(SecurityError, match="Dangerous pattern"):
            validator.validate_command("pytest $(cat /etc/passwd)")

    def test_dangerous_pattern_redirection(self, validator):
        """위험한 패턴 (리다이렉션 >) - 실패"""
        with pytest.raises(SecurityError, match="Dangerous pattern"):
            validator.validate_command("pytest > /dev/null")


class TestActionValidation:
    """액션 검증 테스트"""

    def test_validate_read_file_action(self, validator, temp_workspace):
        """read_file 액션 검증 - 성공"""
        validator.validate_action(
            "read_file",
            {"path": "src/test.py"},
            str(temp_workspace)
        )

    def test_validate_edit_file_action(self, validator, temp_workspace):
        """edit_file 액션 검증 - 성공"""
        validator.validate_action(
            "edit_file",
            {"path": "src/test.py", "old_string": "...", "new_string": "..."},
            str(temp_workspace)
        )

    def test_validate_run_command_action(self, validator):
        """run_command 액션 검증 - 성공"""
        validator.validate_action(
            "run_command",
            {"command": "pytest tests/"}
        )

    def test_validate_action_missing_path(self, validator):
        """path 파라미터 누락 - 실패"""
        with pytest.raises(SecurityError, match="'path' parameter is required"):
            validator.validate_action("read_file", {})

    def test_validate_action_missing_command(self, validator):
        """command 파라미터 누락 - 실패"""
        with pytest.raises(SecurityError, match="'command' parameter is required"):
            validator.validate_action("run_command", {})


class TestFileSizeValidation:
    """파일 크기 검증 테스트"""

    def test_file_size_within_limit(self, validator, temp_workspace):
        """파일 크기 제한 내 - 성공"""
        small_file = temp_workspace / "src" / "small.py"
        small_file.write_text("print('hello')")

        validator.validate_file_size(small_file, "read")

    def test_file_size_exceeds_limit(self, validator, temp_workspace):
        """파일 크기 제한 초과 - 실패"""
        large_file = temp_workspace / "src" / "large.py"

        # 2MB 파일 생성 (읽기 제한은 1MB)
        large_file.write_bytes(b"x" * (2 * 1024 * 1024))

        with pytest.raises(SecurityError, match="exceeds limit"):
            validator.validate_file_size(large_file, "read")

    def test_nonexistent_file_no_error(self, validator, temp_workspace):
        """존재하지 않는 파일 - 에러 없음"""
        nonexistent = temp_workspace / "src" / "nonexistent.py"
        validator.validate_file_size(nonexistent, "read")


class TestHelperMethods:
    """헬퍼 메서드 테스트"""

    def test_is_safe_path_true(self, validator, temp_workspace):
        """안전한 경로 확인 - True"""
        assert validator.is_safe_path("src/test.py", temp_workspace) is True

    def test_is_safe_path_false(self, validator, temp_workspace):
        """안전하지 않은 경로 확인 - False"""
        assert validator.is_safe_path(".env", temp_workspace) is False

    def test_is_safe_command_true(self, validator):
        """안전한 명령어 확인 - True"""
        assert validator.is_safe_command("pytest tests/") is True

    def test_is_safe_command_false(self, validator):
        """안전하지 않은 명령어 확인 - False"""
        assert validator.is_safe_command("rm -rf /") is False


class TestNonStrictMode:
    """비엄격 모드 테스트"""

    def test_non_strict_mode_allows_any_path(self, temp_workspace):
        """비엄격 모드: 허용 목록에 없는 경로도 접근 가능"""
        validator = SecurityValidator(str(temp_workspace), strict_mode=False)

        # 'config'는 허용 목록에 없지만, 비엄격 모드에서는 허용
        (temp_workspace / "config").mkdir()
        validator.validate_file_path("config/settings.py", temp_workspace)

    def test_non_strict_mode_still_blocks_dangerous_paths(self, temp_workspace):
        """비엄격 모드에서도 위험한 경로는 차단"""
        validator = SecurityValidator(str(temp_workspace), strict_mode=False)

        # .env는 여전히 차단
        with pytest.raises(SecurityError, match="blocked path"):
            validator.validate_file_path(".env", temp_workspace)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
