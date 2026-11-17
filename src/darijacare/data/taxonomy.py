"""Loader for ``telecom_taxonomy.json`` (12 categories, 75 intents, 11 products).

Labels are kept *exactly* as written in the taxonomy: the published model scores
these strings as multiple-choice options, so they must never be renamed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPTS: tuple[str, ...] = ("arabic", "arabizi", "mixed")
URGENCY_LEVELS: tuple[int, ...] = (0, 1, 2, 3)


@dataclass(frozen=True)
class Taxonomy:
    """Immutable view of the telecom taxonomy."""

    name: str
    categories: dict[str, list[str]]
    """Category -> ordered list of its intents."""
    intent_descriptions: dict[str, str]
    category_descriptions: dict[str, str]
    products: list[str]
    urgency_criteria: list[str]
    raw: dict[str, Any]

    @property
    def intents(self) -> list[str]:
        """All intents, in taxonomy order."""
        return [i for intents in self.categories.values() for i in intents]

    @property
    def intent_to_category(self) -> dict[str, str]:
        """Map each intent to its (unique) category."""
        return {i: c for c, intents in self.categories.items() for i in intents}

    def category_of(self, intent: str) -> str:
        """Return the category of ``intent`` (``KeyError`` if unknown)."""
        return self.intent_to_category[intent]


def load_taxonomy(path: Path) -> Taxonomy:
    """Parse the taxonomy JSON file and check its internal consistency.

    Raises:
        ValueError: if an intent appears in two categories or a section is missing.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    categories: dict[str, list[str]] = {}
    intent_desc: dict[str, str] = {}
    cat_desc: dict[str, str] = {}
    seen: set[str] = set()
    for cat, body in raw["categories"].items():
        cat_desc[cat] = body.get("description", "")
        categories[cat] = []
        for intent, ibody in body["intents"].items():
            if intent in seen:
                raise ValueError(f"Intention {intent!r} présente dans plusieurs catégories")
            seen.add(intent)
            categories[cat].append(intent)
            intent_desc[intent] = ibody.get("description", "")
    extra = raw.get("extra_questions", {})
    try:
        products = list(extra["product"]["criteria"].keys())
        urgency = list(extra["urgency"]["criteria"])
    except KeyError as exc:
        raise ValueError(f"Section extra_questions incomplète : {exc}") from exc
    return Taxonomy(
        name=raw.get("name", ""),
        categories=categories,
        intent_descriptions=intent_desc,
        category_descriptions=cat_desc,
        products=products,
        urgency_criteria=urgency,
        raw=raw,
    )
