"""Сборка приложения FastAPI.

uvicorn вызывает `create_app()` как фабрику (`--factory`); тесты вызывают её сами,
передавая свои настройки и управляемые часы.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import admin, auth, contests, emails, health, ideas, realtime, votes
from app.clock import Clock, SystemClock
from app.config import Settings
from app.db import create_engine, create_sessionmaker
from app.jobs import JobRunner
from app.i18n import translate, wants_english
from app.realtime import DeadlineTicker, Hub


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Ответ 422 как у FastAPI, но без поля `input` — присланного значения (D-038).

    Стандартный ответ повторяет присланное значение. Одиночный суррогат Юникода
    в нём не кодируется в UTF-8, и вместо 422 сервер падал с 500. Заодно в ответ
    не возвращается, например, присланный пароль.
    """
    errors = [{k: v for k, v in error.items() if k != "input"} for error in exc.errors()]
    if wants_english(request.headers.get("accept-language")):
        # Сообщения наших проверок («Value error, …») — на языке интерфейса (D-065).
        for error in errors:
            message = str(error.get("msg", ""))
            if message.startswith("Value error, "):
                error["msg"] = "Value error, " + translate(message.removeprefix("Value error, "))
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": jsonable_encoder(errors)},
    )


async def _http_error(request: Request, exc: StarletteHTTPException):
    """Как стандартный ответ FastAPI, но текст ошибки — на языке интерфейса (D-065)."""
    if wants_english(request.headers.get("accept-language")):
        detail = exc.detail
        if isinstance(detail, str):
            detail = translate(detail)
        elif isinstance(detail, dict) and isinstance(detail.get("message"), str):
            detail = {**detail, "message": translate(detail["message"])}
        exc = StarletteHTTPException(status_code=exc.status_code, detail=detail, headers=exc.headers)
    return await http_exception_handler(request, exc)


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = create_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Тесты HTTP-запросов lifespan не запускают и управляют фоновыми задачами сами.
        app.state.deadlines.start()
        app.state.jobs.start()
        yield
        await app.state.jobs.stop()
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
    app.state.jobs = JobRunner(
        app.state.sessionmaker, app.state.clock, app.state.hub, settings.jobs_max_sleep_seconds
    )
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(contests.router)
    app.include_router(ideas.router)
    app.include_router(votes.router)
    app.include_router(emails.router)
    app.include_router(realtime.router)
    return app
