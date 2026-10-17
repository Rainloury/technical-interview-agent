"""Authenticated workspace endpoint."""

from fastapi import APIRouter

from app.api.dependencies import AuthDependency, SessionDependency
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import get_dashboard

router = APIRouter(tags=["workspace"])


@router.get("/dashboard", response_model=DashboardResponse)
async def read_dashboard(
    auth: AuthDependency,
    session: SessionDependency,
) -> DashboardResponse:
    """Return the current user's recent task and interview summaries."""

    return await get_dashboard(session, auth.user)
