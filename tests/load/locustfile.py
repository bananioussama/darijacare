"""Locust load test (cahier des charges §8 « Scalabilité », Tableau 33 « Tests de charge »).

Each simulated customer opens a session, then sends messages taken from the
interface's example sentences (three scripts), with a pause between two messages.
The pause comes from ``DARIJACARE_LOAD_WAIT`` (``min,max`` seconds, default ``5,15``).

Capacity (relaxed limits: every simulated user comes from the same address)::

    docker compose -f docker-compose.yml -f deploy/load/docker-compose.load.yml up -d backend edge
    uv run --group load locust -f tests/load/locustfile.py --headless -u 20 -r 2 -t 3m \
        --host https://127.0.0.1:8443/api --csv reports/quality/load/capacite
    docker compose up -d backend edge          # back to the normal limits

Abuse (normal limits): the same command against the normal stack must produce 429s.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

from locust import HttpUser, between, task

MESSAGES = (  # frontend/src/lib/labels.ts (EXAMPLES)
    "الكونيكسيون مقطوعة من البارح ف الدار",
    "chargit 20dh w ma wslatni walo, 3afak chofo lia",
    "Bonjour, ma facture de ce mois est trop élevée",
    "solde dyali sala bzerba, 3lach?",
    "كيفاش نشري باس ديال الأنترنيت",
)
CERT = Path(__file__).resolve().parents[2] / "deploy" / "certs" / "cert.pem"
WAIT = tuple(float(x) for x in os.environ.get("DARIJACARE_LOAD_WAIT", "5,15").split(","))


class Customer(HttpUser):
    """A customer chatting with the assistant."""

    wait_time = between(WAIT[0], WAIT[1])

    def on_start(self) -> None:
        self.client.verify = str(CERT) if CERT.exists() else True
        self.token: str | None = None
        with self.client.post("/sessions", name="/sessions", catch_response=True) as r:
            if r.status_code == 201:
                self.token = r.json()["session_token"]
            else:
                r.failure(f"statut {r.status_code}")

    @task
    def chat(self) -> None:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        body = {"text": random.choice(MESSAGES)}
        with self.client.post(
            "/chat", json=body, headers=headers, name="/chat", catch_response=True
        ) as r:
            if r.status_code != 200:
                r.failure(f"statut {r.status_code}")
            elif "event: done" not in r.text:
                r.failure("flux SSE incomplet")
