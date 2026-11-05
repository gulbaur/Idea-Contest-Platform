"""Кто что может — в одном месте (D-062).

Три роли с разделением обязанностей:
- сотрудник (`employee`) участвует в конкурсах;
- организатор (`organizer`) создаёт и ведёт конкурсы, не участвует (D-005);
- администратор (`admin`) управляет сотрудниками и ролями; конкурсов не ведёт и в них не участвует.
Тот, кто ведёт конкурсы, не создаёт учётных записей — и наоборот: так нельзя завести
«сотрудника» и проголосовать от его имени в своём же конкурсе.
"""

from fastapi import HTTPException, status

from app.models import Role, User


def can_manage_contests(user: User) -> bool:
    return user.role == Role.ORGANIZER


def can_manage_users(user: User) -> bool:
    return user.role == Role.ADMIN


def ensure_admin(user: User) -> None:
    if not can_manage_users(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Действие доступно только администратору")
