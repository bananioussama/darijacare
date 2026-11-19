"""Gold set tooling: schema, composition (Tableau 38), proximity, inter-annotator agreement.

The rows below are placeholders for the checks, not gold messages: the real gold set
is written by the team (docs/gold.md).
"""

from __future__ import annotations

import pandas as pd
import pytest

from darijacare.data import gold
from darijacare.data.taxonomy import Taxonomy

TAXONOMY = Taxonomy(
    name="essai",
    categories={"prepaid_credit": ["balance_check", "recharge_issue"], "sim_line": ["lost_stolen"]},
    intent_descriptions={},
    category_descriptions={},
    products=["mobile", "unknown"],
    urgency_criteria=[],
    raw={},
)
TEXTS = {
    "arabic": "رسالة تجريبية رقم {i} للاختبار فقط",
    "arabizi": "rissala tajribiya ra9m {i} ghir l test",
    "mixed": "message de test {i} ghir bach njerbo",
}


def frame(counts: dict[str, int], edge: int = 0) -> pd.DataFrame:
    rows = []
    for script, n in counts.items():
        for _ in range(n):
            i = len(rows)
            rows.append(
                {
                    "id": f"g{i}",
                    "text": TEXTS[script].format(i=i),
                    "script": script,
                    "category": "prepaid_credit",
                    "intent": "balance_check",
                    "product": "mobile",
                    "urgency": 0,
                    "needs_human": False,
                    "cas_limite": False,
                    "annotateur": "A",
                }
            )
    for row in rows[:edge]:
        row["cas_limite"] = True
    return pd.DataFrame(rows)


def test_schema_problems_are_reported() -> None:
    df = frame({"arabizi": 3})
    df.loc[0, "intent"] = "lost_stolen"  # outside its category
    df.loc[1, "urgency"] = 5
    df.loc[2, "id"] = "g0"
    problems = gold.schema_problems(df, TAXONOMY)
    assert any("en double" in p for p in problems)
    assert any(p.startswith("urgency invalide") for p in problems)
    assert any("hors de sa catégorie" in p for p in problems)
    assert gold.schema_problems(df.drop(columns="annotateur"), TAXONOMY) == [
        "colonnes absentes : ['annotateur']"
    ]


def test_composition_against_the_target_table() -> None:
    comp = gold.composition(frame({"arabic": 38, "arabizi": 30, "mixed": 32}, edge=10))
    assert comp["arabic"] == {"part": 0.28, "cible": 0.35, "ok": False}
    assert comp["mixed"] == {"part": 0.32, "cible": 0.25, "ok": False}
    assert comp["arabizi"]["ok"] and comp["cas_limite"]["ok"]
    balanced = gold.composition(frame({"arabic": 45, "arabizi": 30, "mixed": 25}, edge=10))
    assert all(v["ok"] for v in balanced.values())


def test_check_gold_size_composition_and_proximity(monkeypatch: pytest.MonkeyPatch) -> None:
    df = frame({"arabic": 45, "arabizi": 30, "mixed": 25}, edge=10)
    report = gold.check_gold(df, TAXONOMY, synthetic_texts=["un message synthétique sans rapport"])
    assert report["problemes"] == ["100 messages (minimum 300)"] and not report["ok"]
    monkeypatch.setattr(gold, "MIN_MESSAGES", 100)
    assert gold.check_gold(df, TAXONOMY)["ok"]
    # the placeholder texts differ only by a number: the copy and its look-alikes are caught
    copied = gold.check_gold(df, TAXONOMY, synthetic_texts=[df.loc[50, "text"]])
    assert copied["proches_du_synthetique"] >= 1 and not copied["ok"]


def test_agreement_uses_cohen_kappa_and_weighted_kappa_for_urgency() -> None:
    first = frame({"arabizi": 4})
    first["intent"] = ["balance_check", "recharge_issue", "balance_check", "recharge_issue"]
    first["urgency"] = [0, 1, 2, 3]
    second = first[["id", "category", "intent", "product", "urgency", "needs_human"]].copy()
    perfect = gold.agreement(first, second)
    assert perfect["intent"] == 1.0 and perfect["urgency"] == 1.0 and perfect["ok"]
    second["intent"] = ["balance_check", "balance_check", "recharge_issue", "recharge_issue"]
    second["urgency"] = [0, 1, 3, 3]
    partial = gold.agreement(first, second)
    assert partial["intent"] == 0.0 and not partial["ok"]
    assert 0.8 < partial["urgency"] < 1.0
