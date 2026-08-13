"""
Agent Orchestrator

Main orchestrator that connects LLM and tools to execute agent tasks.
"""

from typing import Any, Dict, List, Optional, AsyncIterator
import logging

from .llm.base import AgentResponse, LLMClient
from .executor import ToolExecutor
from .memory.conversation import ConversationMemory
from .memory.task_state import TaskState, TaskStatus
from .security.validator import SecurityValidator, SecurityError

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    에이전트 메인 오케스트레이터

    LLM과 도구를 연결하여 작업을 실행합니다.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        executor: ToolExecutor,
        security: SecurityValidator,
        max_iterations: int = 20,      # 무한 루프 방지
        max_failures: int = 3           # 연속 실패 허용 횟수
    ):
        """
        Args:
            llm_client: 기본으로 사용할 LLM 클라이언트 (전략). execute_task()에
                llm_client를 넘기면 그 태스크에 한해 이걸 대신 사용한다.
            executor: 도구 실행 엔진
            security: 보안 검증기
            max_iterations: 최대 반복 횟수
            max_failures: 최대 연속 실패 횟수
        """
        self.llm = llm_client
        self.executor = executor
        self.security = security
        self.max_iterations = max_iterations
        self.max_failures = max_failures

        logger.info(
            f"AgentOrchestrator initialized: "
            f"max_iterations={max_iterations}, max_failures={max_failures}"
        )

    async def execute_task(
        self,
        task_id: str,
        user_request: str,
        workspace_path: str,
        llm_client: Optional[LLMClient] = None
    ) -> AsyncIterator[Dict]:
        """
        태스크 실행 (스트리밍)

        Args:
            task_id: 태스크 ID
            user_request: 사용자 요청
            workspace_path: 작업 디렉토리
            llm_client: 이 태스크에 한해 기본 llm_client 대신 사용할 LLM 클라이언트
                (모델별 A/B 테스트 등). 생략하면 생성자에서 주입된 기본값을 쓴다.

        Yields:
            상태 업데이트 딕셔너리
        """
        active_llm = llm_client or self.llm

        # 초기화
        memory = ConversationMemory(max_history=20)
        state = TaskState(
            task_id=task_id,
            user_request=user_request,
            workspace_path=workspace_path,
            status=TaskStatus.PENDING,
            model=active_llm.model
        )

        state.start()

        # 태스크 전용 executor 생성 (세션별 workspace 격리)
        task_executor = ToolExecutor(workspace_path=workspace_path)

        # 초기 사용자 메시지
        memory.add_user_message(user_request)

        consecutive_failures = 0

        # 소프트 검증용 상태 추적 — finish 자체 보고를 실제 증거와 대조하기 위함.
        # 차단하지는 않고 기록만 한다 (run_tests 인프라 자체가 아직 불안정하기 때문).
        run_tests_last_success: Optional[bool] = None
        # 마지막 run_tests의 outcome("passed"/"failed"/"no_tests"/"error").
        # success 불리언만으로는 "테스트가 돌아서 실패한 것"과 "테스트가 아예
        # 없어서 검증을 못 한 것"이 구분되지 않아 따로 남긴다.
        run_tests_last_outcome: Optional[str] = None
        action_failure_count = 0

        try:
            for iteration in range(1, self.max_iterations + 1):
                logger.info(
                    f"[Task {task_id}] Iteration {iteration}/{self.max_iterations}"
                )

                # 1. LLM에게 다음 액션 요청 (스트리밍 — 토큰이 오는 대로 llm_token
                # 이벤트로 흘려보내, 추론이 오래 걸려도 SSE/WebSocket이 침묵하지
                # 않게 한다. 논스트리밍 백엔드는 LLMClient.stream_next_actions()
                # 기본 구현이 "done" 이벤트 하나만 내는 것으로 자동 대체된다.)
                yield {
                    "type": "iteration_start",
                    "iteration": iteration,
                    "message": "Thinking..."
                }

                agent_response: Optional[AgentResponse] = None
                try:
                    async for chunk in active_llm.stream_next_actions(
                        conversation_history=memory.get_history(),
                        workspace_path=workspace_path
                    ):
                        if chunk["type"] == "token":
                            yield {
                                "type": "llm_token",
                                "iteration": iteration,
                                "content": chunk["content"]
                            }
                        elif chunk["type"] == "done":
                            agent_response = chunk["response"]
                except Exception as e:
                    logger.error(f"[Task {task_id}] LLM request failed: {e}")
                    yield {
                        "type": "error",
                        "message": f"LLM request failed: {e}"
                    }
                    consecutive_failures += 1

                    # 실패한 응답도 히스토리에 남겨서 모델이 재시도할 때 "방금 응답이
                    # 거부당했다"는 걸 알 수 있게 한다 — 이게 없으면 같은 실수(예: JSON
                    # 파싱 자체가 깨지는 응답)를 인지하지 못한 채 그대로 반복한다.
                    memory.add_user_message(
                        f"Your previous response could not be processed: {e}. "
                        f"Respond again with ONLY one valid JSON object — no markdown, "
                        f"no code fences, all strings properly escaped."
                    )

                    if consecutive_failures >= self.max_failures:
                        raise RuntimeError(
                            f"Too many consecutive LLM failures ({consecutive_failures})"
                        )

                    continue

                # 추론 과정 전송 (디버깅용)
                if agent_response.reasoning:
                    yield {
                        "type": "reasoning",
                        "content": agent_response.reasoning
                    }
                    logger.info(
                        f"[Task {task_id}] Reasoning: "
                        f"{agent_response.reasoning[:100]}..."
                    )

                # LLM 응답을 메모리에 추가
                memory.add_assistant_message(agent_response.raw_response)

                # 2. 각 액션 실행
                action_results = []

                for action_idx, action in enumerate(agent_response.actions):
                    tool_name = action.get("tool")
                    params = action.get("params", {})

                    if not tool_name:
                        logger.warning(f"[Task {task_id}] Action without tool name: {action}")
                        continue

                    logger.info(f"[Task {task_id}] Executing tool: {tool_name}")

                    yield {
                        "type": "action_start",
                        "tool": tool_name,
                        "params": params
                    }

                    try:
                        # 보안 검증
                        self.security.validate_action(
                            tool_name,
                            params,
                            workspace_path
                        )

                        # 도구 실행 (태스크 전용 executor 사용)
                        result = await task_executor.execute(tool_name, params)

                        action_results.append({
                            "tool": tool_name,
                            "success": True,
                            "result": result
                        })

                        # 성공 시 실패 카운터 리셋
                        consecutive_failures = 0

                        if tool_name == "run_tests" and isinstance(result, dict):
                            run_tests_last_outcome = result.get("outcome")
                            if run_tests_last_outcome == "no_tests":
                                # 테스트가 아예 없었으면 통과도 실패도 아니다.
                                # False로 두면 "테스트가 돌아서 실패했다"와 구분이
                                # 안 되므로 증거 없음(None)으로 남긴다.
                                run_tests_last_success = None
                            else:
                                run_tests_last_success = bool(result.get("success"))

                        yield {
                            "type": "action_success",
                            "tool": tool_name,
                            "params": params,
                            "result": result
                        }

                        # finish 도구면 종료
                        if tool_name == "finish":
                            finish_result = result if isinstance(result, dict) else {}
                            claimed_success = finish_result.get("success", True)

                            # 소프트 검증: 모델의 자체 성공 보고를 실제 증거와 대조만
                            # 하고, 판단 자체를 뒤집지는 않는다 — run_tests 인프라가
                            # 아직 불안정해서 하드 게이트는 오탐 위험이 크다.
                            verification: Dict[str, Any] = {
                                "claimed_success": claimed_success,
                                "run_tests_last_success": run_tests_last_success,
                                "run_tests_last_outcome": run_tests_last_outcome,
                                "action_failure_count": action_failure_count,
                                "suspicious": bool(
                                    claimed_success and (
                                        run_tests_last_success is False
                                        or action_failure_count > 0
                                    )
                                ),
                                # 테스트가 없어 아무 검증도 못 한 채 성공을 주장한
                                # 경우. suspicious(= 반증이 있음)와는 구분되는,
                                # "근거 없음" 신호다.
                                "unverified": bool(
                                    claimed_success
                                    and run_tests_last_success is None
                                ),
                            }

                            state.complete(finish_result, verification=verification)

                            yield {
                                "type": "task_completed",
                                "success": claimed_success,
                                "message": finish_result.get(
                                    "message",
                                    "Task completed"
                                ),
                                "verification": verification,
                                "summary": state.to_dict()
                            }

                            return

                    except SecurityError as e:
                        # 보안 위반 - 즉시 중단
                        logger.error(
                            f"[Task {task_id}] Security violation: {e}"
                        )

                        action_results.append({
                            "tool": tool_name,
                            "success": False,
                            "error": f"Security violation: {e}",
                            "error_type": "SecurityError"
                        })

                        yield {
                            "type": "security_violation",
                            "tool": tool_name,
                            "error": str(e)
                        }

                        raise  # 보안 위반은 즉시 중단

                    except Exception as e:
                        logger.error(
                            f"[Task {task_id}] Tool execution failed: {e}"
                        )

                        action_results.append({
                            "tool": tool_name,
                            "success": False,
                            "error": str(e),
                            "error_type": type(e).__name__
                        })

                        consecutive_failures += 1
                        action_failure_count += 1

                        if tool_name == "run_tests":
                            run_tests_last_success = False

                        yield {
                            "type": "action_failed",
                            "tool": tool_name,
                            "error": str(e)
                        }

                        # 연속 실패 체크
                        if consecutive_failures >= self.max_failures:
                            raise RuntimeError(
                                f"Too many consecutive failures "
                                f"({consecutive_failures}). Aborting."
                            )

                # 3. 결과를 메모리에 추가 (user role로 추가해야 LLM이 인식)
                results_summary = self._format_results(action_results)
                memory.add_user_message(
                    f"Tool execution results:\n{results_summary}\n\n"
                    f"If all requested tasks are now complete, call the 'finish' tool with a summary message. "
                    f"If there are more steps needed, continue with the next action."
                )

                # 4. 상태 업데이트
                state.add_iteration(
                    iteration=iteration,
                    reasoning=agent_response.reasoning,
                    actions=agent_response.actions,
                    results=action_results
                )

            # 최대 반복 도달
            logger.warning(
                f"[Task {task_id}] Max iterations "
                f"({self.max_iterations}) reached"
            )

            state.fail(f"Max iterations ({self.max_iterations}) reached")

            yield {
                "type": "task_failed",
                "error": f"Max iterations ({self.max_iterations}) reached without completion",
                "summary": state.to_dict()
            }

        except Exception as e:
            logger.error(f"[Task {task_id}] Task failed: {e}")

            state.fail(str(e))

            yield {
                "type": "task_failed",
                "error": str(e),
                "summary": state.to_dict()
            }

    def _format_results(self, results: List[Dict]) -> str:
        """도구 실행 결과를 LLM이 이해할 수 있는 형식으로 변환"""
        if not results:
            return "No tools executed."

        formatted = []

        for result in results:
            tool = result["tool"]

            if result["success"]:
                # 성공
                result_preview = str(result["result"])[:200]
                formatted.append(f"✅ {tool}: {result_preview}")
            else:
                # 실패
                error = result.get("error", "Unknown error")
                error_type = result.get("error_type", "Error")
                formatted.append(f"❌ {tool}: {error_type} - {error}")

        return "\n".join(formatted)

    def __repr__(self) -> str:
        return (
            f"<AgentOrchestrator max_iterations={self.max_iterations} "
            f"max_failures={self.max_failures}>"
        )
