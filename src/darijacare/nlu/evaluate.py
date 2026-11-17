"""Evaluate an NLU model on a split and compare with the published numbers.

Outputs, in ``reports/nlu/<model_name>/<split>/``:

* ``predictions.jsonl``: one line per message with every probability (reused by
  calibration, so the model only runs once per split);
* ``metrics.json``: overall, by script, by category, bootstrap 95 % CIs,
  comparison with the model card (tolerance ``tolerance_points``);
* ``confusion_intent.csv`` and ``neighbours.json`` (top-3 confused intents,
  used by RAG retrieval in Phase 3);
* ``README.md``: a French summary.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from darijacare.config import Paths
from darijacare.io import read_jsonl, write_json, write_jsonl, write_text
from darijacare.nlu.metrics import (
    bootstrap_ci,
    confusion_frame,
    headline_metrics,
    intent_end_to_end,
    intent_given_category,
    metrics_by_group,
    top_confusions,
)
from darijacare.nlu.service import NLUResult, NLUService

log = logging.getLogger(__name__)

PUBLISHED_KEYS = {
    "intent_end_to_end": "Intention de bout en bout",
    "category_acc": "Catégorie",
    "intent_given_category": "Intention sachant la catégorie (catégorie prédite juste)",
    "intent_with_gold_category": "Intention avec la vraie catégorie (passe 2 forcée)",
    "product_acc": "Produit",
    "urgency_acc": "Urgence (niveau exact)",
    "needs_human_acc": "needs_human",
}


def result_row(r: NLUResult) -> dict[str, Any]:
    """Flatten an :class:`NLUResult` into a predictions-file row."""
    return {
        "category": r.category,
        "category_p": r.category_confidence,
        "category_top2": [[s.label, s.p] for s in r.category_top2],
        "intent": r.intent,
        "intent_p": r.intent_confidence,
        "intent_joint_p": r.intent_joint_confidence,
        "intent_top2": [[s.label, s.p] for s in r.intent_top2],
        "product": r.product,
        "product_p": r.product_confidence,
        "urgency": r.urgency,
        "urgency_p": r.urgency_confidence,
        "urgency_probs": r.urgency_probabilities,
        "needs_human": r.needs_human,
        "needs_human_p": r.needs_human_probability,
        "script_detected": r.script,
        "latency_ms": round(r.latency_ms, 2),
        "probs": r.probabilities,
    }


def run_predictions(
    service: NLUService,
    df: pd.DataFrame,
    text_col: str = "text",
    progress: Callable[[int, int], None] | None = None,
    chunk: int = 64,
    batch_size: int = 8,
) -> pd.DataFrame:
    """Predict every row of ``df`` (batched) and return a predictions frame aligned on ``df``."""
    texts: list[str] = df[text_col].tolist()
    rows: list[dict[str, Any]] = []
    for start in range(0, len(texts), chunk):
        results = service.predict_batch(texts[start : start + chunk], batch_size=batch_size)
        rows.extend(result_row(r) for r in results)
        if progress:
            progress(len(rows), len(texts))
    pred = pd.DataFrame(rows, index=df.index)
    pred.insert(0, "id", df["id"].to_numpy())
    return pred


def compare_published(
    metrics: dict[str, float], published: dict[str, float], tol_points: float
) -> list[dict[str, Any]]:
    """Measured vs published (percentages) with a pass flag per metric."""
    rows = []
    aliases = {"intent_with_gold_category": "intent_given_category"}
    for key, label in PUBLISHED_KEYS.items():
        ref_key = aliases.get(key, key)
        if ref_key not in published or key not in metrics:
            continue
        measured = round(100 * metrics[key], 1)
        gap = round(measured - published[ref_key], 1)
        rows.append(
            {
                "métrique": label,
                "mesuré (%)": measured,
                "publié (%)": published[ref_key],
                "écart (pts)": gap,
                "ok": abs(gap) <= tol_points,
            }
        )
    # The card gives one "intent given the right category" number; either definition may be
    # the one it used, so the pair counts as reproduced when at least one matches.
    defs = [
        r
        for r in rows
        if str(r["métrique"]).startswith(("Intention sachant", "Intention avec la vraie"))
    ]
    if len(defs) == 2 and any(r["ok"] for r in defs):
        for r in defs:
            r["ok"] = True
    for script, value in published.get("by_script", {}).items():  # type: ignore[union-attr]
        rows.append({"métrique": f"Intention — {script}", "publié (%)": value})
    return rows


def evaluate_predictions(
    gold: pd.DataFrame,
    pred: pd.DataFrame,
    intents: list[str],
    published: dict[str, Any] | None = None,
    tol_points: float = 1.0,
    n_bootstrap: int = 1000,
    seed: int = 42,
    extra_metrics: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compute every metric of the evaluation report."""
    overall = {**headline_metrics(gold, pred), **(extra_metrics or {})}
    by_script = metrics_by_group(gold, pred, "script")
    ci = {}
    for name, fn in {
        "intent_end_to_end": intent_end_to_end,
        "intent_given_category": intent_given_category,
    }.items():
        est, lo, hi = bootstrap_ci(gold, pred, fn, n_resamples=n_bootstrap, seed=seed)
        ci[name] = {"estimate": est, "low": lo, "high": hi}
    report: dict[str, Any] = {
        "n": len(gold),
        "overall": overall,
        "bootstrap_95ci": ci,
        "by_script": by_script,
        "by_category": metrics_by_group(gold, pred, "category"),
        "intent_by_script": {s: m["intent_end_to_end"] for s, m in by_script.items()},
    }
    if published:
        rows = compare_published(overall, published, tol_points)
        for row in rows:
            script = row["métrique"].removeprefix("Intention — ")
            if "mesuré (%)" not in row and script in by_script:
                measured = round(100 * by_script[script]["intent_end_to_end"], 1)
                gap = round(measured - row["publié (%)"], 1)
                row.update(
                    {"mesuré (%)": measured, "écart (pts)": gap, "ok": abs(gap) <= tol_points}
                )
        report["published_comparison"] = rows
        report["reproduced"] = all(r.get("ok", False) for r in rows)
    report["_confusion"] = confusion_frame(gold["intent"], pred["intent"], intents)
    return report


def _md_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    cols = list(rows[0].keys())
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        lines.append(
            "| "
            + " | ".join(
                ("✅" if r.get(c) else "❌") if isinstance(r.get(c), bool) else str(r.get(c, ""))
                for c in cols
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], out_dir: Path, title: str) -> None:
    """Write metrics.json, confusion matrix, neighbours and a Markdown summary."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cm: pd.DataFrame = report.pop("_confusion")
    cm.to_csv(out_dir / "confusion_intent.csv", encoding="utf-8", lineterminator="\n")
    write_json(top_confusions(cm, 3), out_dir / "neighbours.json")
    write_json(report, out_dir / "metrics.json")
    o = report["overall"]
    ci = report["bootstrap_95ci"]["intent_end_to_end"]
    lines = [
        f"# {title}",
        "",
        f"Messages : {report['n']} — résultats mesurés sur des données **synthétiques**.",
        "",
        f"**Intention de bout en bout : {100 * o['intent_end_to_end']:.1f} %** "
        f"(IC 95 % bootstrap : {100 * ci['low']:.1f}–{100 * ci['high']:.1f})",
        "",
    ]
    if "published_comparison" in report:
        lines += [
            "## Comparaison avec les chiffres publiés",
            "",
            _md_table(report["published_comparison"]),
            "",
        ]
    lines += [
        "## Toutes les tâches",
        "",
        _md_table(
            [
                {
                    "tâche": t,
                    "exactitude (%)": round(100 * o[f"{t}_acc"], 1),
                    "F1 macro (%)": round(100 * o[f"{t}_f1_macro"], 1),
                }
                for t in ("category", "intent", "product", "urgency", "needs_human")
            ]
        ),
        f"QWK urgence : {o['urgency_qwk']:.3f}",
        "",
        "## Par script",
        "",
        _md_table(
            [
                {
                    "script": s,
                    "n": int(m["n"]),
                    "intention bout en bout (%)": round(100 * m["intent_end_to_end"], 1),
                    "catégorie (%)": round(100 * m["category_acc"], 1),
                    "needs_human (%)": round(100 * m["needs_human_acc"], 1),
                }
                for s, m in report["by_script"].items()
            ]
        ),
        "## Par catégorie",
        "",
        _md_table(
            [
                {
                    "catégorie": c,
                    "n": int(m["n"]),
                    "intention bout en bout (%)": round(100 * m["intent_end_to_end"], 1),
                }
                for c, m in sorted(report["by_category"].items())
            ]
        ),
    ]
    write_text("\n".join(lines) + "\n", out_dir / "README.md")


def evaluate_model(
    service: NLUService,
    paths: Paths,
    model_name: str,
    split: str,
    intents: list[str],
    published: dict[str, Any] | None,
    tol_points: float = 1.0,
) -> dict[str, Any]:
    """Run ``service`` on ``split`` (or reuse cached predictions) and write the report."""
    gold = read_jsonl(paths.processed / f"{split}.jsonl")
    out_dir = paths.reports / "nlu" / model_name / split
    pred_path = out_dir / "predictions.jsonl"
    if pred_path.exists():
        pred = read_jsonl(pred_path)
        if list(pred["id"]) != list(gold["id"]):
            raise ValueError(f"{pred_path} ne correspond pas au split {split}")
    else:
        pred = run_predictions(
            service,
            gold,
            progress=lambda i, n: log.info("[%s/%s] %d/%d", model_name, split, i, n),
        )
        write_jsonl(pred, pred_path)
    oracle_path = out_dir / "intent_gold_category.jsonl"
    if hasattr(service, "intent_with_category") and not oracle_path.exists():
        oracle = service.intent_with_category(gold["text"].tolist(), gold["category"].tolist())
        write_jsonl(pd.DataFrame({"id": gold["id"], "intent": oracle}), oracle_path)
    extra: dict[str, float] = {}
    if oracle_path.exists():
        oracle_df = read_jsonl(oracle_path)
        extra["intent_with_gold_category"] = float(
            (oracle_df["intent"].to_numpy() == gold["intent"].to_numpy()).mean()
        )
    report = evaluate_predictions(gold, pred, intents, published, tol_points, extra_metrics=extra)
    write_report(report, out_dir, f"Évaluation — {model_name} — {split}")
    return report
