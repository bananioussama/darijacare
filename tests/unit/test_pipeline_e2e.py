"""End-to-end test: the whole data pipeline through the CLI on a tiny fictitious dataset."""

from __future__ import annotations

import copy
import hashlib
import json
import random
from pathlib import Path
from typing import Any

import pytest
import yaml

from darijacare.data import cli
from darijacare.io import read_jsonl
from tests.conftest import REPO_ROOT, TAXONOMY, make_row

SYLLABLES = ["ba", "ki", "lo", "mu", "sa", "ti", "ra", "ne", "do", "fu", "ch", "gh", "kh", "zi"]


def _word(rng: random.Random) -> str:
    return "".join(rng.choice(SYLLABLES) for _ in range(rng.randint(2, 4)))


def _rows(prefix: str, n: int, rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    for i in range(n):
        intent = ["balance_check", "recharge_how"][i % 2]
        text = " ".join(_word(rng) for _ in range(6))  # random Arabizi-like text
        row = make_row(i, text, intent=intent, urgency=i % 4, needs_human=i % 5 == 0)
        row["id"] = f"{prefix}-{i:04d}"
        rows.append(row)
    return rows


def _write_jsonl(rows: list[dict[str, Any]], path: Path) -> bytes:
    data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")
    path.write_bytes(data)
    return data


@pytest.fixture
def mini_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    rng = random.Random(0)
    src = tmp_path / "source"
    root = tmp_path / "repo"
    src.mkdir()
    (root / "configs").mkdir(parents=True)

    contents = {
        "train.jsonl": _write_jsonl(_rows("train", 120, rng), src / "train.jsonl"),
        "test.jsonl": _write_jsonl(_rows("test", 20, rng), src / "test.jsonl"),
        "telecom_taxonomy.json": json.dumps(TAXONOMY).encode("utf-8"),
        "DATASET_CARD.md": b"# fiche\n",
    }
    (src / "telecom_taxonomy.json").write_bytes(contents["telecom_taxonomy.json"])
    (src / "README.md").write_bytes(contents["DATASET_CARD.md"])

    real = yaml.safe_load((REPO_ROOT / "configs" / "data.yaml").read_text(encoding="utf-8"))
    cfg = copy.deepcopy(real)
    cfg["source"]["mode"] = "local"
    cfg["source"]["local_dir"] = str(src)
    for name, spec in cfg["source"]["files"].items():
        spec["sha256"] = hashlib.sha256(contents[name]).hexdigest()
    cfg["validation"]["expected_rows"] = {"train": 120, "test": 20}
    cfg["validation"]["expected_taxonomy"] = {"categories": 2, "intents": 3}
    cfg["split"]["min_stratum_size"] = 5
    cfg["split"]["max_distribution_gap_points"] = 25.0
    (root / "configs" / "data.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    (root / "pyproject.toml").write_text("", encoding="utf-8")
    (root / "src" / "darijacare").mkdir(parents=True)

    monkeypatch.setenv("DARIJACARE_ROOT", str(root))
    monkeypatch.delenv("DARIJACARE_SOURCE_DIR", raising=False)
    return root


def test_full_pipeline_via_cli(mini_repo: Path) -> None:
    assert cli.main(["all"]) == 0

    processed = mini_repo / "data" / "processed"
    train = read_jsonl(processed / "train.jsonl")
    val = read_jsonl(processed / "val.jsonl")
    test = read_jsonl(processed / "test.jsonl")
    assert len(train) + len(val) == 120 and len(test) == 20
    assert set(train["id"]).isdisjoint(val["id"])
    assert "text_norm" in train.columns

    reports = mini_repo / "reports"
    for rel in [
        "validation/report.json",
        "normalize/report.json",
        "split/report.json",
        "eda/README.md",
        "eda/eda.json",
        "eda/figures/cooccurrence_intent_category.png",
    ]:
        assert (reports / rel).exists(), rel
    md = (reports / "eda" / "README.md").read_text(encoding="utf-8")
    assert "Tableau 5" in md and "⚠️" in md  # mini data differs from Table 5: flagged


def test_pipeline_is_byte_reproducible(mini_repo: Path) -> None:
    assert cli.main(["all"]) == 0
    files = sorted(p for p in (mini_repo / "data").rglob("*") if p.is_file())
    files += sorted(p for p in (mini_repo / "reports").rglob("*") if p.is_file())
    first = {p: p.read_bytes() for p in files}
    assert cli.main(["all"]) == 0
    assert {p: p.read_bytes() for p in files} == first


def test_cli_returns_error_code_on_failure(mini_repo: Path) -> None:
    cfg_path = mini_repo / "configs" / "data.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    cfg["source"]["files"]["train.jsonl"]["sha256"] = "0" * 64
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    assert cli.main(["ingest"]) == 1
