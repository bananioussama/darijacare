"""NLU service: one interface, several back-ends.

The backend (API) only knows :class:`NLUService` and :class:`NLUResult`; it never
imports ``laya`` directly. :class:`LayaTelecomModel` reproduces the published
``predict.py`` of ``mballouch/jev-darija-telecom-model`` *exactly*:

* the checkpoint is loaded with
  ``laya.load(path, device=..., backend="eager", compile=False, fast=False)``;
* pass 1 asks ``category`` + the taxonomy's ``extra_questions`` (product,
  urgency, needs_human); pass 2 asks the intent question of the predicted
  category (skipped for single-intent categories such as ``out_of_scope``);
* question wording and option labels come verbatim from ``telecom_taxonomy.json``
  and from the two instruction strings of ``predict.py``.

The model receives the original text (it was trained on raw messages, with
phone numbers written ``06XXXXXXXX``), not ``text_norm``.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from darijacare.data.scripts import detect_script

# Copied verbatim from predict.py (mballouch/jev-darija-telecom-model, Apache-2.0).
CATEGORY_INSTRUCTIONS = (
    "Which area of telecom customer service is this Moroccan Darija message about?"
)
INTENT_INSTRUCTIONS = (
    "Which request does this customer message make? Choose the main explicit request, "
    "respecting negation."
)


@dataclass(frozen=True)
class Scored:
    """A label with its probability."""

    label: str
    p: float


@dataclass
class NLUResult:
    """Everything the decision engine and the UI need about one message."""

    text: str
    script: str
    category: str
    category_confidence: float
    intent: str
    intent_confidence: float
    """Probability of the intent inside the predicted category (pass 2)."""
    intent_joint_confidence: float
    """``category_confidence * intent_confidence``: confidence in the end-to-end label."""
    product: str
    product_confidence: float
    urgency: int
    urgency_confidence: float
    needs_human: bool
    needs_human_probability: float
    category_top2: list[Scored] = field(default_factory=list)
    intent_top2: list[Scored] = field(default_factory=list)
    urgency_probabilities: dict[str, float] = field(default_factory=dict)
    probabilities: dict[str, dict[str, float]] = field(default_factory=dict)
    """Full distributions: ``category``, ``intent`` (inside the predicted category), ``product``."""
    model_version: str = ""
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return asdict(self)


class NLUService(Protocol):
    """Interface used by the rest of the application."""

    model_version: str

    def predict(self, text: str) -> NLUResult:
        """Analyse one customer message."""
        ...

    def predict_batch(self, texts: Sequence[str], batch_size: int = 16) -> list[NLUResult]:
        """Analyse several messages."""
        ...


def _top(probabilities: dict[str, float], k: int = 2) -> list[Scored]:
    items = sorted(probabilities.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
    return [Scored(label=str(lbl), p=float(p)) for lbl, p in items]


def build_questions(taxonomy: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Laya questions exactly as ``predict.py`` builds them (shared by training and inference).

    Returns:
        ``(first_questions, intent_questions)``: pass-1 questions (category + the
        taxonomy's ``extra_questions``) and, for each category with more than one
        intent, its pass-2 intent question.
    """
    categories = taxonomy["categories"]
    first: dict[str, Any] = {
        "category": {
            "type": "choice",
            "instructions": CATEGORY_INSTRUCTIONS,
            "criteria": {k: v["description"] for k, v in categories.items()},
        },
        **taxonomy["extra_questions"],
    }
    intent: dict[str, dict[str, Any]] = {
        c: {
            "type": "choice",
            "instructions": INTENT_INSTRUCTIONS,
            "criteria": {k: v["description"] for k, v in b["intents"].items()},
        }
        for c, b in categories.items()
        if len(b["intents"]) > 1
    }
    return first, intent


class LayaTelecomModel:
    """Published Laya telecom checkpoint, used exactly as its ``predict.py`` does."""

    def __init__(
        self,
        checkpoint: str | Path,
        device: str | None = None,
        model_version: str | None = None,
        needs_human_threshold: float = 0.5,
    ) -> None:
        import laya

        path = Path(checkpoint)
        if not path.exists():
            raise FileNotFoundError(f"Checkpoint introuvable : {path}")
        self.checkpoint = path
        self.taxonomy: dict[str, Any] = json.loads(
            (path / "telecom_taxonomy.json").read_text(encoding="utf-8")
        )
        self.agent = laya.load(str(path), device=device, backend="eager", compile=False, fast=False)
        self.needs_human_threshold = needs_human_threshold
        self.model_version = model_version or path.name
        self.first_questions, self.intent_questions = build_questions(self.taxonomy)

    def first_pass(self, text: str) -> dict[str, Any]:
        """Pass 1: category, product, urgency, needs_human (raw laya answers)."""
        answers: dict[str, Any] = self.agent.predict(text, self.first_questions)["answers"]
        return answers

    def intent_pass(self, text: str, category: str) -> tuple[str, dict[str, float]]:
        """Pass 2: intent inside ``category`` -> (intent, probabilities)."""
        if category not in self.intent_questions:
            only = next(iter(self.taxonomy["categories"][category]["intents"]))
            return only, {only: 1.0}
        answer = self.agent.predict(text, {"intent": self.intent_questions[category]})["answers"][
            "intent"
        ]
        return str(answer["choice"]), {k: float(v) for k, v in answer["probabilities"].items()}

    def _build(
        self,
        text: str,
        first: dict[str, Any],
        intent: str,
        intent_probs: dict[str, float],
        latency_ms: float,
    ) -> NLUResult:
        cat_probs = {k: float(v) for k, v in first["category"]["probabilities"].items()}
        category = str(first["category"]["choice"])
        levels = {str(k): float(v) for k, v in first["urgency"]["probabilities"].items()}
        urgency = max(levels, key=lambda k: levels[k])
        product_probs = {k: float(v) for k, v in first["product"]["probabilities"].items()}
        product = str(first["product"]["choice"])
        p_human = float(first["needs_human"]["noul"])  # laya "noul" answer = P(true)
        return NLUResult(
            text=text,
            script=detect_script(text),
            category=category,
            category_confidence=cat_probs[category],
            intent=intent,
            intent_confidence=intent_probs[intent],
            intent_joint_confidence=cat_probs[category] * intent_probs[intent],
            product=product,
            product_confidence=product_probs.get(product, 0.0),
            urgency=int(urgency),
            urgency_confidence=levels[urgency],
            needs_human=p_human >= self.needs_human_threshold,
            needs_human_probability=p_human,
            category_top2=_top(cat_probs),
            intent_top2=_top(intent_probs),
            urgency_probabilities=levels,
            probabilities={"category": cat_probs, "intent": intent_probs, "product": product_probs},
            model_version=self.model_version,
            latency_ms=latency_ms,
        )

    def predict(self, text: str) -> NLUResult:
        """Two-pass prediction, identical to the published ``predict.py``."""
        start = time.perf_counter()
        first = self.first_pass(text)
        intent, intent_probs = self.intent_pass(text, str(first["category"]["choice"]))
        return self._build(text, first, intent, intent_probs, (time.perf_counter() - start) * 1000)

    def predict_batch(self, texts: Sequence[str], batch_size: int = 16) -> list[NLUResult]:
        """Throughput path with ``laya``'s ``predict_batch``.

        Pass 1 runs over all texts; pass 2 groups texts by predicted category and
        asks that category's intent question in batches. Results keep input order.
        Batching can change probabilities by tiny floating-point amounts (padding);
        :func:`predict` is the reference path.
        """
        texts = list(texts)
        if not texts:
            return []
        start = time.perf_counter()
        firsts = [
            r["answers"]
            for r in self.agent.predict_batch(texts, self.first_questions, batch_size=batch_size)
        ]
        intents: list[tuple[str, dict[str, float]]] = [("", {})] * len(texts)
        groups: dict[str, list[int]] = {}
        for i, f in enumerate(firsts):
            groups.setdefault(str(f["category"]["choice"]), []).append(i)
        for category, idx in groups.items():
            if category not in self.intent_questions:
                only = next(iter(self.taxonomy["categories"][category]["intents"]))
                for i in idx:
                    intents[i] = (only, {only: 1.0})
                continue
            res = self.agent.predict_batch(
                [texts[i] for i in idx],
                {"intent": self.intent_questions[category]},
                batch_size=batch_size,
            )
            for i, r in zip(idx, res, strict=True):
                a = r["answers"]["intent"]
                intents[i] = (
                    str(a["choice"]),
                    {k: float(v) for k, v in a["probabilities"].items()},
                )
        per_item = (time.perf_counter() - start) * 1000 / len(texts)
        return [
            self._build(t, f, it, ip, per_item)
            for t, f, (it, ip) in zip(texts, firsts, intents, strict=True)
        ]

    def intent_with_category(
        self, texts: Sequence[str], categories: Sequence[str], batch_size: int = 16
    ) -> list[str]:
        """Pass 2 only, with a *given* category for each text (e.g. the gold category).

        Used to measure "intent given the right category" the way a model card may
        define it: the intent question of the true category, for every message.
        """
        out = [""] * len(texts)
        groups: dict[str, list[int]] = {}
        for i, c in enumerate(categories):
            groups.setdefault(c, []).append(i)
        for category, idx in groups.items():
            if category not in self.intent_questions:
                only = next(iter(self.taxonomy["categories"][category]["intents"]))
                for i in idx:
                    out[i] = only
                continue
            res = self.agent.predict_batch(
                [texts[i] for i in idx],
                {"intent": self.intent_questions[category]},
                batch_size=batch_size,
            )
            for i, r in zip(idx, res, strict=True):
                out[i] = str(r["answers"]["intent"]["choice"])
        return out
