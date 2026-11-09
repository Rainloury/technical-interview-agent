"""问答用例的冻结契约常量。"""

from __future__ import annotations

QA_MODEL_TIER = "DEFAULT"
QA_PROMPT_VERSION = "1.1.0"
QA_STREAM_URL_PREFIX = "/api/v1/qa"


def qa_stream_url(request_id: str) -> str:
    return f"{QA_STREAM_URL_PREFIX}/{request_id}/stream"
