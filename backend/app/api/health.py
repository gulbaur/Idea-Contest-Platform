"""Проверка работоспособности: backend отвечает и БД доступна."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.deps import ClockDep, DbSession

router = APIRouter(prefix="/api", tags=["health"])


class HealthOut(BaseModel):
    status: str
    database: str
    server_time: datetime


@router.get("/health", response_model=HealthOut)
async def health(db: DbSession, clock: ClockDep) -> HealthOut:
    try:
        await db.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="База данных недоступна"
        ) from exc
    return HealthOut(status="ok", database="ok", server_time=clock.now())
