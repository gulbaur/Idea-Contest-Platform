"""Почтовая заглушка: просмотр писем (D-016, D-045)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import CurrentUserDep, DbSession
from app.models import Contest, Email, Role, User

router = APIRouter(prefix="/api", tags=["emails"])


class RecipientOut(BaseModel):
    id: int
    display_name: str


class EmailOut(BaseModel):
    id: int
    contest_id: int
    contest_topic: str
    recipient: RecipientOut
    to_address: str
    kind: str
    subject: str
    body: str
    created_at: datetime


@router.get("/emails", response_model=list[EmailOut])
async def list_emails(
    current: CurrentUserDep,
    db: DbSession,
    contest_id: Annotated[int | None, Query(ge=1, le=2_147_483_647)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[EmailOut]:
    """Участник видит только свои письма; организатор — журнал всех писем."""
    statement = (
        select(Email, Contest.topic, User.display_name)
        .join(Contest, Contest.id == Email.contest_id)
        .join(User, User.id == Email.recipient_id)
        .order_by(Email.created_at.desc(), Email.id.desc())
        .limit(limit)
    )
    if current.user.role != Role.ORGANIZER:
        statement = statement.where(Email.recipient_id == current.user.id)
    if contest_id is not None:
        statement = statement.where(Email.contest_id == contest_id)
    return [
        EmailOut(
            id=email.id,
            contest_id=email.contest_id,
            contest_topic=topic,
            recipient=RecipientOut(id=email.recipient_id, display_name=name),
            to_address=email.to_address,
            kind=email.kind,
            subject=email.subject,
            body=email.body,
            created_at=email.created_at,
        )
        for email, topic, name in (await db.execute(statement)).all()
    ]
