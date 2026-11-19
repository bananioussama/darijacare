"""Integration tests with Testcontainers (cahier des charges, Tableau 35).

API <-> PostgreSQL <-> Qdrant on throwaway containers of the same images as
docker-compose: Alembic migrations, reference synchronisation, Qdrant indexing and
retrieval, a customer conversation with an escalation, then the advisor's side.
The NLU is the keyword fake and the embedder the hashing fake (no model download in
CI); everything else is the real code. Skipped when Docker is not available.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from darijacare.api.app import create_app
from darijacare.api.db import Base
from darijacare.api.models import Chunk as ChunkRow
from darijacare.api.models import Escalade, FicheKB, Message, Utilisateur
from darijacare.api.security import hash_password
from darijacare.config import get_paths, load_yaml
from darijacare.decision.policy import DecisionPolicy
from darijacare.guards.input_guard import InputGuard
from darijacare.pipeline import DarijaCareAssistant
from darijacare.rag.index import chunk_fiches, get_client, index_chunks, index_is_current
from darijacare.rag.kb import load_kb
from darijacare.rag.respond import Responder
from darijacare.rag.retrieve import Retriever
from tests.api.conftest import KeywordNLU, auth, chat, make_settings
from tests.conftest import REPO_ROOT
from tests.unit.test_decision import CFG
from tests.unit.test_rag import FakeEmbedder

pytestmark = pytest.mark.integration

PG_IMAGE = "postgres:16.4-alpine"  # docker-compose.yml
QDRANT_IMAGE = "qdrant/qdrant:v1.20.0"  # docker-compose.yml (same minor as qdrant-client)
COLLECTION = "kb_fiches"


def _start(container: Any) -> Any:
    try:
        container.start()
    except Exception as e:  # Docker absent or not running
        pytest.skip(f"Docker indisponible pour Testcontainers ({type(e).__name__})")
    return container


@pytest.fixture(scope="module")
def pg_url() -> Iterator[str]:
    from testcontainers.community.postgres import PostgresContainer

    container = _start(
        PostgresContainer(
            PG_IMAGE,
            username="darijacare",
            password=secrets.token_urlsafe(16),
            dbname="darijacare",
            driver="psycopg",
        )
    )
    try:
        yield container.get_connection_url()
    finally:
        container.stop()


@pytest.fixture(scope="module")
def qdrant_url() -> Iterator[str]:
    from testcontainers.community.qdrant import QdrantContainer

    container = _start(QdrantContainer(QDRANT_IMAGE))
    try:
        yield f"http://{container.rest_host_address}"
    finally:
        container.stop()


@pytest.fixture(scope="module")
def migrated(pg_url: str) -> str:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.attributes["database_url"] = pg_url
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
    return pg_url


def test_migrations_match_the_models(migrated: str) -> None:
    engine = create_engine(migrated)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()
    assert diff == [] and version == "0001"


def test_qdrant_indexing_is_idempotent(qdrant_url: str) -> None:
    paths = get_paths()
    rag_cfg = load_yaml(paths.configs / "rag.yaml")
    client = get_client(rag_cfg["qdrant"], paths.root, url=qdrant_url)
    chunks = chunk_fiches(load_kb(REPO_ROOT / "kb"))
    try:
        first = index_chunks(client, "idempotence", chunks, FakeEmbedder())
        second = index_chunks(client, "idempotence", chunks, FakeEmbedder())
        assert first == second == {"upserted": len(chunks), "deleted": 0, "total": len(chunks)}
        assert index_is_current(client, "idempotence", chunks)
        assert not index_is_current(client, "idempotence", chunks[:-1])
        assert not index_is_current(client, "absente", chunks)
    finally:
        client.close()


def test_full_journey(migrated: str, qdrant_url: str) -> None:
    """Customer -> RAG answer from Qdrant -> escalation -> advisor takes and closes it."""
    paths = get_paths()
    rag_cfg = load_yaml(paths.configs / "rag.yaml")
    fiches = load_kb(REPO_ROOT / "kb")
    chunks = chunk_fiches(fiches)
    client = get_client(rag_cfg["qdrant"], paths.root, url=qdrant_url)
    embedder = FakeEmbedder()
    index_chunks(client, COLLECTION, chunks, embedder)
    retrieval = {**rag_cfg["retrieval"], "min_dense_score": 0.0}  # fake embedder scores
    assistant = DarijaCareAssistant(
        InputGuard.from_config(CFG["input"]),
        KeywordNLU(),
        DecisionPolicy(CFG),
        Responder(fiches, max_chars=CFG["input"]["max_chars"]),
        Retriever(client, COLLECTION, embedder, retrieval),
    )
    engine = create_engine(migrated)
    try:
        with TestClient(create_app(make_settings(database_url=migrated), assistant=assistant)) as c:
            health = c.get("/health").json()
            assert health["database"] == "ok" and health["qdrant"] == "ok"

            answer = chat(c, "kifach nchouf solde dyali, nemra 0612345678")
            assert answer["analysis"]["decision"]["action"] == "reponse_ancree"
            assert answer["sources"][0]["id"] == "KB-balance_check"
            assert "<TEL>" in answer["analysis"]["masked_text"]

            lost = chat(c, "tsre9 lia tilifon")
            case = lost["done"]["escalation"]["case_number"]

            with Session(engine) as db:
                db.add(
                    Utilisateur(
                        username="conseiller1",
                        password_hash=hash_password("mot-de-passe-de-test-123"),
                        role="conseiller",
                    )
                )
                db.commit()
            login = c.post(
                "/auth/login",
                json={"username": "conseiller1", "password": "mot-de-passe-de-test-123"},
            )
            token = login.json()["access_token"]
            queue = c.get("/escalades", headers=auth(token)).json()
            assert [e["case_number"] for e in queue] == [case]
            for action in ("prendre", "cloturer"):
                r = c.patch(
                    f"/escalades/{queue[0]['id']}", json={"action": action}, headers=auth(token)
                )
                assert r.status_code == 200, r.text

        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(Message)) == 2
            assert db.scalar(select(Escalade.status)) == "cloture"
            assert db.scalar(select(func.count()).select_from(FicheKB)) == 225
            assert db.scalar(select(func.count()).select_from(ChunkRow)) == len(chunks)
            stored = db.scalars(select(Message.text)).all()
            assert all("0612345678" not in t for t in stored)
    finally:
        engine.dispose()
        client.close()
