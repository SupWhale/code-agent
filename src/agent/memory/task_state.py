"""
Task State Management

Tracks the state of an agent task execution.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """작업 상태"""
    PENDING = "pending"       # 대기 중
    RUNNING = "running"       # 실행 중
    COMPLETED = "completed"   # 완료
    FAILED = "failed"         # 실패


@dataclass
class TaskState:
    """
    작업 상태

    에이전트 작업의 현재 상태를 추적합니다.
    """
    task_id: str
    user_request: str
    workspace_path: str
    status: TaskStatus = TaskStatus.PENDING

    # 실행 결과
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    # 반복 히스토리
    iterations: List[Dict[str, Any]] = field(default_factory=list)

    # 시간 추적
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def start(self) -> None:
        """작업 시작"""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now()
        logger.info(f"Task {self.task_id} started")

    def complete(self, result: Dict[str, Any]) -> None:
        """작업 완료"""
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now()
        logger.info(f"Task {self.task_id} completed")

    def fail(self, error: str) -> None:
        """작업 실패"""
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()
        logger.error(f"Task {self.task_id} failed: {error}")

    def add_iteration(
        self,
        iteration: int,
        reasoning: Optional[str],
        actions: List[Dict],
        results: List[Dict]
    ) -> None:
        """반복 기록 추가"""
        self.iterations.append({
            "iteration": iteration,
            "reasoning": reasoning,
            "actions": actions,
            "results": results,
            "timestamp": datetime.now().isoformat()
        })

    def get_duration(self) -> Optional[float]:
        """실행 시간 (초) 반환"""
        if not self.started_at:
            return None

        end_time = self.completed_at or datetime.now()
        return (end_time - self.started_at).total_seconds()

    def get_iteration_count(self) -> int:
        """반복 횟수 반환"""
        return len(self.iterations)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "task_id": self.task_id,
            "user_request": self.user_request,
            "workspace_path": self.workspace_path,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "iterations": self.iterations,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.get_duration()
        }

    def __repr__(self) -> str:
        return (
            f"<TaskState id={self.task_id} status={self.status.value} "
            f"iterations={self.get_iteration_count()}>"
        )
