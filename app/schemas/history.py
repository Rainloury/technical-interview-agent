"""历史分页响应模型。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

HistoryType = Literal["resume", "qa", "interview", "wrong_question"]


class HistoryItem(BaseModel):
    """一条所有者范围内的历史记录。"""

    id: UUID
    type: HistoryType
    title: str
    state: str
    updated_at: datetime


class HistoryPage(BaseModel):
    """供 Web 和未来客户端使用的稳定游标页。"""

    items: list[HistoryItem]
    next_cursor: str | None
