"""Сборка приложения FastAPI.

uvicorn вызывает `create_app()` как фабрику (`--factory`); тесты вызывают её сами,
передавая свои настройки и управляемые часы.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, contests, health, ideas
from app.clock import Clock, SystemClock
from app.config import Settings
from app.db import create_engine, create_sessionmaker


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = create_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await engine.dispose()

    app = FastAPI(title="Конкурс идей", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = create_sessionmaker(engine)
    app.state.clock = clock or SystemClock()

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(contests.router)
    app.include_router(ideas.router)
    return app
