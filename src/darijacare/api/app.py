"""FastAPI application (``uvicorn darijacare.api.app:create_app --factory``).

At start-up, the models are loaded once (NLU v5, BGE-M3, Qdrant client) and the
reference tables are synchronised (model, decision configuration, knowledge base,
evaluation). The database schema itself comes from the Alembic migrations
(``python -m darijacare.api.cli db-upgrade``).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine
from starlette.concurrency import run_in_threadpool

from darijacare.api.db import make_engine, make_session_factory
from darijacare.api.deps import AppState
from darijacare.api.ratelimit import RateLimiter
from darijacare.api.reference import (
    ensure_model,
    served_model_info,
    sync_decision_config,
    sync_evaluations,
    sync_knowledge_base,
)
from darijacare.api.routes_public import router as public_router
from darijacare.api.routes_staff import router as staff_router
from darijacare.api.service import ChatService
from darijacare.api.settings import Settings
from darijacare.config import get_paths
from darijacare.pipeline import DarijaCareAssistant

log = logging.getLogger("darijacare.api")
access_log = logging.getLogger("darijacare.api.access")

API_VERSION = "0.4.0"
DESCRIPTION = """API de DarijaCare (projet académique).

Données **synthétiques**, fiches **fictives**.

* Clients anonymes : `POST /sessions` ou un premier `POST /chat` ouvre une session ; le jeton de
  session ne donne accès qu'à sa propre conversation.
* Conseillers, ML et administrateurs : `POST /auth/login` (jeton de 15 minutes), rôles vérifiés
  côté serveur (matrice du cahier des charges, Tableau 14).
* Les textes sont masqués (`<TEL>`, `<URL>`, `<EMAIL>`) avant tout stockage ou journal.
"""


def build_state(
    settings: Settings, assistant: DarijaCareAssistant | None, engine: Engine | None
) -> AppState:
    """Load models and configuration, synchronise reference tables (blocking)."""
    from darijacare.nlu.cli import load_train_config
    from darijacare.pipeline import build_assistant
    from darijacare.rag.cli import load_rag_config
    from darijacare.rag.kb import load_kb

    paths = get_paths()
    jwt_key = settings.jwt_key()
    engine = engine or make_engine(settings.sqlalchemy_url())
    sessions = make_session_factory(engine)
    raw_decision = (paths.configs / "decision.yaml").read_text(encoding="utf-8")
    decision_cfg = yaml.safe_load(raw_decision)
    fiches = load_kb(paths.root / load_rag_config(paths)["kb_dir"])
    model_info = None
    if assistant is None:
        if not settings.load_models:
            raise RuntimeError("load_models=false : un assistant doit être fourni (tests).")
        log.info("chargement des modèles (NLU %s, BGE-M3, Qdrant)", settings.nlu_model)
        assistant = build_assistant(
            paths.root, settings.nlu_model, settings.device, qdrant_url=settings.qdrant_url
        )
        model_info = served_model_info(paths, load_train_config(paths), settings.nlu_model)
    with sessions() as db:
        config_row = sync_decision_config(db, decision_cfg, raw_decision)
        if model_info is not None:
            ensure_model(db, model_info["version"], model_info["encoder"], model_info["metrics"])
            sync_evaluations(db, paths, settings.nlu_model, model_info["version"])
        n_parts, n_chunks = sync_knowledge_base(db, fiches)
        db.commit()
        config_id = config_row.id
    log.info(
        "références synchronisées : configuration %s, %d parties de fiches, %d passages",
        config_id,
        n_parts,
        n_chunks,
    )
    retriever = assistant.retriever

    def qdrant_status() -> str:
        if retriever is None:
            return "absent"
        try:
            retriever.client.get_collection(retriever.collection)
            return "ok"
        except Exception:
            return "erreur"

    return AppState(
        settings=settings,
        engine=engine,
        sessions=sessions,
        jwt_key=jwt_key,
        limiter=RateLimiter(),
        chat=ChatService(assistant, config_id),
        fiches=fiches,
        decision_config_id=config_id,
        model_version=model_info["version"] if model_info else None,
        qdrant_status=qdrant_status,
    )


def create_app(
    settings: Settings | None = None,
    *,
    assistant: DarijaCareAssistant | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the application. Tests inject a fake ``assistant`` and an ``engine``."""
    settings = settings or Settings()
    owns_engine = engine is None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = await run_in_threadpool(build_state, settings, assistant, engine)
        app.state.dc = state
        try:
            yield
        finally:
            if owns_engine:
                state.engine.dispose()

    app = FastAPI(
        title="DarijaCare API",
        version=API_VERSION,
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID", "Retry-After"],
        allow_credentials=False,
    )

    @app.middleware("http")
    async def access_logger(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """JSON access log (no body, no query string) and a request id."""
        request_id = uuid.uuid4().hex[:12]
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        access_log.info(
            "requête",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return response

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        log.error("erreur interne sur %s", request.url.path, exc_info=exc)
        return JSONResponse({"detail": "Erreur interne."}, status_code=500)

    app.include_router(public_router)
    app.include_router(staff_router)
    return app
