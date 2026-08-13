"""CLI의 finish 이벤트 렌더링 회귀 테스트

시스템 프롬프트는 finish.params.summary를 통계 "객체"로 정의하는데
(prompts/system_prompt.txt), CLI는 그 값을 마크다운 "문자열"로 가정하고
rich.markdown.Markdown()에 그대로 넘기고 있었다. 에이전트가 프롬프트 계약대로
summary={"total_changes": 1, "file_edits": 1}을 보내자
`TypeError: Input data should be a string, not <class 'dict'>`로 CLI가 죽었다
(2026-08-13 실측).

작업 자체는 서버에서 성공했고 파일 동기화도 끝난 뒤였는데, 예외가 스트림 루프
밖으로 튀면서 finish 이후의 file_changed / task_completed 이벤트가 통째로
유실되고 종료 코드 1 — 성공한 작업이 실패로 보였다. 표시 문제가 동기화를
죽이지 않도록 렌더 실패는 이벤트 단위로 가둔다.
"""

import pytest

pytest.importorskip("typer", reason="CLI 의존성은 cli/requirements.txt에만 있음")
pytest.importorskip("rich", reason="CLI 의존성은 cli/requirements.txt에만 있음")

from rich.markdown import Markdown  # noqa: E402

from cli.main import _format_finish, _render_event, _run_ask  # noqa: E402


def test_dict_summary_renders_as_markdown_string():
    """프롬프트 계약대로 온 dict summary가 Markdown()을 통과해야 한다."""
    params = {
        "success": True,
        "message": "Created calculator.py with add, subtract, multiply, divide",
        "changed_files": ["src/calculator.py"],
        "summary": {"total_changes": 1, "file_edits": 1},
    }

    body = _format_finish(params, {"finished": True})

    assert isinstance(body, str)
    Markdown(body)  # 여기서 TypeError가 났었다
    assert "Created calculator.py" in body
    assert "src/calculator.py" in body
    assert "total_changes: 1" in body


def test_string_summary_still_supported():
    """모델이 summary를 문자열로 보내던 기존 동작도 유지."""
    body = _format_finish({"summary": "## 요약\n작업을 마쳤습니다."}, {})

    assert body.startswith("## 요약")


def test_message_wins_over_summary():
    """사람이 읽을 본문은 message다 — summary는 부가 정보로 붙는다."""
    body = _format_finish(
        {"message": "본문", "summary": {"files_changed": 2}},
        {},
    )

    assert body.splitlines()[0] == "본문"
    assert "files_changed: 2" in body


def test_falls_back_to_result_message_when_params_empty():
    """params가 비어도 도구 반환값에서 메시지를 건져낸다."""
    body = _format_finish({}, {"finished": True, "message": "Task completed"})

    assert body == "Task completed"


class _Boom:
    """렌더 도중 반드시 터지는 값."""

    def __str__(self):
        raise RuntimeError("렌더 폭발")

    __repr__ = __str__


def test_render_event_raises_on_unrenderable_event():
    """가드가 잡을 대상이 실제로 예외라는 전제를 고정."""
    with pytest.raises(RuntimeError):
        _render_event(
            {
                "type": "agent_event",
                "event": {"type": "action_success", "tool": "grep", "result": _Boom()},
            }
        )


@pytest.mark.asyncio
async def test_render_failure_does_not_abort_stream(monkeypatch):
    """한 이벤트의 렌더가 터져도 뒤 이벤트는 계속 처리돼야 한다."""
    events = [
        {
            "type": "agent_event",
            "event": {"type": "action_success", "tool": "grep", "result": _Boom()},
        },
        {"type": "agent_event", "event": {"type": "task_completed"}},
    ]
    consumed = []

    async def fake_run_agent(*args, **kwargs):
        for event in events:
            consumed.append(event)
            yield event

    class _FakeClient:
        run_agent = staticmethod(fake_run_agent)

    monkeypatch.setattr("cli.main._client", lambda: _FakeClient())
    monkeypatch.setattr("cli.main.config.get", lambda *a, **k: None)

    await _run_ask("session-1", "요청")  # typer.Exit이 나면 안 된다

    assert len(consumed) == 2
