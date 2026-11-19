"""Staff self-registration validated by an administrator (cahier des charges, F-UI-08)."""

from __future__ import annotations

import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from darijacare.api.logging_json import JsonFormatter
from darijacare.api.models import Utilisateur
from darijacare.pipeline import DarijaCareAssistant
from tests.api.conftest import auth, chat, make_settings, start

NEW_PASSWORD = "un-mot-de-passe-solide-42"
PENDING = "Compte en attente de validation par un administrateur."


def register(client: TestClient, username: str, role: str = "conseiller") -> int:
    body = {"username": username, "password": NEW_PASSWORD, "requested_role": role}
    return client.post("/auth/register", json=body).status_code


def login(client: TestClient, username: str, password: str = NEW_PASSWORD) -> tuple[int, dict]:
    r = client.post("/auth/login", json={"username": username, "password": password})
    return r.status_code, r.json()


def account(engine: Engine, username: str) -> Utilisateur | None:
    with Session(engine) as db:
        return db.scalar(select(Utilisateur).where(Utilisateur.username == username))


def test_registration_waits_for_an_administrator(
    client: TestClient, staff: dict[str, str], engine: Engine
) -> None:
    r = client.post(
        "/auth/register",
        json={"username": "nouveau.conseiller", "password": NEW_PASSWORD, "requested_role": "ml"},
    )
    assert r.status_code == 202
    assert "administrateur doit valider" in r.json()["detail"]
    user = account(engine, "nouveau.conseiller")
    assert user is not None and user.pending and user.role == "ml"
    assert user.password_hash.startswith("$argon2id$")

    # Right password: the account is told it is waiting. Wrong password: the usual answer.
    assert login(client, "nouveau.conseiller") == (403, {"detail": PENDING})
    assert login(client, "nouveau.conseiller", "faux-mot-de-passe")[0] == 401

    # Pending requests come first in the administrator's list.
    users = client.get("/admin/users", headers=auth(staff["admin1"])).json()
    assert users[0]["username"] == "nouveau.conseiller" and users[0]["pending"] is True
    assert all(u["pending"] is False for u in users[1:])

    # The administrator validates and may change the requested role.
    r = client.patch(
        f"/admin/users/{user.id}",
        json={"action": "valider", "role": "conseiller"},
        headers=auth(staff["admin1"]),
    )
    assert r.status_code == 200
    assert r.json()["pending"] is False and r.json()["role"] == "conseiller"
    code, token = login(client, "nouveau.conseiller")
    assert code == 200 and token["role"] == "conseiller"
    assert client.get("/escalades", headers=auth(token["access_token"])).status_code == 200

    # Validating twice, or refusing an active account, is not possible.
    again = {"action": "valider", "role": "ml"}
    path = f"/admin/users/{user.id}"
    assert client.patch(path, json=again, headers=auth(staff["admin1"])).status_code == 409
    assert client.delete(path, headers=auth(staff["admin1"])).status_code == 409


def test_a_refused_request_is_deleted(
    client: TestClient, staff: dict[str, str], engine: Engine
) -> None:
    assert register(client, "a.refuser") == 202
    user = account(engine, "a.refuser")
    assert user is not None
    r = client.delete(f"/admin/users/{user.id}", headers=auth(staff["admin1"]))
    assert r.status_code == 204 and r.content == b""
    assert account(engine, "a.refuser") is None
    assert login(client, "a.refuser")[0] == 401
    # The username is free again.
    assert register(client, "a.refuser") == 202
    unknown = f"/admin/users/{uuid.uuid4()}"
    assert client.delete(unknown, headers=auth(staff["admin1"])).status_code == 404


def test_registration_input_is_checked(client: TestClient, staff: dict[str, str]) -> None:
    assert register(client, "admin1") == 409  # existing account
    assert register(client, "quelqu.un", role="admin") == 422  # nobody asks to be administrator
    assert register(client, "x") == 422  # too short
    assert register(client, "avec espace") == 422
    short = {"username": "court.mdp", "password": "trop-court", "requested_role": "conseiller"}
    assert client.post("/auth/register", json=short).status_code == 422


def test_only_administrators_decide(
    client: TestClient, staff: dict[str, str], engine: Engine
) -> None:
    assert register(client, "en.attente") == 202
    user = account(engine, "en.attente")
    assert user is not None
    session = chat(client, "kifach nchouf solde dyali")["session"]["session_token"]
    path = f"/admin/users/{user.id}"
    body = {"action": "valider", "role": "admin"}
    for token, code in [
        (None, 401),
        (session, 403),
        (staff["conseiller1"], 403),
        (staff["ml1"], 403),
    ]:
        assert client.patch(path, json=body, headers=auth(token)).status_code == code
        assert client.delete(path, headers=auth(token)).status_code == code
    still = account(engine, "en.attente")
    assert still is not None and still.pending


def test_registrations_are_limited(engine: Engine, assistant: DarijaCareAssistant) -> None:
    with start(make_settings(rate_limit_register_per_minute=2), engine, assistant) as c:
        codes = [register(c, f"rafale{i}") for i in range(3)]
    assert codes == [202, 202, 429]
    with start(make_settings(max_pending_registrations=1), engine, assistant) as c:
        # Two requests are already waiting from the previous client.
        r = c.post(
            "/auth/register",
            json={"username": "une.de.trop", "password": NEW_PASSWORD, "requested_role": "ml"},
        )
    assert r.status_code == 429 and "en attente" in r.json()["detail"]


def test_registration_logs_hold_no_credentials(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        assert register(client, "discret") == 202
        login(client, "discret")
    lines = "\n".join(JsonFormatter().format(r) for r in caplog.records)
    assert "inscription_demandee" in lines and "connexion_en_attente" in lines
    assert NEW_PASSWORD not in lines
