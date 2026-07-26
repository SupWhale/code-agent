"""Shared FastAPI response classes."""

import json
from typing import Any

from fastapi.responses import JSONResponse


class UnicodeJSONResponse(JSONResponse):
    """기본 JSONResponse는 비-ASCII 문자를 \\uXXXX로 이스케이프한다 — 한글 응답을
    사람이 읽을 수 있는 그대로 내려주기 위해 ensure_ascii=False로 오버라이드."""

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")
