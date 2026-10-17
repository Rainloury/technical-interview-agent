"""Version 1 route composition."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")


@router.get("/ping", tags=["meta"])
async def ping() -> dict[str, str]:
    """Confirm the versioned API router is mounted."""

    return {"status": "ok"}
