"""Сборка приложения FastAPI.

uvicorn вызывает `create_app()` как фабрику (`--factory`); тесты вызывают её сами,
передавая свои настройки и управляемые часы.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import auth, contests, health, ideas, realtime, votes
from app.clock import Clock, SystemClock
from app.config import Settings
from app.db import create_engine, create_sessionmaker
from app.realtime import DeadlineTicker, Hub


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Ответ 422 как у FastAPI, но без поля `input` — присланного значения (D-038).

    Стандартный ответ повторяет присланное значение. Одиночный суррогат Юникода
    в нём не кодируется в UTF-8, и вместо 422 сервер падал с 500. Заодно в ответ
    не возвращается, например, присланный пароль.
    """
    errors = [{k: v for k, v in error.items() if k != "input"} for error in exc.errors()]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": jsonable_encoder(errors)},
    )


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = create_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Тесты HTTP-запросов lifespan не запускают и управляют задачей сроков сами.
        app.state.deadlines.start()
        yield
        await app.state.deadlines.stop()
        await engine.dispose()

    app = FastAPI(title="Конкурс идей", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = create_sessionmaker(engine)
    app.state.clock = clock or SystemClock()
    app.state.hub = Hub(app.state.sessionmaker, app.state.clock, settings.ws_queue_limit)
    app.state.deadlines = DeadlineTicker(
        app.state.sessionmaker, app.state.clock, app.state.hub, settings.deadline_max_sleep_seconds
    )
    app.add_exception_handler(RequestValidationError, _validation_error)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(contests.router)
    app.include_router(ideas.router)
    app.include_router(votes.router)
    app.include_router(realtime.router)
    return app
