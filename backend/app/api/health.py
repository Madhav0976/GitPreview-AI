from datetime import datetime, timezone
from fastapi import APIRouter
from app.services.github_client import rate_limit_tracker

router = APIRouter()

START_TIME = datetime.now(timezone.utc)


@router.get("/health", tags=["health"])
def health():
    uptime = datetime.now(timezone.utc) - START_TIME
    return {
        "status": "ok",
        "version": "0.1.0",
        "uptime_seconds": int(uptime.total_seconds()),
        "github_rate_limit": rate_limit_tracker.get_status(),
    }
