"""Evaluation metrics shared by every NLU model (baseline, published model, retrained model).

All functions take a DataFrame of gold labels and a DataFrame of predictions
aligned on the same index, with the columns ``category``, ``intent``,
``product``, ``urgency`` and ``needs_human``.

Definitions follow the model card:

* **intent end to end**: category *and* intent both right (75 classes);
* **intent given category**: intent accuracy on rows whose category is right.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, cohen_kappa_score, confusion_matrix, f1_score

TASKS: tuple[str, ...] = ("category", "intent", "product", "urgency", "needs_human")


def _acc(y: pd.Series, p: pd.Series) -> float:
    return float(accuracy_score(y.astype(str), p.astype(str)))


def _f1(y: pd.Series, p: pd.Series) -> float:
    return float(f1_score(y.astype(str), p.astype(str), average="macro", zero_division=0))


def intent_end_to_end(gold: pd.DataFrame, pred: pd.DataFrame) -> float:
    """Share of rows where both category and intent are right."""
    ok = (gold["category"] == pred["category"]) & (gold["intent"] == pred["intent"])
    return float(ok.mean())


def intent_given_category(gold: pd.DataFrame, pred: pd.DataFrame) -> float:
    """Intent accuracy restricted to rows whose category is right."""
    mask = gold["category"] == pred["category"]
    return (
        float((gold.loc[mask, "intent"] == pred.loc[mask, "intent"]).mean()) if mask.any() else 0.0
    )


def urgency_qwk(gold: pd.DataFrame, pred: pd.DataFrame) -> float:
    """Quadratic weighted kappa for the ordinal urgency level."""
    return float(
        cohen_kappa_score(
            gold["urgency"].astype(int), pred["urgency"].astype(int), weights="quadratic"
        )
    )


def headline_metrics(gold: pd.DataFrame, pred: pd.DataFrame) -> dict[str, float]:
    """Accuracy and macro-F1 for every task, plus the model-card metrics."""
    out: dict[str, float] = {
        "intent_end_to_end": intent_end_to_end(gold, pred),
        "intent_given_category": intent_given_category(gold, pred),
        "urgency_qwk": urgency_qwk(gold, pred),
    }
    for task in TASKS:
        out[f"{task}_acc"] = _acc(gold[task], pred[task])
        out[f"{task}_f1_macro"] = _f1(gold[task], pred[task])
    return out


def metrics_by_group(
    gold: pd.DataFrame, pred: pd.DataFrame, group: str
) -> dict[str, dict[str, float]]:
    """:func:`headline_metrics` for each value of ``gold[group]`` (e.g. script, category)."""
    result: dict[str, dict[str, float]] = {}
    for value, idx in gold.groupby(group).groups.items():
        g, p = gold.loc[idx], pred.loc[idx]
        m = headline_metrics(g, p)
        m["n"] = float(len(idx))
        result[str(value)] = m
    return result


def bootstrap_ci(
    gold: pd.DataFrame,
    pred: pd.DataFrame,
    metric: Callable[[pd.DataFrame, pd.DataFrame], float],
    *,
    n_resamples: int = 1000,
    alpha: float = 0.05,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Point estimate and percentile bootstrap confidence interval of ``metric``."""
    rng = np.random.default_rng(seed)
    n = len(gold)
    g = gold.reset_index(drop=True)
    p = pred.reset_index(drop=True)
    stats = np.empty(n_resamples)
    for i in range(n_resamples):
        idx = rng.integers(0, n, n)
        stats[i] = metric(g.iloc[idx].reset_index(drop=True), p.iloc[idx].reset_index(drop=True))
    lo, hi = np.quantile(stats, [alpha / 2, 1 - alpha / 2])
    return metric(g, p), float(lo), float(hi)


def confusion_frame(gold: pd.Series, pred: pd.Series, labels: Sequence[str]) -> pd.DataFrame:
    """Confusion matrix as a labelled DataFrame (rows = gold, columns = predicted)."""
    cm = confusion_matrix(gold.astype(str), pred.astype(str), labels=list(labels))
    return pd.DataFrame(cm, index=list(labels), columns=list(labels))


def top_confusions(cm: pd.DataFrame, k: int = 3) -> dict[str, list[dict[str, Any]]]:
    """For each gold label, its ``k`` most frequent wrong predictions (neighbours for RAG)."""
    out: dict[str, list[dict[str, Any]]] = {}
    for label in cm.index:
        row = cm.loc[label].drop(label)
        row = row[row > 0].sort_values(ascending=False, kind="stable").head(k)
        out[str(label)] = [{"label": str(c), "count": int(n)} for c, n in row.items()]
    return out
