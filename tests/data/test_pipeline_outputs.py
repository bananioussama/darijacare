"""Data tests on the real pipeline outputs (skipped when ``dvc repro`` has not run)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from darijacare.config import Paths
from darijacare.data.normalize import TEL_TOKEN
from darijacare.data.taxonomy import load_taxonomy
from darijacare.io import read_jsonl, sha256_file

pytestmark = pytest.mark.data


def test_raw_hashes_match_pinned_revision(real_paths: Paths, data_config: dict[str, Any]) -> None:
    for name, spec in data_config["source"]["files"].items():
        assert sha256_file(real_paths.raw / name) == spec["sha256"], name


def test_taxonomy_shape(real_paths: Paths) -> None:
    tax = load_taxonomy(real_paths.raw / "telecom_taxonomy.json")
    assert (len(tax.categories), len(tax.intents), len(tax.products)) == (12, 75, 11)


def test_splits_are_disjoint_and_complete(real_paths: Paths) -> None:
    if not (real_paths.processed / "val.jsonl").exists():
        pytest.skip("data/processed absent")
    tr = read_jsonl(real_paths.processed / "train.jsonl")
    va = read_jsonl(real_paths.processed / "val.jsonl")
    te = read_jsonl(real_paths.processed / "test.jsonl")
    raw_test = read_jsonl(real_paths.raw / "test.jsonl")
    assert set(tr["id"]).isdisjoint(va["id"])
    assert set(tr["id"]).isdisjoint(te["id"])
    assert set(va["id"]).isdisjoint(te["id"])
    report = json.loads((real_paths.reports / "validation" / "report.json").read_text("utf-8"))
    assert len(tr) + len(va) == report["splits"]["train"]["rows_out"]
    # Official test kept as is: same rows, same labels, same text.
    assert te.drop(columns="text_norm").equals(raw_test)
    assert va["intent"].nunique() == 75


def test_text_norm_present_and_masked(real_paths: Paths) -> None:
    if not (real_paths.processed / "train.jsonl").exists():
        pytest.skip("data/processed absent")
    tr = read_jsonl(real_paths.processed / "train.jsonl")
    assert (tr["text_norm"].str.len() > 0).all()
    assert not tr["text_norm"].str.contains(r"0[5-7][xX]{8}").any()
    assert tr["text_norm"].str.contains(TEL_TOKEN, regex=False).sum() > 300
