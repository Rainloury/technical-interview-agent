"""Version 1 route composition."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.history import router as history_router
from app.api.v1.interviews import reviews_router
from app.api.v1.interviews import router as interviews_router
from app.api.v1.privacy import router as privacy_router
from app.api.v1.qa import router as qa_router
from app.api.v1.resumes import router as resumes_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(dashboard_router)
router.include_router(history_router)
router.include_router(interviews_router)
router.include_router(reviews_router)
router.include_router(privacy_router)
router.include_router(qa_router)
router.include_router(resumes_router)


@router.get("/ping", tags=["meta"])
async def ping() -> dict[str, str]:
    """Confirm the versioned API router is mounted."""

    return {"status": "ok"}
