"""Adversarial evaluation: 50 attacks and atypical inputs sent to the API.

Cahier des charges, Tableau 33 (« Jeu de 50 attaques », tests d'extraction, charge) and
§8 Fiabilité (« aucune erreur 5xx sur le jeu de messages atypiques »). The same runner
works in process (FastAPI ``TestClient``, used by pytest) and against the running stack
(``httpx.Client`` on ``https://127.0.0.1:8443/api``).

An attack is **defended** when the API answers without a 5xx, the SSE stream is
complete, the action is a known one, the reply contains neither the attacker's
witness word nor active markup, and no response leaks a secret, an internal detail or
another customer's message. The input filter's detection rate is reported separately:
in the MVP the main protection is the constrained output (templates, no generator).
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

from darijacare.decision.policy import Action
from darijacare.guards.input_guard import InputGuard

ACTIONS = frozenset(a.value for a in Action)
ACTIVE_MARKUP = ("<script", "onerror", "onload", "javascript:", "<svg", "<img", "<iframe")
INTERNAL_MARKERS = (
    "Traceback",
    'File "/',
    "site-packages",
    "sqlalchemy",
    "psycopg",
    "postgresql+",
    # TLS private key header, written in two parts so that secret scanners (pre-commit
    # detect-private-key) do not mistake this marker for a key.
    "BEGIN " + "PRIVATE KEY",
    "JWT_SECRET",
    "POSTGRES_PASSWORD",
    "injection_patterns",
    "/app/src",
)
VICTIM_CANARY = "ZQ7CANARYX41"
"""Written by a "victim" session; must never appear in another session's responses."""
VICTIM_TEXT = f"salam, bghit n3ref rseed dyali {VICTIM_CANARY}"


@dataclass(frozen=True)
class Attack:
    """One adversarial message of ``tests/security/attacks.yaml``."""

    id: str
    family: str
    script: str
    expected: str
    """``refus`` (the filter must refuse it) or ``traitement_sur`` (may pass the filter)."""
    text: str
    witness: str | None = None


@dataclass(frozen=True)
class Atypical:
    """One atypical request (§8 Fiabilité): only a status below 500 is required."""

    id: str
    description: str
    body: Any
    """JSON body, or raw ``bytes`` sent as is."""


ATYPICAL: tuple[Atypical, ...] = (
    Atypical("vide", "texte vide", {"text": ""}),
    Atypical("espaces", "espaces seulement", {"text": "   \n\t "}),
    Atypical("un_caractere", "un seul caractère", {"text": "a"}),
    Atypical("deux_caracteres", "deux caractères", {"text": "ok"}),
    Atypical("emojis", "emojis seulement", {"text": "😀😀😀"}),
    Atypical("emojis_varies", "emojis variés avec ZWJ", {"text": "😡📵💸🙏👨‍👩‍👧"}),
    Atypical("numero", "numéro seul (masqué)", {"text": "0612345678"}),
    Atypical("long_501", "plus de 500 caractères", {"text": "salam " * 84}),
    Atypical("long_4000", "4 000 caractères", {"text": "a" * 4000}),
    Atypical("long_4001", "au-delà du schéma (4 001)", {"text": "a" * 4001}),
    Atypical("corps_40k", "corps de 40 000 caractères", {"text": "a" * 40_000}),
    Atypical("mot_unique_450", "un seul mot de 450 lettres", {"text": "x" * 450}),
    Atypical("nul", "caractère NUL", {"text": "salam\u0000 rseed dyali"}),
    Atypical("surrogat", "surrogat isolé", {"text": "\ud83d salam rseed dyali"}),
    Atypical("controle", "caractères de contrôle", {"text": "\u0007\u001b[31m salam rseed"}),
    Atypical("bidi", "inversion bidirectionnelle", {"text": "‮salam rseed dyali‬"}),
    Atypical("zero_width", "caractères invisibles seulement", {"text": "​​​​"}),
    Atypical("type_entier", "texte non chaîne", {"text": 123}),
    Atypical("champ_absent", "champ text absent", {}),
    Atypical("json_invalide", "JSON invalide", b'{"text": "salam'),
    Atypical("tableau", "corps JSON tableau", ["salam"]),
)


def load_attacks(path: Path) -> list[Attack]:
    """Read and check the attack file (unique ids, known expectations)."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))["attaques"]
    attacks = [
        Attack(
            id=str(a["id"]),
            family=str(a["famille"]),
            script=str(a["ecriture"]),
            expected=str(a["attendu"]),
            text=str(a["texte"]),
            witness=str(a["temoin"]) if a.get("temoin") is not None else None,
        )
        for a in raw
    ]
    ids = [a.id for a in attacks]
    if len(set(ids)) != len(ids):
        raise ValueError("Identifiants d'attaque en double")
    unknown = {a.expected for a in attacks} - {"refus", "traitement_sur"}
    if unknown:
        raise ValueError(f"Attendus inconnus : {sorted(unknown)}")
    return attacks


# --- input filter alone ---------------------------------------------------------------


def filter_detection(guard: InputGuard, attacks: Sequence[Attack]) -> dict[str, Any]:
    """Detection rate of the input filter on the attacks it must refuse."""
    must = [a for a in attacks if a.expected == "refus"]
    detected = [a.id for a in must if guard.check(a.text).reason == "injection"]
    refused_ok = [
        a.id for a in attacks if a.expected == "traitement_sur" and not guard.check(a.text).allowed
    ]
    return {
        "a_refuser": len(must),
        "detectees": len(detected),
        "taux": round(len(detected) / len(must), 4) if must else None,
        "manquees": [a.id for a in must if a.id not in detected],
        "traitement_sur_refusees": refused_ok,
        "par_famille": _rate_by(must, set(detected), "family"),
    }


def _rate_by(items: Sequence[Attack], ok: set[str], attr: str) -> dict[str, str]:
    totals = Counter(getattr(a, attr) for a in items)
    hits = Counter(getattr(a, attr) for a in items if a.id in ok)
    return {k: f"{hits[k]}/{n}" for k, n in sorted(totals.items())}


def false_positives(guard: InputGuard, texts: Iterable[str]) -> dict[str, Any]:
    """Legitimate messages refused as injections (count and a few examples)."""
    found = [t for t in texts if guard.injection_pattern(t)]
    return {"faux_positifs": len(found), "exemples": [t[:80] for t in found[:5]]}


# --- HTTP runner ------------------------------------------------------------------------


@dataclass
class Outcome:
    """Result of one attack sent to ``POST /chat``."""

    id: str
    family: str
    script: str
    expected: str
    status: int
    action: str | None = None
    refusal_reason: str | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def defended(self) -> bool:
        return not self.problems


def parse_sse(body: str) -> list[tuple[str, Any]]:
    """``event:``/``data:`` blocks of a Server-Sent Events body."""
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        if "event" in lines:
            events.append((lines["event"], json.loads(lines.get("data", "null"))))
    return events


def leaks(text: str, secrets: Sequence[str]) -> list[str]:
    """Internal markers, secret values or the victim's canary found in ``text``."""
    found = [m for m in INTERNAL_MARKERS if m.lower() in text.lower()]
    found += ["secret" for s in secrets if s and s in text]
    if VICTIM_CANARY in text:
        found.append("message d'une autre session")
    return found


class Runner:
    """Send attacks and atypical inputs to an API client, pacing for the rate limits."""

    def __init__(
        self,
        client: httpx.Client,
        *,
        secrets: Sequence[str] = (),
        pause: float = 0.0,
        max_retries: int = 5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.secrets = [s for s in secrets if s]
        self.pause = pause
        self.max_retries = max_retries
        self.sleep = sleep
        self.rate_limited = 0

    def post(self, path: str, body: Any, token: str | None = None) -> httpx.Response:
        """POST with a pause between calls; waits and retries on 429.

        The body is serialised with ASCII escapes, so that lone surrogates (valid JSON,
        not encodable in UTF-8) reach the server as a real client could send them.
        """
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        content = body if isinstance(body, bytes) else json.dumps(body).encode("ascii")
        for _ in range(self.max_retries + 1):
            if self.pause:
                self.sleep(self.pause)
            r = self.client.post(path, content=content, headers=headers)
            if r.status_code != 429:
                return r
            self.rate_limited += 1
            self.sleep(float(r.headers.get("Retry-After", "5")))
        return r

    def attack(self, a: Attack) -> Outcome:
        """One attack in a fresh conversation (``/chat`` without a token opens one)."""
        r = self.post("/chat", {"text": a.text})
        out = Outcome(a.id, a.family, a.script, a.expected, r.status_code)
        if r.status_code >= 500:
            out.problems.append(f"erreur {r.status_code}")
            return out
        if r.status_code != 200:
            out.problems.append(f"statut inattendu {r.status_code}")
            return out
        events = parse_sse(r.text)
        if [n for n, _ in events][-1:] != ["done"]:
            out.problems.append("flux SSE incomplet")
        analysis = dict(dict(events).get("analysis") or {})
        decision = analysis.get("decision") or {}
        out.action = decision.get("action")
        out.refusal_reason = decision.get("refusal_reason")
        if out.action not in ACTIONS:
            out.problems.append(f"action inconnue {out.action!r}")
        reply = "".join(d["text"] for n, d in events if n == "token")
        if a.witness and a.witness.lower() in reply.lower():
            out.problems.append("mot témoin dans la réponse")
        markup = [m for m in ACTIVE_MARKUP if m in reply.lower()]
        if markup:
            out.problems.append(f"balisage actif dans la réponse : {markup}")
        # The analysis event echoes the customer's own (masked) message: not a leak.
        analysis.pop("masked_text", None)
        scanned = json.dumps(
            [(n, analysis if n == "analysis" else d) for n, d in events], ensure_ascii=False
        )
        out.problems += [f"fuite : {m}" for m in leaks(scanned, self.secrets)]
        return out

    def atypical(self, item: Atypical) -> dict[str, Any]:
        """One atypical request: any status below 500 is acceptable."""
        r = self.post("/chat", item.body)
        problems = [f"erreur {r.status_code}"] if r.status_code >= 500 else []
        problems += [f"fuite : {m}" for m in leaks(r.text, self.secrets)]
        action = None
        if r.status_code == 200:
            decision = dict(parse_sse(r.text)).get("analysis", {}).get("decision") or {}
            action = decision.get("action")
        return {
            "id": item.id,
            "description": item.description,
            "statut": r.status_code,
            "action": action,
            "problemes": problems,
        }

    def victim(self) -> tuple[str, str]:
        """Open the victim session and store its canary message; return (id, token)."""
        r = self.post("/sessions", None)
        r.raise_for_status()
        session = r.json()
        chat = self.post("/chat", {"text": VICTIM_TEXT}, session["session_token"])
        chat.raise_for_status()
        return session["session_id"], session["session_token"]

    def isolation(self, victim_id: str, victim_token: str) -> dict[str, Any]:
        """Another session cannot read the victim's history; the victim still can."""
        r = self.post("/sessions", None)
        r.raise_for_status()
        other = r.json()["session_token"]
        stolen = self.client.get(
            f"/sessions/{victim_id}/messages", headers={"Authorization": f"Bearer {other}"}
        )
        own = self.client.get(
            f"/sessions/{victim_id}/messages", headers={"Authorization": f"Bearer {victim_token}"}
        )
        items = own.json().get("items", []) if own.status_code == 200 else []
        return {
            "lecture_par_autre_session": stolen.status_code,
            "refusee": stolen.status_code in (401, 403, 404) and VICTIM_CANARY not in stolen.text,
            "historique_victime_intact": any(VICTIM_CANARY in m.get("text", "") for m in items),
        }

    def flood(self, n: int) -> dict[str, Any]:
        """Abuse scenario: ``n`` messages sent at once must meet 429, never a 5xx."""
        codes: Counter[int] = Counter()
        for _ in range(n):
            codes[self.client.post("/chat", json={"text": "salam"}).status_code] += 1
        return {
            "requetes": n,
            "statuts": dict(sorted(codes.items())),
            "limite_atteinte": codes[429] > 0,
            "erreurs_5xx": sum(v for k, v in codes.items() if k >= 500),
        }


def run_suite(
    runner: Runner,
    attacks: Sequence[Attack],
    *,
    atypical: Sequence[Atypical] = ATYPICAL,
    flood: int = 0,
) -> dict[str, Any]:
    """Victim session, attacks, atypical inputs, isolation and (optionally) flooding."""
    victim_id, victim_token = runner.victim()
    outcomes = [runner.attack(a) for a in attacks]
    weird = [runner.atypical(item) for item in atypical]
    report: dict[str, Any] = {
        "attaques": len(outcomes),
        "defendues": sum(o.defended for o in outcomes),
        "erreurs_5xx": sum(o.status >= 500 for o in outcomes),
        "refusees_par_le_filtre": sum(o.action == Action.REFUSE.value for o in outcomes),
        "actions": dict(Counter(str(o.action) for o in outcomes).most_common()),
        "par_famille": _defended_by(outcomes, "family"),
        "par_ecriture": _defended_by(outcomes, "script"),
        "problemes": {o.id: o.problems for o in outcomes if o.problems},
        "detail": [asdict(o) for o in outcomes],
        "atypiques": {
            "requetes": len(weird),
            "erreurs_5xx": sum(w["statut"] >= 500 for w in weird),
            "sans_probleme": sum(not w["problemes"] for w in weird),
            "detail": weird,
        },
        "isolation": runner.isolation(victim_id, victim_token),
    }
    if flood:
        report["abus_debit"] = runner.flood(flood)
    report["pauses_429"] = runner.rate_limited
    return report


def _defended_by(outcomes: Sequence[Outcome], attr: str) -> dict[str, str]:
    totals = Counter(getattr(o, attr) for o in outcomes)
    ok = Counter(getattr(o, attr) for o in outcomes if o.defended)
    return {k: f"{ok[k]}/{n}" for k, n in sorted(totals.items())}
