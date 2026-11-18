"""Integration test on the docker-compose PostgreSQL (skipped when it is not reachable).

A temporary database is created, migrated with Alembic, checked against the models,
used by the API for a full escalation cycle, then dropped.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from darijacare.api.app import create_app
from darijacare.api.db import Base
from darijacare.api.models import Utilisateur
from darijacare.api.settings import Settings
from darijacare.pipeline import DarijaCareAssistant
from tests.api.conftest import PASSWORD, auth, chat, make_settings
from tests.conftest import REPO_ROOT

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def pg_url() -> Iterator[str]:
    """URL of a fresh temporary database on the docker-compose server."""
    try:
        base = make_url(Settings().sqlalchemy_url())
    except RuntimeError as e:
        pytest.skip(f"PostgreSQL non configuré ({e})")
    if base.get_backend_name() != "postgresql":
        pytest.skip("DATABASE_URL ne vise pas PostgreSQL")
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    name = f"darijacare_test_{uuid.uuid4().hex[:8]}"
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as e:  # server down or unreachable
        admin.dispose()
        pytest.skip(f"PostgreSQL injoignable : {type(e).__name__}")
    try:
        yield base.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def test_migrations_match_the_models(pg_url: str) -> None:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.attributes["database_url"] = pg_url
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
    engine = create_engine(pg_url)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert diff == [], diff
        assert version == "0001"
    finally:
        engine.dispose()


def test_full_cycle_on_postgres(
    pg_url: str, assistant: DarijaCareAssistant, password_hash: str
) -> None:
    settings = make_settings(database_url=pg_url)
    with TestClient(create_app(settings, assistant=assistant)) as client:
        engine = create_engine(pg_url)
        with Session(engine) as db:
            db.add(
                Utilisateur(username="conseiller1", password_hash=password_hash, role="conseiller")
            )
            db.add(Utilisateur(username="ml1", password_hash=password_hash, role="ml"))
            db.commit()
        engine.dispose()
        token = {
            name: client.post("/auth/login", json={"username": name, "password": PASSWORD}).json()[
                "access_token"
            ]
            for name in ("conseiller1", "ml1")
        }
        assert client.get("/health").json()["kb_fiches"] == 75
        a = chat(client, "kifach nchouf solde dyali, nemra 0612345678")
        b = chat(client, "tsre9 lia tilifon")
        assert "<TEL>" in a["analysis"]["masked_text"]
        queue = client.get("/escalades", headers=auth(token["conseiller1"])).json()
        assert [e["case_number"] for e in queue] == [b["done"]["escalation"]["case_number"]]
        esc = queue[0]["id"]
        for action in ("prendre", "cloturer"):
            r = client.patch(
                f"/escalades/{esc}", json={"action": action}, headers=auth(token["conseiller1"])
            )
            assert r.status_code == 200, r.text
        other = client.get(
            f"/sessions/{b['session']['session_id']}/messages",
            headers=auth(a["session"]["session_token"]),
        )
        assert other.status_code == 403
        summary = client.get("/analytics/summary", headers=auth(token["ml1"])).json()
        assert summary["messages"] == 2 and summary["par_script"] == {"arabizi": 2}
