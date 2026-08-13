"""RunTestsTool의 outcome 분류 단위 테스트

pytest 종료 코드를 "통과 / 실패 / 테스트 없음 / 실행 오류"로 구분하는 부분을 고정한다.

이 구분이 없던 시절에는 `success = exit_code == 0` 한 줄로 모든 비정상 종료를 실패로
뭉갰다. 그러면 테스트가 아예 없는 워크스페이스에서 에이전트가 자기 코드 수정이 잘못된
것으로 오해해, 이미 올바르게 고친 코드를 계속 다시 고치며 max_iterations(20)까지 헛돌다
task_failed로 끝났다 (테스트 없는 시나리오 6회 중 5회 재현, 2026-08-13).
"""

import pytest

from src.agent.tools.test_tools import RunTestsTool


class _StubRunTestsTool(RunTestsTool):
    """실제로 pytest를 띄우지 않고 정해둔 종료 코드를 돌려주는 스텁."""

    def __init__(self, exit_code, stdout="", stderr=""):
        super().__init__(workspace_path="/tmp")
        self._fake = {"exit_code": exit_code, "stdout": stdout, "stderr": stderr}

    async def _run_command(self, cmd, timeout=None, cwd=None):
        return self._fake


@pytest.mark.parametrize(
    "exit_code, expected",
    [
        (0, "passed"),
        (1, "failed"),
        (2, "error"),   # 사용자 중단
        (3, "error"),   # pytest 내부 오류
        (4, "no_tests"),  # 사용법 오류 — 실제로는 tests 디렉토리 자체가 없을 때
        (5, "no_tests"),  # 수집된 테스트 없음(빈 디렉토리 / -k 미매칭)
    ],
)
def test_classify_maps_pytest_exit_codes(exit_code, expected):
    assert RunTestsTool._classify(exit_code) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_code", [4, 5])
async def test_no_tests_is_not_reported_as_failure(exit_code):
    """테스트가 하나도 안 돌았으면 success=False지만 outcome으로 구분 가능해야 한다."""
    tool = _StubRunTestsTool(exit_code)

    result = await tool.execute({"scope": "all"})

    assert result["outcome"] == "no_tests"
    assert result["success"] is False
    # 모델이 "내 수정이 틀렸다"로 오해하지 않도록 설명이 함께 실려야 한다
    assert "코드 수정이 잘못됐다는 뜻이 아니라" in result["message"]


@pytest.mark.asyncio
async def test_passing_run_has_no_message():
    tool = _StubRunTestsTool(0, stdout="== 2 passed in 0.01s ==")

    result = await tool.execute({"scope": "all"})

    assert result["outcome"] == "passed"
    assert result["success"] is True
    assert "message" not in result


@pytest.mark.asyncio
async def test_real_failure_is_still_a_failure():
    """테스트가 실제로 돌아서 깨진 경우는 예전처럼 실패로 남아야 한다."""
    tool = _StubRunTestsTool(1, stdout="== 1 failed, 1 passed in 0.02s ==")

    result = await tool.execute({"scope": "all"})

    assert result["outcome"] == "failed"
    assert result["success"] is False
    assert result["summary"]["failed"] == 1
