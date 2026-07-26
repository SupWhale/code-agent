"""AgentOrchestrator.execute_task() 단위 테스트

- finish 자체 성공 보고를 실제 실행 증거와 대조하는 소프트 검증(verification)
- LLM 응답 파싱/요청 실패가 다음 시도의 대화 히스토리에 피드백되는지
"""

import pytest

from src.agent.executor import ToolExecutor
from src.agent.llm.base import AgentResponse
from src.agent.orchestrator import AgentOrchestrator
from src.agent.security.validator import SecurityValidator


class _ScriptedLLMClient:
    """미리 정해둔 AgentResponse(혹은 예외)를 순서대로 돌려주는 가짜 LLM 클라이언트."""

    def __init__(self, script):
        self.model = "fake-model"
        self._script = list(script)
        self.received_histories = []

    async def get_next_actions_async(self, conversation_history, workspace_path):
        self.received_histories.append(list(conversation_history))
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def test_connection(self) -> bool:
        return True

    def check_model_available(self) -> bool:
        return True


def _make_orchestrator(tmp_path, llm_client):
    security = SecurityValidator(workspace_path=str(tmp_path), strict_mode=True)
    executor = ToolExecutor(workspace_path=str(tmp_path))
    return AgentOrchestrator(
        llm_client=llm_client,
        executor=executor,
        security=security,
        max_iterations=5,
        max_failures=3,
    )


async def _run(orchestrator, tmp_path):
    events = []
    async for event in orchestrator.execute_task(
        task_id="t1", user_request="do something", workspace_path=str(tmp_path)
    ):
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_verification_flags_suspicious_success(tmp_path):
    """이전 액션이 실패했는데도 finish가 success=true를 주장하면 suspicious=True."""
    llm = _ScriptedLLMClient([
        AgentResponse(
            reasoning="try reading a file that doesn't exist",
            actions=[{"tool": "read_file", "params": {"path": "src/missing.txt"}}],
            raw_response="...",
        ),
        AgentResponse(
            reasoning="claim done anyway",
            actions=[{"tool": "finish", "params": {"success": True, "message": "done"}}],
            raw_response="...",
        ),
    ])
    orchestrator = _make_orchestrator(tmp_path, llm)

    events = await _run(orchestrator, tmp_path)

    completed = [e for e in events if e["type"] == "task_completed"][0]
    assert completed["verification"]["suspicious"] is True
    assert completed["verification"]["action_failure_count"] == 1
    # 소프트 검증이므로 claimed_success 자체는 뒤집지 않는다
    assert completed["success"] is True


@pytest.mark.asyncio
async def test_verification_not_suspicious_when_clean(tmp_path):
    """실패 없이 바로 finish하면 suspicious=False."""
    llm = _ScriptedLLMClient([
        AgentResponse(
            reasoning="done immediately",
            actions=[{"tool": "finish", "params": {"success": True, "message": "done"}}],
            raw_response="...",
        ),
    ])
    orchestrator = _make_orchestrator(tmp_path, llm)

    events = await _run(orchestrator, tmp_path)

    completed = [e for e in events if e["type"] == "task_completed"][0]
    assert completed["verification"]["suspicious"] is False
    assert completed["verification"]["action_failure_count"] == 0


@pytest.mark.asyncio
async def test_parse_failure_is_fed_back_into_history(tmp_path):
    """LLM 요청/파싱 실패가 다음 호출의 conversation_history에 안내 메시지로 남는지."""
    llm = _ScriptedLLMClient([
        ValueError("Failed to parse LLM response as JSON"),
        AgentResponse(
            reasoning="retry with valid json",
            actions=[{"tool": "finish", "params": {"success": True, "message": "done"}}],
            raw_response="...",
        ),
    ])
    orchestrator = _make_orchestrator(tmp_path, llm)

    await _run(orchestrator, tmp_path)

    assert len(llm.received_histories) == 2
    second_call_history = llm.received_histories[1]
    combined = " ".join(m["content"] for m in second_call_history)
    assert "could not be processed" in combined
    assert "Failed to parse LLM response as JSON" in combined
