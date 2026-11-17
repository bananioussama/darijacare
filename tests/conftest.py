"""Shared fixtures: a tiny synthetic taxonomy and dataset written to a temp repo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from darijacare.config import Paths, get_paths, load_data_config

REPO_ROOT = Path(__file__).resolve().parents[1]

TAXONOMY: dict[str, Any] = {
    "name": "mini",
    "note": "",
    "sources": {},
    "categories": {
        "prepaid_credit": {
            "description": "",
            "intents": {
                "balance_check": {"description": "", "bitext": [], "example": ""},
                "recharge_how": {"description": "", "bitext": [], "example": ""},
            },
        },
        "out_of_scope": {
            "description": "",
            "intents": {"non_telecom": {"description": "", "bitext": [], "example": ""}},
        },
    },
    "extra_questions": {
        "product": {"criteria": {"prepaid_mobile": "", "unknown": ""}},
        "urgency": {"criteria": ["a", "b", "c", "d"]},
        "needs_human": {"criteria": {"true": "", "false": ""}},
    },
}


def make_row(i: int, text: str, intent: str = "balance_check", **kw: Any) -> dict[str, Any]:
    """Build one valid dataset row."""
    cat = "out_of_scope" if intent == "non_telecom" else "prepaid_credit"
    row = {
        "id": f"r-{i:04d}",
        "text": text,
        "script": "arabizi",
        "category": cat,
        "intent": intent,
        "product": "unknown",
        "urgency": 0,
        "needs_human": False,
        "persona": "étudiant, Fès",
        "generator": "claude-opus-5.5",
        "round": 1,
    }
    row.update(kw)
    return row


@pytest.fixture
def taxonomy_path(tmp_path: Path) -> Path:
    p = tmp_path / "telecom_taxonomy.json"
    p.write_text(json.dumps(TAXONOMY), encoding="utf-8")
    return p


@pytest.fixture
def mini_df() -> pd.DataFrame:
    words = ["solde", "rasid", "recharge", "pass", "internet", "carte", "flous", "dh"]
    rows = []
    for i in range(60):
        intent = ["balance_check", "recharge_how"][i % 2]
        text = f"msg {i} {words[i % 8]} {words[(i * 3) % 8]} n{i * 7919 % 1000}"
        rows.append(make_row(i, text, intent=intent))
    return pd.DataFrame(rows)


@pytest.fixture
def real_paths() -> Paths:
    """Paths of the real repo; skips the test when data/raw has not been ingested."""
    paths = get_paths(REPO_ROOT)
    if not (paths.raw / "train.jsonl").exists():
        pytest.skip("data/raw absent : lancer `dvc repro` d'abord")
    return paths


@pytest.fixture
def data_config() -> dict[str, Any]:
    return load_data_config(get_paths(REPO_ROOT))
