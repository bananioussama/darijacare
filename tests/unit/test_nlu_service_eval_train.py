"""Service, evaluation and training helpers, tested with a fake laya agent (no torch needed)."""

from __future__ import annotations

import json
import math
import sys
import types
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from darijacare.config import get_paths
from darijacare.nlu.evaluate import compare_published, evaluate_model
from darijacare.nlu.service import (
    CATEGORY_INSTRUCTIONS,
    INTENT_INSTRUCTIONS,
    LayaTelecomModel,
    build_questions,
)
from darijacare.nlu.train import RetrainConfig, build_rows, lr_lambda
from tests.conftest import TAXONOMY, make_row


class FakeAgent:
    """Answers like laya: category from keywords, first option otherwise."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def _answer(self, text: str, qid: str, q: dict[str, Any]) -> dict[str, Any]:
        if q["type"] == "noul":
            return {"noul": 0.9 if "!!" in text else 0.1}
        if q["type"] == "score":
            return {"choice": 2, "probabilities": {"0": 0.1, "1": 0.1, "2": 0.7, "3": 0.1}}
        options = list(q["criteria"])
        if qid == "category":
            choice = "out_of_scope" if "foot" in text else "prepaid_credit"
        elif qid == "intent":
            choice = "recharge_how" if "kifach" in text else options[0]
        else:
            choice = options[0]
        rest = (1 - 0.8) / max(1, len(options) - 1)
        return {
            "choice": choice,
            "probabilities": {o: 0.8 if o == choice else rest for o in options},
        }

    def predict(self, text: str, questions: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((text, tuple(questions)))
        return {"answers": {k: self._answer(text, k, q) for k, q in questions.items()}}

    def predict_batch(
        self, texts: list[str], questions: dict[str, Any], batch_size: int = 8
    ) -> list[dict[str, Any]]:
        return [self.predict(t, questions) for t in texts]


@pytest.fixture
def fake_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LayaTelecomModel:
    fake_laya = types.ModuleType("laya")
    fake_laya.load = lambda *a, **k: FakeAgent()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "laya", fake_laya)
    (tmp_path / "telecom_taxonomy.json").write_text(json.dumps(TAXONOMY), encoding="utf-8")
    return LayaTelecomModel(tmp_path, model_version="fake")


def test_build_questions_matches_predict_py() -> None:
    first, intent = build_questions(TAXONOMY)
    assert list(first) == ["category", "product", "urgency", "needs_human"]
    assert first["category"]["instructions"] == CATEGORY_INSTRUCTIONS
    assert list(first["category"]["criteria"]) == ["prepaid_credit", "out_of_scope"]
    # Single-intent categories (out_of_scope) get no intent question.
    assert list(intent) == ["prepaid_credit"]
    assert intent["prepaid_credit"]["instructions"] == INTENT_INSTRUCTIONS


def test_predict_two_passes(fake_model: LayaTelecomModel) -> None:
    r = fake_model.predict("kifach nchargi!!")
    assert (r.category, r.intent, r.urgency, r.needs_human) == (
        "prepaid_credit",
        "recharge_how",
        2,
        True,
    )
    assert r.intent_joint_confidence == pytest.approx(0.8 * 0.8)
    assert r.intent_top2[0].label == "recharge_how"
    assert r.script == "arabizi" and r.model_version == "fake"
    calls = fake_model.agent.calls  # type: ignore[attr-defined]
    assert calls[0][1] == ("category", "product", "urgency", "needs_human")
    assert calls[1][1] == ("intent",)


def test_single_intent_category_skips_pass_two(fake_model: LayaTelecomModel) -> None:
    r = fake_model.predict("match de foot")
    assert (r.category, r.intent, r.intent_confidence) == ("out_of_scope", "non_telecom", 1.0)
    assert len(fake_model.agent.calls) == 1  # type: ignore[attr-defined]


def test_batch_equals_single(fake_model: LayaTelecomModel) -> None:
    texts = ["kifach nchargi", "match de foot", "solde!!", "bghit recharge"]
    single = [fake_model.predict(t) for t in texts]
    batch = fake_model.predict_batch(texts, batch_size=2)
    for a, b in zip(single, batch, strict=True):
        a.latency_ms = b.latency_ms = 0.0
        assert a == b
    assert fake_model.predict_batch([]) == []


def test_intent_with_category(fake_model: LayaTelecomModel) -> None:
    got = fake_model.intent_with_category(["kifach", "x"], ["prepaid_credit", "out_of_scope"])
    assert got == ["recharge_how", "non_telecom"]


def test_missing_checkpoint() -> None:
    with pytest.raises(FileNotFoundError):
        LayaTelecomModel("does/not/exist")


def test_evaluate_model_end_to_end(fake_model: LayaTelecomModel, tmp_path: Path) -> None:
    paths = get_paths(tmp_path)
    rows = [
        make_row(i, t, intent=i_, script="arabizi")
        for i, (t, i_) in enumerate(
            [
                ("kifach nchargi", "recharge_how"),
                ("solde", "balance_check"),
                ("kifach solde", "balance_check"),
                ("match de foot", "non_telecom"),
            ]
        )
    ]
    df = pd.DataFrame(rows)
    paths.processed.mkdir(parents=True)
    df.to_json(paths.processed / "test.jsonl", orient="records", lines=True, force_ascii=False)
    published = {
        "intent_end_to_end": 75.0,
        "intent_given_category": 75.0,
        "by_script": {"arabizi": 75.0},
    }
    report = evaluate_model(
        fake_model,
        paths,
        "fake",
        "test",
        ["balance_check", "recharge_how", "non_telecom"],
        published,
    )
    assert report["overall"]["intent_end_to_end"] == 0.75
    assert report["overall"]["intent_with_gold_category"] == 0.75
    assert report["reproduced"] is True
    out = paths.reports / "nlu" / "fake" / "test"
    for name in (
        "predictions.jsonl",
        "metrics.json",
        "README.md",
        "neighbours.json",
        "confusion_intent.csv",
        "intent_gold_category.jsonl",
    ):
        assert (out / name).exists(), name
    # Second run reuses cached predictions.
    again = evaluate_model(
        fake_model,
        paths,
        "fake",
        "test",
        ["balance_check", "recharge_how", "non_telecom"],
        published,
    )
    assert again["overall"] == report["overall"]


def test_compare_published_flags_gaps() -> None:
    rows = compare_published(
        {"intent_end_to_end": 0.80, "category_acc": 0.9},
        {"intent_end_to_end": 84.6, "category_acc": 90.0},
        1.0,
    )
    by = {r["métrique"]: r for r in rows}
    assert by["Intention de bout en bout"]["ok"] is False
    assert by["Catégorie"]["ok"] is True


# --- training helpers ----------------------------------------------------------


def test_build_rows_asks_own_category_intent() -> None:
    df = pd.DataFrame(
        [
            make_row(0, "kifach nchargi", intent="recharge_how", urgency=2, needs_human=True),
            make_row(1, "foot", intent="non_telecom"),
        ]
    )
    rows = build_rows(df, TAXONOMY)
    assert rows[0]["expected"] == {
        "category": "prepaid_credit",
        "product": "unknown",
        "urgency": 2,
        "needs_human": True,
        "intent": "recharge_how",
    }
    assert "intent" in rows[0]["questions"]
    assert "intent" not in rows[1]["questions"]  # single-intent category
    assert rows[1]["state"] == "foot"


def test_lr_schedule_warmup_then_cosine() -> None:
    total, warmup = 100, 6
    assert lr_lambda(0, total, warmup, 0.0) == pytest.approx(1 / 6)
    assert lr_lambda(5, total, warmup, 0.0) == pytest.approx(1.0)
    assert lr_lambda(6, total, warmup, 0.0) == pytest.approx(1.0)
    mid = warmup + (total - warmup) // 2
    assert lr_lambda(mid, total, warmup, 0.0) == pytest.approx(0.5, abs=0.02)
    assert lr_lambda(total, total, warmup, 0.0) == pytest.approx(0.0, abs=1e-9)
    assert lr_lambda(total, total, warmup, 0.1) == pytest.approx(0.1)
    assert all(0 <= lr_lambda(s, total, warmup, 0.0) <= 1 for s in range(total))
    assert not math.isnan(lr_lambda(0, 1, 0, 0.0))


def test_retrain_config_from_yaml() -> None:
    import yaml

    from tests.conftest import REPO_ROOT

    cfg = yaml.safe_load((REPO_ROOT / "configs" / "train.yaml").read_text(encoding="utf-8"))
    rc = RetrainConfig.from_mapping(cfg["retrain"])
    assert (rc.micro_batch * rc.grad_accum, rc.encoder_lr, rc.head_lr) == (32, 3e-5, 1e-4)
    assert rc.label_smoothing == 0.05 and rc.warmup_frac == 0.06
    assert rc.shuffle_options == ("choice",) and rc.seeds == (42, 43, 44)
    assert rc.frozen_prefixes == ("encoder.embeddings.tok_embeddings.",)
