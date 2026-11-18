"""Staff routes: login, advisor console, permission matrix (Table 14), analytics, accounts."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from darijacare.api.models import Feedback, Utilisateur
from darijacare.api.security import STAFF, create_token, decode_token
from darijacare.pipeline import DarijaCareAssistant
from tests.api.conftest import PASSWORD, TEST_JWT_KEY, auth, chat, make_settings, start


def test_passwords_are_argon2id_and_login_errors_are_uniform(
    client: TestClient, staff: dict[str, str], engine: Engine
) -> None:
    with Session(engine) as db:
        user = db.scalar(select(Utilisateur).where(Utilisateur.username == "admin1"))
        assert user is not None and user.password_hash.startswith("$argon2id$")
    wrong = client.post("/auth/login", json={"username": "admin1", "password": "faux-mot-de-passe"})
    unknown = client.post("/auth/login", json={"username": "personne", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Identifiants invalides."}
    principal = decode_token(TEST_JWT_KEY, staff["admin1"])
    assert principal.kind == STAFF and principal.role == "admin"
    me = client.get("/auth/me", headers=auth(staff["ml1"])).json()
    assert me["username"] == "ml1" and me["role"] == "ml"


def test_expired_tampered_and_deactivated_tokens_are_refused(
    client: TestClient, staff: dict[str, str], engine: Engine
) -> None:
    sub = decode_token(TEST_JWT_KEY, staff["admin1"]).subject
    expired = create_token(
        TEST_JWT_KEY, subject=sub, role="admin", kind=STAFF, ttl=timedelta(seconds=-1)
    )
    assert client.get("/auth/me", headers=auth(expired)).status_code == 401
    forged = create_token(
        "une-autre-cle-" + "y" * 32, subject=sub, role="admin", kind=STAFF, ttl=timedelta(minutes=5)
    )
    assert client.get("/auth/me", headers=auth(forged)).status_code == 401
    with Session(engine) as db:
        user = db.scalar(select(Utilisateur).where(Utilisateur.username == "admin1"))
        assert user is not None
        user.active = False
        db.commit()
    assert client.get("/auth/me", headers=auth(staff["admin1"])).status_code == 401


def test_login_attempts_are_limited(engine: Engine, assistant: DarijaCareAssistant) -> None:
    with start(make_settings(rate_limit_login_per_minute=3), engine, assistant) as c:
        codes = [
            c.post("/auth/login", json={"username": "x", "password": "y"}).status_code
            for _ in range(4)
        ]
        assert codes == [401, 401, 401, 429]


def escalate(client: TestClient, text: str) -> dict[str, Any]:
    out = chat(client, text)
    assert out["done"]["escalation"] is not None, out["analysis"]["decision"]
    return out


def test_escalation_full_cycle(client: TestClient, staff: dict[str, str], engine: Engine) -> None:
    out = escalate(client, "tsre9 lia tilifon daba f zan9a")
    case = out["done"]["escalation"]
    assert case["priority_level"] == "critique" and case["status"] == "nouveau"
    # the customer gets the case number in their script, and the safety steps
    assert f"Numero dyal dossier dyalek : {case['case_number']}" in out["reply"]
    assert out["sources"][0]["id"] == "KB-lost_stolen"

    queue = client.get("/escalades", headers=auth(staff["conseiller1"])).json()
    assert queue[0]["case_number"] == case["case_number"]
    esc_id = queue[0]["id"]
    detail = client.get(f"/escalades/{esc_id}", headers=auth(staff["conseiller1"])).json()
    assert detail["message"]["intent"] == "lost_stolen" and detail["analysis"]["urgency"] == 3
    assert detail["proposed_fiche"]["id"] == "KB-lost_stolen" and detail["history"]
    assert set(detail["priority_contributions"]) >= {"urgence", "bonus"}

    take = client.patch(
        f"/escalades/{esc_id}", json={"action": "prendre"}, headers=auth(staff["conseiller1"])
    )
    assert take.status_code == 200 and take.json()["status"] == "en_cours"
    assert take.json()["advisor"] == "conseiller1"
    again = client.patch(
        f"/escalades/{esc_id}", json={"action": "prendre"}, headers=auth(staff["conseiller2"])
    )
    assert again.status_code == 409
    not_mine = client.patch(
        f"/escalades/{esc_id}", json={"action": "cloturer"}, headers=auth(staff["conseiller2"])
    )
    assert not_mine.status_code == 403
    close = client.patch(
        f"/escalades/{esc_id}",
        json={"action": "cloturer", "corrected_intent": "scam_spam_report"},
        headers=auth(staff["conseiller1"]),
    )
    assert close.status_code == 200 and close.json()["status"] == "cloture"
    assert close.json()["corrected_intent"] == "scam_spam_report"
    with Session(engine) as db:
        fb = db.scalar(select(Feedback))
        assert fb is not None and fb.author == "conseiller" and fb.rating == "a_corriger"
    export = client.get("/feedback/export", headers=auth(staff["ml1"])).json()
    assert export[0]["corrected_intent"] == "scam_spam_report"
    assert export[0]["predicted_intent"] == "lost_stolen"
    # the customer can no longer overwrite the advisor's correction
    token = out["session"]["session_token"]
    body = {"message_id": out["done"]["message_id"], "rating": "utile"}
    assert client.post("/feedback", json=body, headers=auth(token)).status_code == 409
    # a new request in the same conversation reopens the same case
    reopened = chat(client, "tsre9 lia tilifon, 3awtani", token)
    assert reopened["done"]["escalation"]["case_number"] == case["case_number"]
    assert reopened["done"]["escalation"]["status"] == "nouveau"


def test_queue_is_sorted_by_priority_then_arrival(
    client: TestClient, staff: dict[str, str]
) -> None:
    first_agent = escalate(client, "bghit nhder m3a chi conseiller")  # normale
    escalate(client, "sifet lflous l nmra ghalta")  # mm_transaction_issue: haute
    escalate(client, "tsre9 lia tilifon")  # lost_stolen: critique
    second_agent = escalate(client, "3afak bghit conseiller daba")  # same priority as the first
    queue = client.get("/escalades", headers=auth(staff["conseiller1"])).json()
    levels = [e["priority_level"] for e in queue]
    assert levels == ["critique", "haute", "normale", "normale"]
    priorities = [e["priority"] for e in queue]
    assert priorities == sorted(priorities, reverse=True)
    assert [e["case_number"] for e in queue[2:]] == [
        first_agent["done"]["escalation"]["case_number"],
        second_agent["done"]["escalation"]["case_number"],
    ]
    stats = client.get("/analytics/escalades", headers=auth(staff["conseiller1"])).json()
    assert stats["par_statut"] == {"nouveau": 4}
    assert client.get("/escalades?status=inconnu", headers=auth(staff["admin1"])).status_code == 422


# (method, path, expected status for: none, session, conseiller, ml, admin)
MATRIX: list[tuple[str, str, tuple[int, int, int, int, int]]] = [
    ("GET", "/escalades", (401, 403, 200, 403, 200)),
    ("GET", "/escalades/{esc}", (401, 403, 200, 403, 200)),
    ("PATCH", "/escalades/{esc}", (401, 403, 200, 403, 403)),
    ("GET", "/analytics/summary", (401, 403, 403, 200, 200)),
    ("GET", "/analytics/escalades", (401, 403, 200, 200, 200)),
    ("GET", "/feedback/export", (401, 403, 403, 200, 200)),
    ("GET", "/kb/fiches", (401, 403, 403, 200, 200)),
    ("GET", "/models", (401, 403, 403, 200, 200)),
    ("GET", "/config/decision", (401, 403, 403, 200, 200)),
    ("GET", "/admin/users", (401, 403, 403, 403, 200)),
    ("POST", "/admin/users", (401, 403, 403, 403, 201)),
    ("GET", "/sessions/{sid}/messages", (401, 200, 403, 403, 403)),
    ("POST", "/feedback", (401, 201, 403, 403, 403)),
]


def test_permission_matrix(client: TestClient, staff: dict[str, str]) -> None:
    """Server-side checks of the cahier des charges' permission matrix (Table 14)."""
    out = escalate(client, "tsre9 lia tilifon")
    session = out["session"]
    esc = client.get("/escalades", headers=auth(staff["conseiller1"])).json()[0]["id"]
    callers = [
        None,
        session["session_token"],
        staff["conseiller1"],
        staff["ml1"],
        staff["admin1"],
    ]
    bodies: dict[str, Any] = {
        "PATCH": {"action": "prendre"},
        "POST /admin/users": {"username": "", "password": "x" * 12, "role": "ml"},
        "POST /feedback": {"message_id": out["done"]["message_id"], "rating": "utile"},
    }
    n_users = 0
    for method, template, expected in MATRIX:
        path = template.format(esc=esc, sid=session["session_id"])
        for caller, want in zip(callers, expected, strict=True):
            body = bodies.get(f"{method} {template}", bodies.get(method))
            if template == "/admin/users" and method == "POST":
                n_users += 1
                body = {**body, "username": f"nouveau{n_users}"}
            r = client.request(method, path, json=body, headers=auth(caller))
            assert r.status_code == want, (method, template, caller is None, r.text)


def test_analytics_summary(client: TestClient, staff: dict[str, str]) -> None:
    chat(client, "kifach nchouf solde dyali")
    chat(client, "كيفاش نشوف الصولد ديالي")
    escalate(client, "tsre9 lia tilifon")
    s = client.get("/analytics/summary", headers=auth(staff["ml1"])).json()
    assert s["messages"] == 3 and s["escalades"] == 1
    assert s["taux_escalade"] == pytest.approx(1 / 3, abs=1e-4)  # rounded to 4 decimals
    assert s["par_script"] == {"arabizi": 2, "arabic": 1}
    assert s["top_intentions"][0] == {"intent": "balance_check", "messages": 2}
    assert s["latence_ms"]["p95"] is not None


def test_admin_manages_accounts(client: TestClient, staff: dict[str, str]) -> None:
    body = {"username": "conseiller3", "password": "un-long-mot-de-passe", "role": "conseiller"}
    created = client.post("/admin/users", json=body, headers=auth(staff["admin1"]))
    assert created.status_code == 201 and created.json()["role"] == "conseiller"
    duplicate = client.post("/admin/users", json=body, headers=auth(staff["admin1"]))
    assert duplicate.status_code == 409
    short = {**body, "username": "court", "password": "court"}
    assert client.post("/admin/users", json=short, headers=auth(staff["admin1"])).status_code == 422
    login = client.post(
        "/auth/login", json={"username": "conseiller3", "password": body["password"]}
    )
    assert login.status_code == 200 and login.json()["expires_in"] == 15 * 60


def test_models_kb_and_config_are_listed(client: TestClient, staff: dict[str, str]) -> None:
    fiches = client.get("/kb/fiches", headers=auth(staff["ml1"])).json()
    assert len(fiches) == 75 and set(fiches[0]["titles"]) == {"fr", "ar", "arabizi"}
    config = client.get("/config/decision", headers=auth(staff["ml1"])).json()
    assert config["content"]["thresholds"]["needs_human"] == 0.30


def test_database_constraints(engine: Engine, password_hash: str) -> None:
    with Session(engine) as db, pytest.raises(IntegrityError):
        db.add(Utilisateur(username="x", password_hash=password_hash, role="pirate"))
        db.commit()
