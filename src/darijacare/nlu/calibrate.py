"""Confidence calibration and decision thresholds (cahier des charges, F-NLU calibration).

Works on the ``predictions.jsonl`` files written by :mod:`darijacare.nlu.evaluate`
(full probability distributions), so the model does not need to run again.

* **Temperature scaling** per task (category, intent, product, urgency,
  needs_human), optionally per script: ``p_T = softmax(log p / T)``; for the
  binary needs_human, the logit ``log(p / (1 - p))`` is divided by ``T``.
  ``T`` minimises the negative log-likelihood on the *fit* split (validation).
* **ECE** (15 equal-width bins) before/after, with reliability diagrams.
* **needs_human threshold**: the largest threshold whose recall is at least
  ``min_recall`` on the fit split (maximises precision under the recall
  constraint); the precision target is reported, not forced.
* **Intent confidence threshold** (clarification): the smallest threshold on
  the calibrated end-to-end confidence such that messages above it reach
  ``target_accuracy``; coverage is reported.

The intent pass gives probabilities *inside the predicted category*. When the
category is wrong, the gold intent is not among the options; such rows count
as errors for ECE and thresholds and are left out of the intent temperature fit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from darijacare.io import read_jsonl, write_json

log = logging.getLogger(__name__)

EPS = 1e-9
T_BOUNDS = (0.05, 20.0)


# --- Basic tools --------------------------------------------------------------


def ece(confidence: np.ndarray, correct: np.ndarray, n_bins: int = 15) -> float:
    """Expected calibration error with equal-width bins."""
    confidence = np.asarray(confidence, dtype=float)
    correct = np.asarray(correct, dtype=float)
    if len(confidence) == 0:
        return 0.0
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(confidence, bins[1:-1], right=True), 0, n_bins - 1)
    total = 0.0
    for b in range(n_bins):
        mask = idx == b
        if mask.any():
            total += mask.mean() * abs(correct[mask].mean() - confidence[mask].mean())
    return float(total)


def apply_temperature(probs: np.ndarray, t: float) -> np.ndarray:
    """Rescale a (n, k) matrix of probabilities with temperature ``t``."""
    logits = np.log(np.clip(probs, EPS, 1.0)) / t
    logits -= logits.max(axis=1, keepdims=True)
    e = np.exp(logits)
    out: np.ndarray = e / e.sum(axis=1, keepdims=True)
    return out


def apply_temperature_binary(p: np.ndarray, t: float) -> np.ndarray:
    """Rescale positive-class probabilities of a binary task with temperature ``t``."""
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    logit = np.log(p / (1 - p)) / t
    out: np.ndarray = 1 / (1 + np.exp(-logit))
    return out


def fit_temperature(probs: np.ndarray, target: np.ndarray) -> float:
    """Temperature minimising the NLL of ``target`` (column indices) under ``probs``."""
    if len(target) == 0:
        return 1.0
    rows = np.arange(len(target))

    def nll(t: float) -> float:
        return float(-np.log(apply_temperature(probs, t)[rows, target] + EPS).mean())

    res = minimize_scalar(nll, bounds=T_BOUNDS, method="bounded")
    return float(res.x)


def fit_temperature_binary(p: np.ndarray, y: np.ndarray) -> float:
    """Temperature minimising the binary NLL."""
    if len(y) == 0:
        return 1.0
    y = np.asarray(y, dtype=float)

    def nll(t: float) -> float:
        q = apply_temperature_binary(p, t)
        return float(-(y * np.log(q + EPS) + (1 - y) * np.log(1 - q + EPS)).mean())

    res = minimize_scalar(nll, bounds=T_BOUNDS, method="bounded")
    return float(res.x)


# --- Building task matrices from prediction files -----------------------------


@dataclass
class TaskData:
    """Probability matrix, gold column indices (-1 = gold not among options), labels."""

    probs: np.ndarray
    target: np.ndarray
    labels: list[str]


def _matrix(dists: list[dict[str, float]], gold: list[str]) -> TaskData:
    labels = sorted({k for d in dists for k in d})
    col = {lbl: i for i, lbl in enumerate(labels)}
    probs = np.zeros((len(dists), len(labels)))
    for i, d in enumerate(dists):
        for k, v in d.items():
            probs[i, col[k]] = v
    target = np.array([col.get(g, -1) for g in gold])
    return TaskData(probs, target, labels)


def task_data(gold: pd.DataFrame, pred: pd.DataFrame, task: str) -> TaskData:
    """Probability matrix for a multi-class task (category, product, urgency)."""
    source = pred["urgency_probs"] if task == "urgency" else (p[task] for p in pred["probs"])
    dists: list[dict[str, float]] = list(source)
    return _matrix(dists, gold[task].astype(str).tolist())


def intent_rows(gold: pd.DataFrame, pred: pd.DataFrame) -> tuple[list[np.ndarray], np.ndarray]:
    """Per-row intent probability vectors (variable size) and the gold position (-1 if absent)."""
    vecs, target = [], []
    for g, p in zip(gold["intent"], pred["probs"], strict=True):
        labels = sorted(p["intent"])
        vecs.append(np.array([p["intent"][lbl] for lbl in labels]))
        target.append(labels.index(g) if g in labels else -1)
    return vecs, np.array(target)


def fit_intent_temperature(vecs: list[np.ndarray], target: np.ndarray) -> float:
    """NLL temperature for the intent pass, on rows where the gold intent is an option."""
    keep = [i for i, t in enumerate(target) if t >= 0 and len(vecs[i]) > 1]
    if not keep:
        return 1.0

    def nll(t: float) -> float:
        tot = 0.0
        for i in keep:
            q = apply_temperature(vecs[i][None, :], t)[0]
            tot -= np.log(q[target[i]] + EPS)
        return tot / len(keep)

    return float(minimize_scalar(nll, bounds=T_BOUNDS, method="bounded").x)


# --- Calibrator ---------------------------------------------------------------


@dataclass
class Calibrator:
    """Fitted temperatures (global and per script) applied to prediction files."""

    temperatures: dict[str, float]
    by_script: dict[str, dict[str, float]]

    def t(self, task: str, script: str | None) -> float:
        if script is not None and script in self.by_script:
            return self.by_script[script].get(task, self.temperatures[task])
        return self.temperatures[task]

    def calibrated(
        self, gold: pd.DataFrame, pred: pd.DataFrame, use_script: bool
    ) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """Return ``{task: (confidence, correct)}`` after calibration."""
        scripts = list(gold["script"]) if use_script else [None] * len(gold)
        out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for task in ("category", "product", "urgency"):
            td = task_data(gold, pred, task)
            conf, correct = np.zeros(len(gold)), np.zeros(len(gold))
            for i, s in enumerate(scripts):
                q = apply_temperature(td.probs[i : i + 1], self.t(task, s))[0]
                j = int(q.argmax())
                conf[i], correct[i] = q[j], float(j == td.target[i])
            out[task] = (conf, correct)
        vecs, target = intent_rows(gold, pred)
        cat_conf, cat_ok = out["category"]
        conf, correct, joint = np.zeros(len(gold)), np.zeros(len(gold)), np.zeros(len(gold))
        for i, s in enumerate(scripts):
            q = apply_temperature(vecs[i][None, :], self.t("intent", s))[0]
            j = int(q.argmax())
            conf[i], correct[i] = q[j], float(j == target[i] and cat_ok[i] == 1.0)
            joint[i] = q[j] * cat_conf[i]
        out["intent"] = (conf, correct)
        out["intent_end_to_end"] = (joint, correct)
        p = np.array(
            [
                apply_temperature_binary(np.array([v]), self.t("needs_human", s))[0]
                for v, s in zip(pred["needs_human_p"], scripts, strict=True)
            ]
        )
        y = gold["needs_human"].astype(bool).to_numpy()
        out["needs_human"] = (np.where(p >= 0.5, p, 1 - p), ((p >= 0.5) == y).astype(float))
        out["_needs_human_p"] = (p, y.astype(float))
        return out


def identity_calibrator() -> Calibrator:
    """Temperature 1 everywhere (= probabilities as returned by the model)."""
    return Calibrator(
        {t: 1.0 for t in ("category", "intent", "product", "urgency", "needs_human")}, {}
    )


def fit_calibrator(gold: pd.DataFrame, pred: pd.DataFrame, per_script: bool) -> Calibrator:
    """Fit one temperature per task (and per script when ``per_script``)."""

    def fit(g: pd.DataFrame, p: pd.DataFrame) -> dict[str, float]:
        temps = {}
        for task in ("category", "product", "urgency"):
            td = task_data(g, p, task)
            ok = td.target >= 0
            temps[task] = fit_temperature(td.probs[ok], td.target[ok])
        vecs, target = intent_rows(g, p)
        temps["intent"] = fit_intent_temperature(vecs, target)
        temps["needs_human"] = fit_temperature_binary(
            p["needs_human_p"].to_numpy(), g["needs_human"].astype(float).to_numpy()
        )
        return temps

    glob = fit(gold, pred)
    by_script: dict[str, dict[str, float]] = {}
    if per_script:
        for s, idx in gold.groupby("script").groups.items():
            by_script[str(s)] = fit(gold.loc[idx], pred.loc[idx])
    return Calibrator(glob, by_script)


# --- Thresholds -------------------------------------------------------------


def needs_human_threshold(p: np.ndarray, y: np.ndarray, min_recall: float) -> dict[str, float]:
    """Largest threshold reaching ``min_recall`` on the positive class."""
    y = y.astype(bool)
    best = {"threshold": 0.0, "precision": float(y.mean()), "recall": 1.0}
    for t in np.unique(np.round(p, 4))[::-1]:
        pos = p >= t
        recall = float((pos & y).sum() / max(y.sum(), 1))
        if recall >= min_recall:
            precision = float((pos & y).sum() / max(pos.sum(), 1))
            best = {"threshold": float(t), "precision": precision, "recall": recall}
            break
    return best


def intent_threshold(
    joint: np.ndarray, correct: np.ndarray, target_accuracy: float
) -> dict[str, float]:
    """Smallest confidence threshold whose answered messages reach ``target_accuracy``."""
    order = np.argsort(-joint)
    acc = np.cumsum(correct[order]) / np.arange(1, len(order) + 1)
    ok = np.nonzero(acc >= target_accuracy)[0]
    if len(ok) == 0:
        return {"threshold": 1.0, "coverage": 0.0, "accuracy_answered": float("nan")}
    k = int(ok.max())
    return {
        "threshold": float(joint[order][k]),
        "coverage": float((k + 1) / len(order)),
        "accuracy_answered": float(acc[k]),
    }


def reliability_figure(
    curves: dict[str, tuple[np.ndarray, np.ndarray]], title: str, path: Path, n_bins: int = 15
) -> None:
    """Reliability diagram (accuracy vs confidence) for before/after curves."""
    fig, ax = plt.subplots(figsize=(4.2, 4.2))
    ax.plot([0, 1], [0, 1], color="#B9B2C6", linewidth=1, linestyle="--")
    colors = {"avant": "#B57BFF", "après": "#4B1486"}
    bins = np.linspace(0, 1, n_bins + 1)
    for name, (conf, correct) in curves.items():
        idx = np.clip(np.digitize(conf, bins[1:-1], right=True), 0, n_bins - 1)
        xs, ys = [], []
        for b in range(n_bins):
            m = idx == b
            if m.sum() >= 5:
                xs.append(conf[m].mean())
                ys.append(correct[m].mean())
        ax.plot(
            xs,
            ys,
            marker="o",
            markersize=4,
            linewidth=2,
            color=colors.get(name, "#7B2CBF"),
            label=f"{name} (ECE {ece(conf, correct):.3f})",
        )
    ax.set_xlabel("confiance")
    ax.set_ylabel("exactitude")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_title(title, loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)


def run_calibration(
    model_dir: Path, cfg: dict[str, Any], fit_split: str = "val", report_split: str = "test"
) -> dict[str, Any]:
    """Fit on ``fit_split`` predictions; report ECE on both splits; choose thresholds.

    ``model_dir`` is ``reports/nlu/<model_name>`` (contains ``<split>/predictions.jsonl``).
    Gold labels are read from ``data/processed`` through the path in ``cfg['processed_dir']``.
    """
    processed = Path(cfg["processed_dir"])
    data = {}
    for split in (fit_split, report_split):
        pred_path = model_dir / split / "predictions.jsonl"
        if pred_path.exists():
            data[split] = (read_jsonl(processed / f"{split}.jsonl"), read_jsonl(pred_path))
    if fit_split not in data:
        raise FileNotFoundError(f"Prédictions {fit_split} absentes dans {model_dir}")

    gold, pred = data[fit_split]
    fit_filter: dict[str, list[Any]] = cfg.get("fit_filter") or {}
    if fit_filter:
        # e.g. {"round": [4, 6]}: rows a model never saw in training (clean calibration subset).
        keep = pd.Series(True, index=gold.index)
        for col, values in fit_filter.items():
            keep &= gold[col].isin(values)
        gold = gold[keep].reset_index(drop=True)
        pred = pred[keep.to_numpy()].reset_index(drop=True)
        data[fit_split] = (gold, pred)
    per_script = bool(cfg.get("per_script", True))
    cal = fit_calibrator(gold, pred, per_script)
    ident = identity_calibrator()
    report: dict[str, Any] = {
        "fit_split": fit_split,
        "fit_filter": fit_filter,
        "fit_rows": len(gold),
        "temperatures": cal.temperatures,
        "temperatures_by_script": cal.by_script,
        "ece": {},
    }
    for split, (g, p) in data.items():
        before = ident.calibrated(g, p, use_script=False)
        after = cal.calibrated(g, p, use_script=per_script)
        report["ece"][split] = {
            task: {"avant": ece(*before[task]), "après": ece(*after[task])}
            for task in (
                "category",
                "intent",
                "intent_end_to_end",
                "product",
                "urgency",
                "needs_human",
            )
        }
        for task in ("intent_end_to_end", "needs_human"):
            reliability_figure(
                {"avant": before[task], "après": after[task]},
                f"{task} — {split}",
                model_dir / "calibration" / f"reliability_{task}_{split}.png",
            )

    after_fit = cal.calibrated(gold, pred, use_script=per_script)
    p_h, y_h = after_fit["_needs_human_p"]
    nh = needs_human_threshold(p_h, y_h, cfg["needs_human_min_recall"])
    nh["precision_target"] = cfg["needs_human_min_precision"]
    nh["precision_target_met"] = nh["precision"] >= cfg["needs_human_min_precision"]
    joint, correct = after_fit["intent_end_to_end"]
    it = intent_threshold(joint, correct, cfg["intent_target_accuracy"])
    report["thresholds"] = {"needs_human": nh, "intent_confidence": it}

    if report_split in data:
        g, p = data[report_split]
        after = cal.calibrated(g, p, use_script=per_script)
        ph, yh = after["_needs_human_p"]
        pos = ph >= nh["threshold"]
        yb = yh.astype(bool)
        j, c = after["intent_end_to_end"]
        answered = j >= it["threshold"]
        report["thresholds_on_" + report_split] = {
            "needs_human_recall": float((pos & yb).sum() / max(yb.sum(), 1)),
            "needs_human_precision": float((pos & yb).sum() / max(pos.sum(), 1)),
            "intent_coverage": float(answered.mean()),
            "intent_accuracy_answered": float(c[answered].mean()) if answered.any() else None,
        }
    write_json(report, model_dir / "calibration" / "calibration.json")
    return report
