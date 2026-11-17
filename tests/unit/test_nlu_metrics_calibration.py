"""Unit tests for NLU metrics and calibration (no model needed)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from darijacare.nlu.calibrate import (
    apply_temperature,
    apply_temperature_binary,
    ece,
    fit_calibrator,
    fit_temperature,
    fit_temperature_binary,
    identity_calibrator,
    intent_threshold,
    needs_human_threshold,
)
from darijacare.nlu.metrics import (
    bootstrap_ci,
    confusion_frame,
    headline_metrics,
    intent_end_to_end,
    intent_given_category,
    top_confusions,
)


def _gold() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "category": ["a", "a", "b", "b"],
            "intent": ["a1", "a2", "b1", "b1"],
            "product": ["p", "p", "q", "q"],
            "urgency": [0, 1, 2, 3],
            "needs_human": [False, True, False, True],
            "script": ["arabic", "arabizi", "arabic", "mixed"],
        }
    )


def test_end_to_end_and_given_category() -> None:
    gold = _gold()
    pred = gold.copy()
    pred.loc[1, "intent"] = "a1"  # right category, wrong intent
    pred.loc[2, ["category", "intent"]] = ["a", "b1"]  # wrong category, "right" intent string
    assert intent_end_to_end(gold, pred) == 0.5
    assert intent_given_category(gold, pred) == pytest.approx(2 / 3)


def test_headline_metrics_perfect() -> None:
    gold = _gold()
    m = headline_metrics(gold, gold.copy())
    assert m["intent_end_to_end"] == 1.0 and m["urgency_qwk"] == 1.0
    assert all(m[f"{t}_acc"] == 1.0 for t in ("category", "intent", "product", "needs_human"))


def test_bootstrap_ci_contains_estimate() -> None:
    gold = pd.concat([_gold()] * 25, ignore_index=True)
    pred = gold.copy()
    pred.loc[::4, "intent"] = "zz"
    est, lo, hi = bootstrap_ci(gold, pred, intent_end_to_end, n_resamples=200)
    assert lo <= est <= hi and est == 0.75


def test_confusion_and_neighbours() -> None:
    gold = pd.Series(["x", "x", "x", "y", "z"])
    pred = pd.Series(["x", "y", "y", "z", "z"])
    cm = confusion_frame(gold, pred, ["x", "y", "z"])
    assert cm.loc["x", "y"] == 2
    nb = top_confusions(cm, 3)
    assert nb["x"] == [{"label": "y", "count": 2}]
    assert nb["z"] == []


# --- calibration -------------------------------------------------------------


def test_ece_perfect_and_overconfident() -> None:
    assert ece(np.array([1.0, 1.0]), np.array([1, 1])) == 0.0
    assert ece(np.array([0.9] * 10), np.array([1] * 5 + [0] * 5)) == pytest.approx(0.4)


def test_temperature_identity_and_sharpening() -> None:
    p = np.array([[0.7, 0.2, 0.1]])
    assert np.allclose(apply_temperature(p, 1.0), p)
    assert apply_temperature(p, 0.5)[0, 0] > 0.7
    assert apply_temperature(p, 2.0)[0, 0] < 0.7
    assert apply_temperature_binary(np.array([0.8]), 1.0)[0] == pytest.approx(0.8)


def test_fit_temperature_recovers_overconfidence() -> None:
    rng = np.random.default_rng(0)
    n, k = 4000, 5
    true_logits = rng.normal(size=(n, k)) * 2
    true_p = np.exp(true_logits) / np.exp(true_logits).sum(1, keepdims=True)
    y = np.array([rng.choice(k, p=row) for row in true_p])
    overconfident = apply_temperature(true_p, 0.5)  # model sharper than reality
    t = fit_temperature(overconfident, y)
    assert t == pytest.approx(2.0, rel=0.15)


def test_fit_temperature_binary() -> None:
    rng = np.random.default_rng(1)
    p_true = rng.uniform(0.05, 0.95, 5000)
    y = rng.uniform(size=5000) < p_true
    t = fit_temperature_binary(apply_temperature_binary(p_true, 0.5), y)
    assert t == pytest.approx(2.0, rel=0.15)


def test_needs_human_threshold_meets_recall() -> None:
    p = np.array([0.95, 0.9, 0.8, 0.6, 0.4, 0.3, 0.2, 0.1])
    y = np.array([1, 1, 0, 1, 0, 1, 0, 0], dtype=float)
    res = needs_human_threshold(p, y, min_recall=0.75)
    assert res["threshold"] == 0.6 and res["recall"] == 0.75
    assert res["precision"] == pytest.approx(0.75)


def test_intent_threshold() -> None:
    joint = np.array([0.99, 0.95, 0.9, 0.6, 0.5])
    correct = np.array([1, 1, 1, 0, 1], dtype=float)
    res = intent_threshold(joint, correct, target_accuracy=0.95)
    assert res["threshold"] == 0.9 and res["coverage"] == 0.6
    assert intent_threshold(joint, np.zeros(5), 0.9)["coverage"] == 0.0


def _pred_frame(gold: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, g in gold.iterrows():
        other = "b" if g["category"] == "a" else "a"
        intents = ["a1", "a2"] if g["category"] == "a" else ["b1", "b2"]
        rows.append(
            {
                "probs": {
                    "category": {g["category"]: 0.8, other: 0.2},
                    "intent": {intents[0]: 0.7, intents[1]: 0.3},
                    "product": {g["product"]: 0.9, "unknown": 0.1},
                },
                "urgency_probs": {"0": 0.4, "1": 0.3, "2": 0.2, "3": 0.1},
                "needs_human_p": 0.7 if g["needs_human"] else 0.2,
            }
        )
    return pd.DataFrame(rows)


def test_fit_and_apply_calibrator_shapes() -> None:
    gold = pd.concat([_gold()] * 10, ignore_index=True)
    pred = _pred_frame(gold)
    cal = fit_calibrator(gold, pred, per_script=True)
    assert set(cal.temperatures) == {"category", "intent", "product", "urgency", "needs_human"}
    assert set(cal.by_script) == {"arabic", "arabizi", "mixed"}
    out = cal.calibrated(gold, pred, use_script=True)
    for task in ("category", "intent", "intent_end_to_end", "product", "urgency", "needs_human"):
        conf, correct = out[task]
        assert conf.shape == correct.shape == (len(gold),)
        assert ((conf >= 0) & (conf <= 1)).all()
    base = identity_calibrator().calibrated(gold, pred, use_script=False)
    assert base["category"][0][0] == pytest.approx(0.8)
