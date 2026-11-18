"""Smoke test of a running API with the real models (Phase 4); writes reports/demo/phase4.md.

    DARIJACARE_SMOKE_PASSWORD=... python tools/api_smoke.py --base-url http://127.0.0.1:8000

Needs the staff accounts ``conseiller1`` and ``ml1`` (same password, read from the
environment). Every message below is fictional; numbers are masked by the API.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

import httpx

MESSAGES = [
    ("arabe", "الكونيكسيون مقطوعة من البارح ف الدار والضو ديال الروتور حمر"),
    ("arabizi", "chargit 20dh w ma wslatni walo, 3afak chofo lia"),
    ("mixte", "Bonjour, ma facture de ce mois est trop élevée, je veux comprendre pourquoi"),
    ("arabe", "تسرق ليا التيليفون دابا، عافاك بلوكيو ليا الخط، النمرة ديالي 0612345678"),
    ("arabizi", "bghit nhder m3a chi conseiller daba"),
]
LATENCY_MESSAGES = [
    "solde dyali sala bzerba, 3lach?",
    "كيفاش نشري باس ديال الأنترنيت",
    "internet f dar t9il bzaf had simana",
    "Je n'arrive pas à appeler à l'étranger depuis hier",
    "wach kayn chi forfait fih appels illimités",
]


def parse_sse(body: str) -> dict[str, Any]:
    out: dict[str, Any] = {"tokens": []}
    for block in body.strip().split("\n\n"):
        event_line, data_line = block.split("\n", 1)
        name = event_line.removeprefix("event: ")
        data = json.loads(data_line.removeprefix("data: "))
        if name == "token":
            out["tokens"].append(data["text"])
        else:
            out[name] = data
    out["reply"] = "".join(out.pop("tokens"))
    return out


def send(client: httpx.Client, text: str, token: str | None = None) -> tuple[dict[str, Any], float]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    t = time.perf_counter()
    r = client.post("/chat", json={"text": text}, headers=headers)
    elapsed = (time.perf_counter() - t) * 1000
    r.raise_for_status()
    return parse_sse(r.text), elapsed


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(q / 100 * (len(ordered) - 1))))
    return ordered[k]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--out", default="reports/demo/phase4.md")
    parser.add_argument("--latency-runs", type=int, default=20)
    args = parser.parse_args()
    password = os.environ["DARIJACARE_SMOKE_PASSWORD"]
    lines = [
        "# Démonstration de l'API (Phase 4)",
        "",
        "API lancée avec les vrais modèles (NLU v5, BGE-M3, serveur Qdrant), PostgreSQL de",
        "docker-compose. Messages **fictifs** ; données d'entraînement **synthétiques**.",
        "",
    ]
    with httpx.Client(base_url=args.base_url, timeout=60) as client:
        health = client.get("/health").json()
        lines += [
            "## Santé",
            "",
            "```json",
            json.dumps(health, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
        client.post("/predict", json={"text": "salam, bghit n3ref solde dyali"})  # warm-up

        lines += ["## Conversations", ""]
        sessions = []
        for label, text in MESSAGES:
            out, ms = send(client, text)
            sessions.append(out)
            nlu = out["analysis"]["nlu"] or {}
            esc = out["done"]["escalation"]
            case = f"{esc['case_number']} ({esc['priority_level']})" if esc else "non"
            lines += [
                f"### {label} — « {out['analysis']['masked_text']} »",
                "",
                f"- NLU : `{nlu.get('intent')}` ({nlu.get('category')}), confiance "
                f"{nlu.get('intent_joint_confidence', 0):.2f}, urgence {nlu.get('urgency')}, "
                f"p(conseiller) {nlu.get('needs_human_probability', 0):.2f}, écriture "
                f"`{out['analysis']['script']}`",
                f"- Décision : règle {out['analysis']['decision']['rule']} "
                f"`{out['analysis']['decision']['action']}`",
                f"- Sources : {', '.join(s['id'] for s in out['sources']) or 'aucune'}",
                f"- Escalade : {case}",
                f"- Latence : serveur {out['done']['latency_ms'].get('total', 0):.0f} ms, "
                f"requête complète {ms:.0f} ms",
                "",
                "```text",
                out["reply"],
                "```",
                "",
            ]

        # Second turn in the first session, history, isolation
        first = sessions[0]["session"]
        follow, _ = send(client, "w daba kifach ndir?", first["session_token"])
        history = client.get(
            f"/sessions/{first['session_id']}/messages",
            headers={"Authorization": f"Bearer {first['session_token']}"},
        ).json()
        other = client.get(
            f"/sessions/{sessions[1]['session']['session_id']}/messages",
            headers={"Authorization": f"Bearer {first['session_token']}"},
        )
        lines += [
            "## Session et isolation",
            "",
            f"- Deuxième message dans la même session : tour {follow['done']['turn']} ; "
            f"historique : {history['total']} messages.",
            f"- Lecture de la session d'un autre client : HTTP {other.status_code}.",
            "",
        ]

        # Advisor console
        tokens = {}
        for name in ("conseiller1", "ml1"):
            r = client.post("/auth/login", json={"username": name, "password": password})
            r.raise_for_status()
            tokens[name] = {"Authorization": f"Bearer {r.json()['access_token']}"}
        queue = client.get("/escalades", headers=tokens["conseiller1"]).json()
        lines += [
            "## Console conseiller",
            "",
            "| Dossier | Priorité | Niveau | Intention | Écriture |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| {e['case_number']} | {e['priority']:.1f} | {e['priority_level']} | {e['intent']} "
            f"| {e['script']} |"
            for e in queue
        ]
        top = queue[0]
        detail = client.get(f"/escalades/{top['id']}", headers=tokens["conseiller1"]).json()
        taken = client.patch(
            f"/escalades/{top['id']}", json={"action": "prendre"}, headers=tokens["conseiller1"]
        ).json()
        closed = client.patch(
            f"/escalades/{top['id']}",
            json={"action": "cloturer", "corrected_intent": detail["message"]["intent"]},
            headers=tokens["conseiller1"],
        ).json()
        lines += [
            "",
            f"Dossier en tête : {top['case_number']} ; fiche proposée "
            f"`{(detail['proposed_fiche'] or {}).get('id')}` ; "
            f"statuts : {top['status']} → {taken['status']} → {closed['status']}.",
            "",
        ]

        # Latency on repeated messages (CPU)
        totals, servers = [], []
        for i in range(args.latency_runs):
            out, ms = send(client, LATENCY_MESSAGES[i % len(LATENCY_MESSAGES)])
            totals.append(ms)
            servers.append(out["done"]["latency_ms"].get("total", 0.0))
        summary = client.get("/analytics/summary", headers=tokens["ml1"]).json()
        lines += [
            f"## Latence ({args.latency_runs} messages, CPU)",
            "",
            "| Mesure | Médiane | p95 |",
            "|---|---|---|",
            f"| Traitement serveur (garde, NLU, décision, recherche, gabarit) | "
            f"{statistics.median(servers):.0f} ms | {percentile(servers, 95):.0f} ms |",
            f"| Requête complète vue du client (dont enregistrement) | "
            f"{statistics.median(totals):.0f} ms | {percentile(totals, 95):.0f} ms |",
            "",
            "## Tableau de bord (rôle ml)",
            "",
            "```json",
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            "```",
            "",
        ]
    Path(args.out).write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
