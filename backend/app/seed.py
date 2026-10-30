"""Демонстрационные аккаунты. Запуск: `python -m app.seed` (идемпотентно).

Все данные синтетические; адреса в зарезервированном домене example.com.
"""

import asyncio

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock, SystemClock
from app.config import Settings
from app.db import create_engine, create_sessionmaker
from app.models import Role, User
from app.security import hash_password

# (логин, отображаемое имя, роль)
DEMO_USERS: list[tuple[str, str, Role]] = [
    ("organizer", "Организатор", Role.ORGANIZER),
    ("anna", "Анна Смирнова", Role.EMPLOYEE),
    ("boris", "Борис Котов", Role.EMPLOYEE),
    ("vera", "Вера Орлова", Role.EMPLOYEE),
    ("gleb", "Глеб Лебедев", Role.EMPLOYEE),
    ("dina", "Дина Ахметова", Role.EMPLOYEE),
]


async def seed_demo_users(session: AsyncSession, password: str, clock: Clock) -> int:
    """Создаёт недостающих демо-пользователей; возвращает число созданных."""
    now = clock.now()
    rows = [
        {
            "login": login,
            "display_name": name,
            "email": f"{login}@example.com",
            "role": role.value,
            "password_hash": hash_password(password),
            "created_at": now,
        }
        for login, name, role in DEMO_USERS
    ]
    # ON CONFLICT DO NOTHING: существующие аккаунты не трогаем, повторный запуск безопасен.
    result = await session.execute(
        insert(User).values(rows).on_conflict_do_nothing(index_elements=["login"]).returning(User.id)
    )
    created = len(result.all())
    await session.commit()
    return created


async def _main() -> None:
    settings = Settings()
    if not settings.seed_demo_data:
        print("seed: SEED_DEMO_DATA=false, демо-данные не создаются")
        return
    engine = create_engine(settings.database_url)
    try:
        async with create_sessionmaker(engine)() as session:
            created = await seed_demo_users(session, settings.demo_password, SystemClock())
        print(f"seed: создано демо-пользователей: {created}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
