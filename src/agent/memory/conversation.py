"""
Conversation Memory Management

Manages conversation history for agent interactions.
Keeps track of messages between user, assistant, and system.
"""

from typing import List, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ConversationMemory:
    """
    대화 히스토리 관리

    사용자, 어시스턴트, 시스템 메시지를 관리합니다.
    """

    def __init__(self, max_history: int = 20):
        """
        Args:
            max_history: 최대 메시지 수 (오래된 메시지는 자동 삭제)
        """
        self.max_history = max_history
        self.messages: List[Dict[str, str]] = []
        self.logger = logging.getLogger(f"{__name__}.ConversationMemory")

    def add_user_message(self, content: str) -> None:
        """
        사용자 메시지 추가

        Args:
            content: 메시지 내용
        """
        self.messages.append({
            "role": "user",
            "content": content
        })
        self._trim_history()
        self.logger.debug(f"Added user message ({len(content)} chars)")

    def add_assistant_message(self, content: str) -> None:
        """
        어시스턴트 메시지 추가

        Args:
            content: 메시지 내용
        """
        self.messages.append({
            "role": "assistant",
            "content": content
        })
        self._trim_history()
        self.logger.debug(f"Added assistant message ({len(content)} chars)")

    def add_system_message(self, content: str) -> None:
        """
        시스템 메시지 추가

        Args:
            content: 메시지 내용
        """
        self.messages.append({
            "role": "system",
            "content": content
        })
        self._trim_history()
        self.logger.debug(f"Added system message ({len(content)} chars)")

    def get_history(self) -> List[Dict[str, str]]:
        """
        전체 히스토리 반환

        Returns:
            메시지 리스트 [{"role": "user", "content": "..."}, ...]
        """
        return self.messages.copy()

    def get_last_n_messages(self, n: int) -> List[Dict[str, str]]:
        """
        최근 N개 메시지 반환

        Args:
            n: 메시지 수

        Returns:
            최근 N개 메시지
        """
        return self.messages[-n:] if n > 0 else []

    def clear(self) -> None:
        """히스토리 초기화"""
        self.messages.clear()
        self.logger.info("Conversation history cleared")

    def count(self) -> int:
        """메시지 수 반환"""
        return len(self.messages)

    def _trim_history(self) -> None:
        """
        히스토리 크기 제한

        max_history를 초과하면 오래된 메시지 삭제
        """
        if len(self.messages) > self.max_history:
            removed = len(self.messages) - self.max_history
            self.messages = self.messages[-self.max_history:]
            self.logger.info(
                f"Trimmed conversation history: removed {removed} old messages"
            )

    def get_summary(self) -> Dict[str, int]:
        """
        히스토리 요약 정보

        Returns:
            {
                "total": 전체 메시지 수,
                "user": 사용자 메시지 수,
                "assistant": 어시스턴트 메시지 수,
                "system": 시스템 메시지 수
            }
        """
        summary = {
            "total": len(self.messages),
            "user": 0,
            "assistant": 0,
            "system": 0
        }

        for msg in self.messages:
            role = msg.get("role", "unknown")
            if role in summary:
                summary[role] += 1

        return summary

    def __len__(self) -> int:
        """len() 지원"""
        return len(self.messages)

    def __repr__(self) -> str:
        """문자열 표현"""
        summary = self.get_summary()
        return (
            f"<ConversationMemory total={summary['total']} "
            f"user={summary['user']} assistant={summary['assistant']} "
            f"system={summary['system']}>"
        )
