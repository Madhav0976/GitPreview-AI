from fastapi import APIRouter
from datetime import datetime

router = APIRouter()

START_TIME = datetime.utcnow()

@router.get("/health", tags=["health"])
def health():
    uptime = datetime.utcnow() - START_TIME
    return {
        "status": "ok",
        "version": "0.1.0",
        "uptime_seconds": int(uptime.total_seconds()),
    }
