"""Сигналы реального времени по WebSocket (D-014, D-039, D-040).

Сигнал не содержит данных конкурса — только «перечитай снимок». Что именно видно
пользователю, решает REST-снимок, поэтому через WebSocket ничего не утекает.

- `Hub` знает открытые соединения и решает, кому отправить сигнал.
- `Connection` — одно соединение (одна вкладка) со своей очередью сигналов.
- `DeadlineTicker` — фоновая задача: в момент срока рассылает `phase_changed`.
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable, Iterable
from datetime import datetime

from fastapi import WebSocket
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.models import Contest, ContestParticipant, Role

log = logging.getLogger(__name__)

# Коды закрытия соединения (D-039). 4000–4999 — коды приложения.
CLOSE_BAD_MESSAGE = 4400
CLOSE_UNAUTHORIZED = 4401
CLOSE_AUTH_TIMEOUT = 4408
CLOSE_TRY_AGAIN = 1013  # стандартный код «перегружен, подключитесь позже»


class Connection:
    """Одна вкладка. Сигналы копятся в очереди; отправляет их отдельная задача `run()`."""

    def __init__(
        self,
        websocket: WebSocket,
        *,
        user_id: int,
        role: str,
        session_id: int,
        expires_at: datetime,
        queue_limit: int,
    ) -> None:
        self.websocket = websocket
        self.user_id = user_id
        self.role = role
        self.session_id = session_id
        self.expires_at = expires_at
        self._queue_limit = queue_limit
        # В очереди — сообщения (dict) или код закрытия (int), который всегда последний.
        self._queue: asyncio.Queue[dict | int] = asyncio.Queue()
        self.closing = False

    def send(self, message: dict) -> None:
        """Поставить сигнал в очередь, не дожидаясь отправки (не задерживает HTTP-ответ)."""
        if self.closing:
            return
        if self._queue.qsize() >= self._queue_limit:
            # Клиент не успевает читать — закрываем; он переподключится и перечитает снимок.
            self.close(CLOSE_TRY_AGAIN)
            return
        self._queue.put_nowait(message)

    def close(self, code: int) -> None:
        if not self.closing:
            self.closing = True
            self._queue.put_nowait(code)

    async def run(self) -> None:
        """Отправляет сигналы по порядку, пока соединение не закроется."""
        try:
            while True:
                item = await self._queue.get()
                if isinstance(item, int):
                    await self.websocket.close(code=item)
                    return
                await self.websocket.send_json(item)
        except Exception:  # noqa: BLE001 — клиент отключился во время отправки
            self.closing = True


class Hub:
    """Открытые соединения процесса и правила, кому отправлять сигнал (D-039)."""

    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], clock: Clock, queue_limit: int
    ) -> None:
        self._sessionmaker = sessionmaker
        self._clock = clock
        self._queue_limit = queue_limit
        self._connections: set[Connection] = set()
        # Список участников конкурса после создания не меняется (D-009) — его можно кешировать.
        self._participants: dict[int, frozenset[int]] = {}
        # События фоновых задач (сроки, задания): их будит появление конкурса с новыми сроками.
        self._contest_created_events: list[asyncio.Event] = []

    @property
    def connections(self) -> frozenset[Connection]:
        return frozenset(self._connections)

    def contest_created_event(self) -> asyncio.Event:
        """Новое событие, которое устанавливается при каждом создании конкурса."""
        event = asyncio.Event()
        self._contest_created_events.append(event)
        return event

    def register(
        self,
        websocket: WebSocket,
        *,
        user_id: int,
        role: str,
        session_id: int,
        expires_at: datetime,
    ) -> Connection:
        connection = Connection(
            websocket,
            user_id=user_id,
            role=role,
            session_id=session_id,
            expires_at=expires_at,
            queue_limit=self._queue_limit,
        )
        self._connections.add(connection)
        return connection

    def unregister(self, connection: Connection) -> None:
        self._connections.discard(connection)

    def close_session(self, session_id: int) -> None:
        """Выход из системы закрывает соединения только этой сессии (вкладки)."""
        for connection in list(self._connections):
            if connection.session_id == session_id:
                connection.close(CLOSE_UNAUTHORIZED)

    def close_user(self, user_id: int, *, keep_session: int | None = None) -> None:
        """Отключение, смена роли или пароля (D-062): все вкладки пользователя выходят сразу.

        `keep_session` — вкладка, в которой человек сам сменил пароль, остаётся в системе.
        """
        for connection in list(self._connections):
            if connection.user_id == user_id and connection.session_id != keep_session:
                connection.close(CLOSE_UNAUTHORIZED)

    async def contest_changed(
        self, contest_id: int, revision: int, *, restrict_to: int | None = None
    ) -> None:
        """Изменение в конкурсе зафиксировано в БД. Вызывать только после COMMIT.

        `restrict_to=user_id` — изменение видно только организаторам и этому пользователю
        (подача и правка идеи, голос); `None` — всем участникам конкурса и организаторам.
        """
        message = {"type": "contest_changed", "contest_id": contest_id, "revision": revision}
        if restrict_to is not None:
            self._deliver(message, lambda c: c.role == Role.ORGANIZER or c.user_id == restrict_to)
        else:
            await self._deliver_to_contest(contest_id, message)

    async def phase_changed(self, contest_id: int, revision: int) -> None:
        message = {"type": "phase_changed", "contest_id": contest_id, "revision": revision}
        await self._deliver_to_contest(contest_id, message)

    def contest_created(self, contest_id: int, participant_ids: Iterable[int]) -> None:
        """Новый конкурс: обновить список конкурсов у его участников и организаторов."""
        participants = frozenset(participant_ids)
        self._participants[contest_id] = participants
        self._deliver(
            {"type": "contests_changed"},
            lambda c: c.role == Role.ORGANIZER or c.user_id in participants,
        )
        for event in self._contest_created_events:
            event.set()

    def schedule_changed(self, contest_id: int) -> None:
        """Выполнено задание расписания — обновить экран организатора (D-051)."""
        self._deliver(
            {"type": "schedule_changed", "contest_id": contest_id},
            lambda c: c.role == Role.ORGANIZER,
        )

    def mail_changed(self, recipient_ids: Iterable[int]) -> None:
        """Появились письма: обновить «Входящие» получателей и журнал рассылки (D-045, D-063)."""
        recipients = frozenset(recipient_ids)
        if recipients:
            self._deliver(
                {"type": "mail_changed"},
                lambda c: c.role in (Role.ORGANIZER, Role.ADMIN) or c.user_id in recipients,
            )

    async def _deliver_to_contest(self, contest_id: int, message: dict) -> None:
        participants = await self._participants_of(contest_id)
        self._deliver(message, lambda c: c.role == Role.ORGANIZER or c.user_id in participants)

    async def _participants_of(self, contest_id: int) -> frozenset[int]:
        cached = self._participants.get(contest_id)
        if cached is None:
            async with self._sessionmaker() as db:
                rows = await db.scalars(
                    select(ContestParticipant.user_id).where(
                        ContestParticipant.contest_id == contest_id
                    )
                )
                cached = self._participants[contest_id] = frozenset(rows.all())
        return cached

    def _deliver(self, message: dict, accept: Callable[[Connection], bool]) -> None:
        now = self._clock.now()
        for connection in list(self._connections):
            if now >= connection.expires_at:
                connection.close(CLOSE_UNAUTHORIZED)  # сессия истекла — права больше нет
            elif accept(connection):
                connection.send(message)


class DeadlineTicker:
    """В момент срока рассылает `phase_changed` (D-040).

    Фаза вычисляется по часам, и в момент срока в БД ничего не меняется — без этой
    задачи клиенты не узнали бы, что раунд закрылся.
    """

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        clock: Clock,
        hub: Hub,
        max_sleep_seconds: float,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._clock = clock
        self._hub = hub
        self._max_sleep = max_sleep_seconds
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        wakeup = self._hub.contest_created_event()
        self._task = asyncio.create_task(self._run(self._clock.now(), wakeup))

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def tick(self, since: datetime, now: datetime) -> list[int]:
        """Объявляет сроки из промежутка (since, now]; возвращает номера конкурсов.

        Срок, равный `now`, уже наступил: ровно в момент срока раунд закрыт (D-007).
        """
        in_window = lambda column: (column > since) & (column <= now)  # noqa: E731
        async with self._sessionmaker() as db:
            rows = (
                await db.execute(
                    select(Contest.id, Contest.revision)
                    .where(or_(in_window(Contest.submission_deadline), in_window(Contest.voting_deadline)))
                    .order_by(Contest.id)
                )
            ).all()
        for contest_id, revision in rows:
            await self._hub.phase_changed(contest_id, revision)
        return [contest_id for contest_id, _ in rows]

    async def _seconds_until_next_deadline(self, now: datetime) -> float:
        async with self._sessionmaker() as db:
            nearest = [
                await db.scalar(select(func.min(column)).where(column > now))
                for column in (Contest.submission_deadline, Contest.voting_deadline)
            ]
        upcoming = [moment for moment in nearest if moment is not None]
        if not upcoming:
            return self._max_sleep
        return min(self._max_sleep, max(0.0, (min(upcoming) - now).total_seconds()))

    async def _run(self, since: datetime, wakeup: asyncio.Event) -> None:
        while True:
            # Сбрасываем до проверки: конкурс, созданный во время проверки, снова разбудит цикл.
            wakeup.clear()
            delay = self._max_sleep
            try:
                now = self._clock.now()
                await self.tick(since, now)
                since = now
                delay = await self._seconds_until_next_deadline(now)
            except Exception:  # noqa: BLE001 — например, БД недоступна; повторим позже
                log.exception("Ошибка рассылки сигналов о сроках")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(wakeup.wait(), timeout=delay)
