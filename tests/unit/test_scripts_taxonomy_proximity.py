"""Unit tests for script heuristics, taxonomy loading and near-duplicate search."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from darijacare.data.proximity import find_near_pairs, jaccard, ngram_set
from darijacare.data.scripts import detect_script, is_script_coherent, script_features
from darijacare.data.taxonomy import load_taxonomy
from tests.conftest import TAXONOMY

# --- scripts -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "script", "ok"),
    [
        ("الريزو مقطوع من البارح", "arabic", True),
        ("الريزو مقطوع f l'appli", "arabic", True),  # a little Latin is fine
        ("nsit mot de passe dyal l'appli", "arabic", False),
        ("ch7al b9a f solde?", "arabizi", True),
        ("ch7al b9a f الرصيد", "arabizi", False),  # Arabic letter in Arabizi
        ("nsit mot de passe dyal l'appli", "mixed", True),
        ("فين جات l'agence حدا لافاك؟", "mixed", True),
        ("ch7al b9a", "mixed", False),  # no French, single script
    ],
)
def test_is_script_coherent(text: str, script: str, ok: bool) -> None:
    assert is_script_coherent(text, script) is ok


def test_unknown_script_raises() -> None:
    with pytest.raises(ValueError):
        is_script_coherent("salam", "latin")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("بغيت نشارجي", "arabic"),
        ("bghit nchargi 3afak", "arabizi"),
        ("je veux payer la facture dyali", "mixed"),
        ("واش la facture وصلات", "mixed"),
        ("", "arabic"),
    ],
)
def test_detect_script(text: str, expected: str) -> None:
    assert detect_script(text) == expected


def test_script_features_counts() -> None:
    f = script_features("abc دي")
    assert (f.latin_letters, f.arabic_letters) == (3, 2)
    assert f.latin_ratio == pytest.approx(0.6)


# --- taxonomy ----------------------------------------------------------------


def test_load_taxonomy(taxonomy_path: Path) -> None:
    tax = load_taxonomy(taxonomy_path)
    assert tax.intents == ["balance_check", "recharge_how", "non_telecom"]
    assert tax.category_of("non_telecom") == "out_of_scope"
    assert tax.products == ["prepaid_mobile", "unknown"]
    assert len(tax.urgency_criteria) == 4


def test_taxonomy_rejects_intent_in_two_categories(tmp_path: Path) -> None:
    bad = json.loads(json.dumps(TAXONOMY))
    bad["categories"]["out_of_scope"]["intents"]["balance_check"] = {}
    p = tmp_path / "t.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="plusieurs catégories"):
        load_taxonomy(p)


# --- proximity ---------------------------------------------------------------


def test_ngram_set_and_jaccard() -> None:
    assert ngram_set("ab", 3) == {" ab", "ab "}
    assert jaccard("salam", "salam") == 1.0
    assert jaccard("salam", "zzzzz") == 0.0


def test_find_near_pairs_matches_reference_implementation() -> None:
    queries = ["ch7al b9a f solde", "bghit nchargi", "رصيدي سالا"]
    refs = ["ch7al b9a f solde?", "kifach nchargi", "رصيدي سالا بزاف", "ch7al b9a f solde"]
    for threshold in (0.3, 0.5, 0.8):
        got = {
            (p.query_index, p.reference_index)
            for p in find_near_pairs(queries, refs, threshold=threshold)
        }
        want = {
            (i, j)
            for i, q in enumerate(queries)
            for j, r in enumerate(refs)
            if jaccard(q, r) >= threshold
        }
        assert got == want


def test_find_near_pairs_chunking_and_self() -> None:
    base = "salam khoya bghit nchargi 50 dh"
    assert jaccard(base, base + "!") >= 0.8
    texts = [base, base + "!", "autre chose", base]
    pairs = find_near_pairs(texts, texts, threshold=0.8, chunk_size=1, exclude_self=True)
    got = {(p.query_index, p.reference_index) for p in pairs}
    assert got == {(0, 1), (0, 3), (1, 3)}


def test_find_near_pairs_empty() -> None:
    assert find_near_pairs([], ["a"]) == []
