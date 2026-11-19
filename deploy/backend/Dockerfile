# syntax=docker/dockerfile:1.7
# Image de l'API et du worker (Phase 6). Versions Python figées par uv.lock (torch CPU).
# Les modèles ne sont pas copiés : ils sont montés en lecture seule dans /app/models.
FROM python:3.11.18-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /uvx /bin/

ENV PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    DARIJACARE_ROOT=/app \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# 1. Dépendances seules (couche réutilisée tant que uv.lock ne change pas).
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project \
        --extra nlu --extra rag --extra api --extra cpu

# 2. Code, configuration, base de connaissances, migrations et rapports versionnés
#    (voisines du filtre d'intention, métriques du modèle servi).
COPY src ./src
COPY configs ./configs
COPY kb ./kb
COPY migrations ./migrations
COPY alembic.ini ./
COPY reports ./reports
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra nlu --extra rag --extra api --extra cpu

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin darijacare
USER darijacare

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=600s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

ENTRYPOINT ["python", "-m", "darijacare.api.cli"]
CMD ["start"]
