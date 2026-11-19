"""API test fixtures: SQLite in memory, keyword-based fake NLU, real policy, KB and templates."""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from darijacare.api.app import create_app
from darijacare.api.db import Base, make_engine
from darijacare.api.models import Utilisateur
from darijacare.api.security import hash_password
from darijacare.api.settings import Settings
from darijacare.data.scripts import detect_script
from darijacare.decision.policy import DecisionPolicy
from darijacare.guards.input_guard import InputGuard
from darijacare.nlu.service import NLUResult, Scored
from darijacare.pipeline import DarijaCareAssistant
from darijacare.rag.kb import load_kb
from darijacare.rag.respond import Responder
from tests.conftest import REPO_ROOT
from tests.unit.test_decision import CFG

TEST_JWT_KEY = "cle-de-test-uniquement-" + "x" * 32  # test-only signing key
PASSWORD = "mot-de-passe-de-test-123"
STAFF_USERS = {
    "conseiller1": "conseiller",
    "conseiller2": "conseiller",
    "ml1": "ml",
    "admin1": "admin",
}

# keyword in the message -> fake NLU prediction (first match wins)
RULES: list[tuple[str, dict[str, Any]]] = [
    ("tsre9", {"intent": "lost_stolen", "category": "sim_line", "urgency": 3, "p_human": 0.97}),
    (
        "conseiller",
        {"intent": "human_agent", "category": "customer_care", "urgency": 1, "p_human": 0.92},
    ),
    (
        "flous",
        {
            "intent": "mm_transaction_issue",
            "category": "mobile_money",
            "urgency": 2,
            "p_human": 0.6,
        },
    ),
    (
        "hmmm",
        {"intent": "balance_check", "category": "prepaid_credit", "cat_p": 0.6, "intent_p": 0.6},
    ),
    ("match", {"intent": "non_telecom", "category": "out_of_scope"}),
]
DEFAULT = {"intent": "balance_check", "category": "prepaid_credit"}


def fake_result(
    text: str,
    intent: str,
    category: str,
    *,
    p_human: float = 0.05,
    urgency: int = 0,
    cat_p: float = 0.95,
    intent_p: float = 0.95,
) -> NLUResult:
    return NLUResult(
        text=text,
        script=detect_script(text),
        category=category,
        category_confidence=cat_p,
        intent=intent,
        intent_confidence=intent_p,
        intent_joint_confidence=cat_p * intent_p,
        product="mobile",
        product_confidence=0.9,
        urgency=urgency,
        urgency_confidence=0.8,
        needs_human=p_human >= 0.5,
        needs_human_probability=p_human,
        category_top2=[Scored(category, cat_p), Scored("customer_care", 0.02)],
        intent_top2=[Scored(intent, intent_p), Scored("balance_deducted", 0.02)],
        model_version="fake@0000",
    )


class KeywordNLU:
    """Deterministic stand-in for the published model."""

    model_version = "fake@0000"

    def predict(self, text: str) -> NLUResult:
        low = text.lower()
        for keyword, kwargs in RULES:
            if keyword in low:
                return fake_result(text, **kwargs)
        return fake_result(text, **DEFAULT)

    def predict_batch(self, texts: Sequence[str], batch_size: int = 16) -> list[NLUResult]:
        return [self.predict(t) for t in texts]


@pytest.fixture(scope="session")
def assistant() -> DarijaCareAssistant:
    fiches = load_kb(REPO_ROOT / "kb")
    return DarijaCareAssistant(
        InputGuard.from_config(CFG["input"]),
        KeywordNLU(),
        DecisionPolicy(CFG),
        Responder(fiches, max_chars=CFG["input"]["max_chars"]),
        retriever=None,
    )


@pytest.fixture(scope="session")
def password_hash() -> str:
    return hash_password(PASSWORD)


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": "sqlite://",
        "jwt_secret": TEST_JWT_KEY,
        "load_models": False,
        "rate_limit_chat_per_minute": 10_000,
        "rate_limit_login_per_minute": 10_000,
        "rate_limit_register_per_minute": 10_000,
        "cors_origins": ["http://localhost:5173"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def engine() -> Iterator[Engine]:
    eng = make_engine("sqlite://")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def start(settings: Settings, engine: Engine, assistant: DarijaCareAssistant) -> TestClient:
    return TestClient(create_app(settings, assistant=assistant, engine=engine))


@pytest.fixture
def client(engine: Engine, assistant: DarijaCareAssistant) -> Iterator[TestClient]:
    with start(make_settings(), engine, assistant) as c:
        yield c


@pytest.fixture
def staff(client: TestClient, engine: Engine, password_hash: str) -> dict[str, str]:
    """Staff accounts and their access tokens (username -> token)."""
    with Session(engine) as db:
        for username, role in STAFF_USERS.items():
            db.add(Utilisateur(username=username, password_hash=password_hash, role=role))
        db.commit()
    tokens = {}
    for username in STAFF_USERS:
        r = client.post("/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200, r.text
        tokens[username] = r.json()["access_token"]
    return tokens


def auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def parse_sse(body: str) -> list[tuple[str, Any]]:
    events = []
    for block in body.strip().split("\n\n"):
        event_line, data_line = block.split("\n", 1)
        events.append(
            (event_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: ")))
        )
    return events


def chat(client: TestClient, text: str, token: str | None = None) -> dict[str, Any]:
    """Send one message; return the events grouped by name (tokens joined)."""
    r = client.post("/chat", json={"text": text}, headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    return chat_events(r.text)


def chat_events(body: str) -> dict[str, Any]:
    """SSE body -> events grouped by name, with the ``token`` pieces joined in ``reply``."""
    events = parse_sse(body)
    names = [e for e, _ in events]
    out: dict[str, Any] = {"order": names}
    out.update({name: data for name, data in events if name != "token"})
    out["reply"] = "".join(data["text"] for name, data in events if name == "token")
    return out
