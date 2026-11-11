"""需认证的工作区端点。"""

from typing import Annotated

from fastapi import APIRouter, Header

from app.dependencies import AuthDependency, SessionDependency, SettingsDependency
from app.errors import AppError
from app.schemas.dashboard import DashboardResponse, OperationalMetrics
from app.security import tokens_equal
from app.services.dashboard import get_dashboard
from app.services.metrics import operational_metrics

router = APIRouter(tags=["workspace"])


@router.get("/dashboard", response_model=DashboardResponse)
async def read_dashboard(
    auth: AuthDependency,
    session: SessionDependency,
) -> DashboardResponse:
    """返回当前用户近期的任务和面试摘要。"""

    return await get_dashboard(session, auth.user)


@router.get("/ops/metrics", response_model=OperationalMetrics)
async def read_operational_metrics(
    settings: SettingsDependency,
    session: SessionDependency,
    authorization: Annotated[str | None, Header()] = None,
) -> OperationalMetrics:
    """仅使用配置的 ops token 返回聚合发布指标。"""

    expected = settings.ops_metrics_token
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if expected is None or not supplied or not tokens_equal(supplied, expected.get_secret_value()):
        raise AppError(
            status_code=404,
            code="resource_not_found",
            message="资源不存在",
        )
    return await operational_metrics(session)
