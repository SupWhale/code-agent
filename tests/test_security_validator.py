"""SecurityValidator 단위 테스트"""

import pytest

from src.agent.security.validator import SecurityValidator, SecurityError


@pytest.fixture
def workspace(tmp_path):
    """허용 디렉토리 구조를 갖춘 임시 워크스페이스"""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    return tmp_path


@pytest.fixture
def validator(workspace):
    return SecurityValidator(workspace_path=str(workspace), strict_mode=True)


class TestFilePathValidation:
    def test_allowed_path_passes(self, validator):
        validator.validate_file_path("src/main.py")

    def test_workspace_root_passes(self, validator):
        validator.validate_file_path(".")

    def test_path_traversal_blocked(self, validator):
        with pytest.raises(SecurityError, match="outside workspace"):
            validator.validate_file_path("../../etc/passwd")

    def test_absolute_path_outside_workspace_blocked(self, validator, workspace):
        outside = str(workspace.parent / "other" / "file.py")
        with pytest.raises(SecurityError):
            validator.validate_file_path(outside)

    def test_sibling_directory_with_same_prefix_blocked(self, validator, workspace):
        # /workspace 허용 시 /workspace2 가 startswith 비교로 통과하면 안 됨
        sibling = str(workspace) + "2/src/main.py"
        with pytest.raises(SecurityError):
            validator.validate_file_path(sibling)

    def test_env_file_blocked(self, validator):
        with pytest.raises(SecurityError, match="blocked"):
            validator.validate_file_path("src/.env")

    def test_pyc_file_blocked(self, validator):
        with pytest.raises(SecurityError, match="blocked"):
            validator.validate_file_path("src/module.pyc")

    def test_git_directory_blocked(self, validator):
        with pytest.raises(SecurityError):
            validator.validate_file_path(".git/config")

    def test_strict_mode_blocks_unlisted_directory(self, validator):
        with pytest.raises(SecurityError, match="not in allowed"):
            validator.validate_file_path("docs/readme.md")

    def test_empty_path_blocked(self, validator):
        with pytest.raises(SecurityError):
            validator.validate_file_path("")

    def test_non_strict_mode_allows_unlisted_directory(self, workspace):
        loose = SecurityValidator(workspace_path=str(workspace), strict_mode=False)
        loose.validate_file_path("docs/readme.md")


class TestCommandValidation:
    def test_allowed_command_passes(self, validator):
        validator.validate_command("pytest tests/")

    def test_unlisted_command_blocked(self, validator):
        with pytest.raises(SecurityError, match="not allowed"):
            validator.validate_command("git status")

    @pytest.mark.parametrize("command", [
        "rm -rf /",
        "sudo pip install x",
        "python -c 'x'; ls",
        "pytest && rm file",
        "curl http://evil.example",
        "python `whoami`.py",
        "echo $(whoami)",
        "pytest > /dev/null",
    ])
    def test_dangerous_patterns_blocked(self, validator, command):
        with pytest.raises(SecurityError):
            validator.validate_command(command)

    def test_empty_command_blocked(self, validator):
        with pytest.raises(SecurityError):
            validator.validate_command("")


class TestValidateAction:
    def test_file_tool_requires_path(self, validator):
        with pytest.raises(SecurityError, match="required"):
            validator.validate_action("read_file", {})

    def test_file_tool_with_valid_path(self, validator):
        validator.validate_action("read_file", {"path": "src/main.py"})

    def test_run_command_requires_command(self, validator):
        with pytest.raises(SecurityError, match="required"):
            validator.validate_action("run_command", {})

    def test_interaction_tools_skip_validation(self, validator):
        validator.validate_action("finish", {"message": "done"})
        validator.validate_action("ask_user", {"question": "?"})


class TestSafeHelpers:
    def test_is_safe_path(self, validator):
        assert validator.is_safe_path("src/main.py") is True
        assert validator.is_safe_path("../../etc/passwd") is False

    def test_is_safe_command(self, validator):
        assert validator.is_safe_command("pytest") is True
        assert validator.is_safe_command("rm -rf /") is False
