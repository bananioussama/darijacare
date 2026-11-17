"""Unit tests for the stratified split with proximity control."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from darijacare.data.normalize import add_normalized_column
from darijacare.data.split import (
    SplitFailed,
    distribution_gaps,
    make_split,
    stratification_key,
)
from tests.conftest import make_row

CFG: dict[str, Any] = {
    "val_fraction": 0.2,
    "stratify_by": ["intent", "script", "generator"],
    "fallback_keys": [["intent", "script"], ["intent"]],
    "min_stratum_size": 5,
    "proximity": {"ngram": 3, "threshold": 0.8, "action": "move_to_train"},
    "max_distribution_gap_points": 15.0,
    "check_columns": ["intent", "script"],
}


def _frame(n: int = 200) -> pd.DataFrame:
    rows = []
    for i in range(n):
        intent = ["balance_check", "recharge_how"][i % 2]
        script = ["arabizi", "mixed"][(i // 2) % 2]
        gen = "gemini-3.8-flash" if i % 37 == 0 else "claude-opus-5.5"
        text = f"message numero {i} sur {intent} {i * 7919 % 9973}"
        rows.append(make_row(i, text, intent=intent, script=script, generator=gen))
    return add_normalized_column(pd.DataFrame(rows))


def test_stratification_key_falls_back_for_rare_strata() -> None:
    df = _frame()
    key = stratification_key(df, CFG["stratify_by"], CFG["fallback_keys"], 5)
    assert key.notna().all()
    assert key.value_counts().min() >= 2
    rare = df["generator"] == "gemini-3.8-flash"
    assert not key[rare].str.startswith("L0:").any()
    assert key[~rare].str.startswith("L0:").all()


def test_stratification_key_rest_bucket() -> None:
    df = pd.DataFrame({"a": ["x"] * 10 + ["y", "z"], "b": ["1"] * 12})
    key = stratification_key(df, ["a"], [], 5)
    assert (key[:10] == "L0:x").all()
    assert (key[10:] == "rest").all()


def test_split_is_deterministic_and_disjoint() -> None:
    df = _frame()
    tr1, va1, _, _ = make_split(df, CFG, seed=42)
    _tr2, va2, _, _ = make_split(df.sample(frac=1, random_state=0), CFG, seed=42)
    assert list(va1["id"]) == list(va2["id"])  # independent of input order
    assert set(tr1["id"]).isdisjoint(va1["id"])
    assert len(tr1) + len(va1) == len(df)
    assert len(va1) == pytest.approx(0.2 * len(df), abs=2)


def test_different_seed_gives_different_split() -> None:
    df = _frame()
    _, va1, _, _ = make_split(df, CFG, seed=1)
    _, va2, _, _ = make_split(df, CFG, seed=2)
    assert set(va1["id"]) != set(va2["id"])


def test_near_duplicates_are_moved_back_to_train() -> None:
    df = _frame()
    # Each row gets a near twin (same text + "!"), so many val rows have a twin in train.
    twins = df.copy()
    twins["id"] = twins["id"] + "b"
    twins["text"] = twins["text"] + " !"
    full = add_normalized_column(
        pd.concat([df, twins], ignore_index=True).drop(columns="text_norm")
    )
    train, val, moved, info = make_split(full, CFG, seed=42)
    assert info["val_moved_to_train"] > 0
    assert set(moved["query_id"]).isdisjoint(val["id"])
    assert set(moved["query_id"]) <= set(train["id"])


def test_distribution_gap_check_fails() -> None:
    df = _frame()
    with pytest.raises(SplitFailed, match="Écart de distribution"):
        make_split(df, {**CFG, "max_distribution_gap_points": 0.0}, seed=42)


def test_distribution_gaps() -> None:
    a = pd.DataFrame({"c": ["x", "x", "y", "y"]})
    b = pd.DataFrame({"c": ["x", "x", "x", "y"]})
    assert distribution_gaps(a, b, ["c"]) == {"c": 25.0}
