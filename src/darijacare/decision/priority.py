"""Escalation priority score (cahier des charges, F-DEC-02).

``score = 100 × (w_urg · urgency/3 + w_hum · p(needs_human) + w_conf · (1 − confidence)) / Σw``
plus a bonus for sensitive intents or categories (fraud, theft, money), capped at 100.
Weights and bonuses live in ``configs/decision.yaml``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Priority:
    """Priority score (0–100) with its level label and the contributions that explain it."""

    score: float
    level: str
    contributions: dict[str, float]


def priority_score(
    *,
    urgency: int,
    needs_human_probability: float,
    confidence: float,
    intent: str,
    category: str,
    cfg: Mapping[str, Any],
) -> Priority:
    """Compute the escalation priority of one analysed message."""
    w = cfg["weights"]
    total_w = float(w["urgency"] + w["needs_human"] + w["uncertainty"]) or 1.0
    parts = {
        "urgence": 100 * w["urgency"] * max(0, min(urgency, 3)) / 3 / total_w,
        "needs_human": 100
        * w["needs_human"]
        * min(max(needs_human_probability, 0.0), 1.0)
        / total_w,
        "incertitude": 100 * w["uncertainty"] * (1 - min(max(confidence, 0.0), 1.0)) / total_w,
    }
    bonus = float(cfg.get("bonus", {}).get("intents", {}).get(intent, 0))
    bonus += float(cfg.get("bonus", {}).get("categories", {}).get(category, 0))
    if bonus:
        parts["bonus"] = bonus
    score = round(min(100.0, sum(parts.values())), 2)
    return Priority(
        score, priority_level(score, cfg["levels"]), {k: round(v, 2) for k, v in parts.items()}
    )


def priority_level(score: float, levels: Mapping[str, float]) -> str:
    """Label of the highest level whose floor is reached (``basse`` otherwise)."""
    for name, floor in sorted(levels.items(), key=lambda kv: -kv[1]):
        if score >= floor:
            return name
    return "basse"


def order_queue(items: Iterable[tuple[str, Priority, float]]) -> list[str]:
    """Order escalation ids by priority (desc), then arrival time (asc) for ties.

    ``items`` are ``(id, priority, arrival_timestamp)`` tuples.
    """
    return [i for i, _p, _t in sorted(items, key=lambda x: (-x[1].score, x[2], x[0]))]
