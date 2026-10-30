# Один Dockerfile, две целевые стадии:
#   runtime — рабочий backend (compose-сервис backend);
#   test    — тот же код плюс тестовые зависимости (compose-сервис tests).
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt


FROM base AS test
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY . .
CMD ["pytest"]


FROM base AS runtime
COPY . .
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
# Миграции и демо-аккаунты применяются идемпотентно при каждом старте (D-027).
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]
