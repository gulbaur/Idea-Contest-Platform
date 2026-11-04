# Браузерные E2E (D-055): официальный образ Playwright с Chromium нужной версии.
# Запускается в проверочной среде (compose.check.yaml) скриптом scripts/check.*.
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /e2e
COPY requirements.txt .
RUN pip install --break-system-packages -r requirements.txt
COPY . .
CMD ["pytest"]
