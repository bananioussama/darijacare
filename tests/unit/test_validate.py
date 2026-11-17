"""Unit tests for the blocking validation checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from darijacare.data.normalize import Normalizer
from darijacare.data.taxonomy import load_taxonomy
from darijacare.data.validate import (
    ValidationFailed,
    build_schema,
    check_cross_split,
    check_schema,
    deduplicate,
    validate_split,
)
from tests.conftest import make_row

VCFG: dict[str, Any] = {
    "min_script_coherence": 0.99,
    "duplicate_conflict_policy": "drop_all",
    "expected_rows": {},
}
PCFG = {"ngram": 3, "threshold": 0.8, "block_on": "same_intent", "max_allowed_pairs": 0}


@pytest.fixture
def schema(taxonomy_path: Path):  # type: ignore[no-untyped-def]
    return build_schema(load_taxonomy(taxonomy_path))


def test_valid_frame_passes(mini_df: pd.DataFrame, schema) -> None:  # type: ignore[no-untyped-def]
    check_schema(mini_df, schema, "train")


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("intent", "unknown_intent"),
        ("category", "billing_payment"),
        ("product", "home_fiber"),
        ("urgency", 4),
        ("script", "latin"),
        ("generator", "gpt"),
        ("text", "   "),
    ],
)
def test_invalid_labels_fail(mini_df: pd.DataFrame, schema, column: str, value: Any) -> None:  # type: ignore[no-untyped-def]
    df = mini_df.copy()
    df.loc[0, column] = value
    with pytest.raises(ValidationFailed):
        check_schema(df, schema, "train")


def test_intent_must_belong_to_category(mini_df: pd.DataFrame, schema) -> None:  # type: ignore[no-untyped-def]
    df = mini_df.copy()
    df.loc[0, "category"] = "out_of_scope"  # balance_check is in prepaid_credit
    with pytest.raises(ValidationFailed, match="intention_dans_categorie"):
        check_schema(df, schema, "train")


def test_duplicate_ids_fail(mini_df: pd.DataFrame, schema) -> None:  # type: ignore[no-untyped-def]
    df = mini_df.copy()
    df.loc[1, "id"] = df.loc[0, "id"]
    with pytest.raises(ValidationFailed):
        check_schema(df, schema, "train")


def test_unexpected_column_fails(mini_df: pd.DataFrame, schema) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationFailed):
        check_schema(mini_df.assign(extra=1), schema, "train")


def test_expected_row_count(mini_df: pd.DataFrame, schema) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationFailed, match="lignes au lieu de"):
        validate_split(mini_df, "train", schema, {**VCFG, "expected_rows": {"train": 61}})


def test_script_coherence_threshold(mini_df: pd.DataFrame, schema) -> None:  # type: ignore[no-untyped-def]
    df = mini_df.copy()
    df.loc[0, "text"] = "رصيدي سالا"  # Arabic text labelled arabizi
    # 59/60 = 98.3 % < 99 % -> blocking
    with pytest.raises(ValidationFailed, match="cohérence"):
        validate_split(df, "train", schema, VCFG)
    # With a lower threshold it passes and the exception is reported.
    _, rep = validate_split(df, "train", schema, {**VCFG, "min_script_coherence": 0.95})
    assert [e["id"] for e in rep.script_exceptions] == ["r-0000"]


def test_deduplicate_identical_copies_keep_first() -> None:
    df = pd.DataFrame([make_row(2, "salam"), make_row(1, "salam"), make_row(3, "autre")])
    out, removed = deduplicate(df, "drop_all")
    assert sorted(out["id"]) == ["r-0001", "r-0003"]
    assert removed == [
        {
            "id": "r-0002",
            "text": "salam",
            "intent": "balance_check",
            "reason": "copie_identique",
            "kept_id": "r-0001",
        }
    ]


@pytest.mark.parametrize(
    ("policy", "kept"), [("drop_all", ["r-0003"]), ("keep_first", ["r-0001", "r-0003"])]
)
def test_deduplicate_conflicting_labels(policy: str, kept: list[str]) -> None:
    df = pd.DataFrame(
        [
            make_row(1, "ch7al b9a?", intent="balance_check"),
            make_row(2, "ch7al b9a?", intent="recharge_how"),
            make_row(3, "autre"),
        ]
    )
    out, removed = deduplicate(df, policy)
    assert sorted(out["id"]) == kept
    assert all(r["reason"] == "labels_divergents" for r in removed)


def test_deduplicate_bad_policy() -> None:
    with pytest.raises(ValueError):
        deduplicate(pd.DataFrame([make_row(1, "a")]), "random")


def test_cross_split_rejects_shared_text(mini_df: pd.DataFrame) -> None:
    test = pd.DataFrame([make_row(900, mini_df.loc[0, "text"])])
    with pytest.raises(ValidationFailed, match="identiques"):
        check_cross_split(mini_df, test, PCFG, Normalizer())


def test_cross_split_rejects_shared_id(mini_df: pd.DataFrame) -> None:
    test = pd.DataFrame([make_row(0, "texte totalement différent")])
    with pytest.raises(ValidationFailed, match="ids communs"):
        check_cross_split(mini_df, test, PCFG, Normalizer())


def test_cross_split_near_duplicate_same_intent_blocks(mini_df: pd.DataFrame) -> None:
    near = mini_df.loc[0, "text"].upper()  # identical after normalisation
    test = pd.DataFrame([make_row(900, near, intent=mini_df.loc[0, "intent"])])
    with pytest.raises(ValidationFailed, match="quasi identiques"):
        check_cross_split(mini_df, test, PCFG, Normalizer())


def test_cross_split_near_duplicate_other_intent_is_reported(mini_df: pd.DataFrame) -> None:
    near = mini_df.loc[0, "text"].upper()
    test = pd.DataFrame([make_row(900, near, intent="non_telecom")])
    frame, summary = check_cross_split(mini_df, test, PCFG, Normalizer())
    assert summary["pairs_cross_intent"] == 1 and summary["pairs_same_intent"] == 0
    assert frame.loc[0, "reference_id"] == "r-0000"
