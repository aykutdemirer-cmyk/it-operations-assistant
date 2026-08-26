from fastapi import APIRouter, HTTPException

from app.db.connection import check_db_connection

router = APIRouter(prefix="/api")


@router.get("/health")
def get_health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
async def get_health_db() -> dict[str, str]:
    try:
        await check_db_connection()
    except OSError as exc:
        raise HTTPException(
            status_code=503, detail={"database": "unreachable"}
        ) from exc
    return {"database": "ok"}
