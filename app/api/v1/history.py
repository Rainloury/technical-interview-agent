"""Authenticated cursor-paginated history endpoint."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import AuthDependency, SessionDependency
from app.schemas.history import HistoryPage, HistoryType
from app.services.history import decode_cursor, list_history

router = APIRouter(tags=["history"])


@router.get("/history", response_model=HistoryPage)
async def read_history(
    auth: AuthDependency,
    session: SessionDependency,
    history_type: Annotated[HistoryType, Query(alias="type")] = "interview",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> HistoryPage:
    """List only the current user's history in a stable descending order."""

    parsed_cursor = decode_cursor(cursor) if cursor else None
    return await list_history(
        session,
        auth.user,
        history_type=history_type,
        limit=limit,
        cursor=parsed_cursor,
    )
