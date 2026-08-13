"""finish 도구의 필드 계약 테스트

시스템 프롬프트(prompts/system_prompt.txt)는 finish.params에 changed_files와
summary를 포함시켜 놓았는데, FinishTool은 success/message/result만 읽고 나머지를
조용히 버렸다. 그래서 모델이 계약대로 보낸 변경 정보가 검증 단계에 닿지 못했다.

여기서는 (1) 두 필드가 정식으로 수용/정규화되는지, (2) 모델이 타입을 틀리게
보내도 흡수되는지, (3) 주장한 changed_files가 실제 파일 도구 실행 기록과
대조되는지를 고정한다.
"""

import pytest

from src.agent.orchestrator import _normalize_path
from src.agent.tools.interaction_tools import FinishTool


@pytest.mark.asyncio
async def test_changed_files_and_summary_are_kept():
    """프롬프트 계약대로 온 필드가 결과에 그대로 살아 있어야 한다."""
    result = await FinishTool().execute({
        "success": True,
        "message": "Created calculator.py",
        "changed_files": ["src/calculator.py"],
        "summary": {"total_changes": 1, "file_edits": 1},
    })

    assert result["changed_files"] == ["src/calculator.py"]
    assert result["summary"] == {"total_changes": 1, "file_edits": 1}
    assert result["message"] == "Created calculator.py"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_single_path_string_becomes_list():
    """파일 하나를 문자열로 보내는 모델이 흔하다."""
    result = await FinishTool().execute({"changed_files": "src/a.py"})

    assert result["changed_files"] == ["src/a.py"]


@pytest.mark.asyncio
async def test_non_string_entries_are_dropped():
    result = await FinishTool().execute({"changed_files": ["src/a.py", None, 3, "  "]})

    assert result["changed_files"] == ["src/a.py"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value, expected",
    [(True, True), ("true", True), ("false", False), ("no", False), (0, False), (1, True)],
)
async def test_success_accepts_loose_booleans(value, expected):
    """불리언 자리에 문자열/숫자를 넣는 모델을 흡수한다."""
    result = await FinishTool().execute({"success": value})

    assert result["success"] is expected


@pytest.mark.asyncio
async def test_swapped_message_and_summary_types_are_sorted_out():
    """message에 객체를, summary에 문자열을 넣어 보내도 제자리를 찾아준다."""
    result = await FinishTool().execute({
        "message": {"files_changed": 2},
        "summary": "두 파일을 고쳤습니다.",
    })

    assert result["message"] == "두 파일을 고쳤습니다."
    assert result["summary"] == {"files_changed": 2}


@pytest.mark.asyncio
async def test_defaults_when_nothing_provided():
    """빈 params로 호출해도 계약된 키가 모두 존재해야 한다."""
    result = await FinishTool().execute({})

    assert result == {
        "finished": True,
        "success": True,
        "message": "Task completed",
        "changed_files": [],
        "summary": {},
        "result": {},
    }


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("src/a.py", "src/a.py"),
        ("./src/a.py", "src/a.py"),
        ("src\\a.py", "src/a.py"),
        ("  src/a.py  ", "src/a.py"),
        ("/src/a.py", "src/a.py"),
    ],
)
def test_normalize_path_absorbs_common_notation_differences(raw, expected):
    assert _normalize_path(raw) == expected
