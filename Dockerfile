FROM python:3.12-slim-bookworm

ARG APP_UID=10001
ARG APP_GID=10001

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    TRIALGUARD_CACHE_DIR=/var/lib/trialguard/cache \
    TRIALGUARD_RUNS_DIR=/var/lib/trialguard/runs

RUN groupadd --gid "${APP_GID}" trialguard \
    && useradd \
        --uid "${APP_UID}" \
        --gid "${APP_GID}" \
        --create-home \
        --shell /usr/sbin/nologin \
        trialguard \
    && mkdir -p /app "${TRIALGUARD_CACHE_DIR}" "${TRIALGUARD_RUNS_DIR}" \
    && chown -R trialguard:trialguard /app /var/lib/trialguard

WORKDIR /app

COPY --chown=trialguard:trialguard . .

RUN test -f pyproject.toml \
    && python -m pip install .

USER trialguard:trialguard

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
