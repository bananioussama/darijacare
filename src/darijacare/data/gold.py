"""Gold set tooling (F-DAT-06, cahier des charges §22.3 and Tableau 38).

The gold set holds at least 300 messages **written by the team's Darija speakers**,
annotated with the taxonomy, never used for training, opened only for the final
evaluation. A sample is annotated twice (Cohen's kappa ≥ 0.70, target to validate).
This module provides the tooling only: the project ships no gold messages, because
they must be written by people (no fabricated data). Format and annotation guide:
``docs/gold.md``.

Files (``data/gold/``, versioned by DVC, never by git):

* ``gold.jsonl``: ``id``, ``text``, ``script`` (arabic | arabizi | mixed), ``category``,
  ``intent``, ``product``, ``urgency`` (0-3), ``needs_human``, ``cas_limite`` (bool),
  ``annotateur``;
* ``double.jsonl``: second annotation of a sample: ``id``, the five labels, ``annotateur``.

Commands::

    python -m darijacare.data.gold validate
    python -m darijacare.data.gold evaluate --model v5 [--device cuda]   # final, once
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from typing import Any

import pandas as pd
from sklearn.metrics import cohen_kappa_score

from darijacare.config import Paths, get_paths
from darijacare.data.proximity import find_near_pairs
from darijacare.data.scripts import detect_script
from darijacare.data.taxonomy import Taxonomy, load_taxonomy
from darijacare.io import read_jsonl, write_json, write_text

log = logging.getLogger("darijacare.data")

COLUMNS = (
    "id",
    "text",
    "script",
    "category",
    "intent",
    "product",
    "urgency",
    "needs_human",
    "cas_limite",
    "annotateur",
)
LABELS = ("category", "intent", "product", "urgency", "needs_human")
SCRIPTS = ("arabic", "arabizi", "mixed")
TARGET_SHARES = {"arabic": 0.35, "arabizi": 0.30, "mixed": 0.25, "cas_limite": 0.10}
SHARE_TOLERANCE = 0.05
MIN_MESSAGES = 300
KAPPA_TARGET = 0.70
PROXIMITY_THRESHOLD = 0.8
"""Character 3-gram Jaccard, as in the split proximity control (Phase 1)."""


def schema_problems(df: pd.DataFrame, taxonomy: Taxonomy) -> list[str]:
    """Missing columns, unknown labels, intents outside their category, bad types."""
    missing = [c for c in COLUMNS if c not in df]
    if missing:
        return [f"colonnes absentes : {missing}"]
    problems = []
    if df["id"].duplicated().any():
        problems.append(
            f"identifiants en double : {df.loc[df['id'].duplicated(), 'id'].tolist()[:5]}"
        )
    empty = df["text"].astype(str).str.strip().eq("")
    if empty.any():
        problems.append(f"{int(empty.sum())} texte(s) vide(s)")
    checks: dict[str, set[Any]] = {
        "script": set(SCRIPTS),
        "category": set(taxonomy.categories),
        "intent": set(taxonomy.intents),
        "product": set(taxonomy.products),
        "urgency": {0, 1, 2, 3},
        "needs_human": {True, False},
        "cas_limite": {True, False},
    }
    for column, allowed in checks.items():
        bad = df["id"][~df[column].isin(list(allowed))].tolist()
        if bad:
            problems.append(f"{column} invalide pour {len(bad)} message(s), ex. {bad[:5]}")
    outside = df["intent"].map(taxonomy.intent_to_category) != df["category"]
    if outside.any():
        problems.append(f"intention hors de sa catégorie : {df.loc[outside, 'id'].tolist()[:5]}")
    return problems


def composition(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Share of each script (edge cases apart) and of edge cases, against Tableau 38."""
    n = len(df)
    edge = df["cas_limite"].astype(bool)
    shares = {s: float(((df["script"] == s) & ~edge).sum()) / n for s in SCRIPTS} if n else {}
    shares["cas_limite"] = float(edge.sum()) / n if n else 0.0
    return {
        k: {
            "part": round(v, 4),
            "cible": TARGET_SHARES[k],
            "ok": abs(v - TARGET_SHARES[k]) <= SHARE_TOLERANCE,
        }
        for k, v in shares.items()
    }


def near_duplicates(gold: Sequence[str], others: Sequence[str]) -> int:
    """Gold messages too close to a synthetic message (copied or lightly edited)."""
    pairs = find_near_pairs(gold, others, threshold=PROXIMITY_THRESHOLD)
    return len({p.query_index for p in pairs})


def check_gold(
    df: pd.DataFrame,
    taxonomy: Taxonomy,
    synthetic_texts: Sequence[str] = (),
) -> dict[str, Any]:
    """Every check of the gold set; ``ok`` only if none fails."""
    problems = schema_problems(df, taxonomy)
    report: dict[str, Any] = {"messages": len(df), "problemes": problems}
    if problems:
        report["ok"] = False
        return report
    if len(df) < MIN_MESSAGES:
        problems.append(f"{len(df)} messages (minimum {MIN_MESSAGES})")
    comp = composition(df)
    report["composition"] = comp
    problems += [
        f"part de {k} : {v['part']:.1%} (cible {v['cible']:.0%} ± {SHARE_TOLERANCE:.0%})"
        for k, v in comp.items()
        if not v["ok"]
    ]
    incoherent = [
        i
        for i, t, s, edge in zip(df["id"], df["text"], df["script"], df["cas_limite"], strict=True)
        if not edge and detect_script(str(t)) != s
    ]
    report["ecriture_a_verifier"] = incoherent[:20]
    duplicated = int(df["text"].str.strip().duplicated().sum())
    if duplicated:
        problems.append(f"{duplicated} texte(s) en double")
    close = near_duplicates(df["text"].astype(str).tolist(), list(synthetic_texts))
    report["proches_du_synthetique"] = close
    if close:
        problems.append(f"{close} message(s) trop proches du jeu synthétique (Jaccard ≥ 0,8)")
    report["ok"] = not problems
    return report


def agreement(first: pd.DataFrame, second: pd.DataFrame) -> dict[str, Any]:
    """Cohen's kappa per label on the doubly annotated sample (weighted for urgency)."""
    both = first.merge(second, on="id", suffixes=("_1", "_2"))
    out: dict[str, Any] = {"messages": len(both)}
    for label in LABELS:
        a, b = both[f"{label}_1"].astype(str), both[f"{label}_2"].astype(str)
        if len(both) and set(a) == set(b) and a.nunique() == 1:
            out[label] = 1.0  # a single label used by both: kappa undefined, agreement total
            continue
        if label == "urgency":
            kappa = cohen_kappa_score(
                both["urgency_1"].astype(int), both["urgency_2"].astype(int), weights="quadratic"
            )
        else:
            kappa = cohen_kappa_score(a, b)
        out[label] = round(float(kappa), 4)
    out["ok"] = len(both) > 0 and all(out[k] >= KAPPA_TARGET for k in ("category", "intent"))
    return out


def run_validate(paths: Paths) -> dict[str, Any]:
    """Validate ``data/gold`` and write ``reports/gold/validation.{json,md}``."""
    gold_dir = paths.root / "data" / "gold"
    gold_path = gold_dir / "gold.jsonl"
    if not gold_path.exists():
        raise SystemExit(f"{gold_path} absent : le jeu gold doit être rédigé par l'équipe")
    taxonomy = load_taxonomy(paths.raw / "telecom_taxonomy.json")
    gold = read_jsonl(gold_path)
    synthetic = [
        t
        for split in ("train", "val", "test")
        if (paths.processed / f"{split}.jsonl").exists()
        for t in read_jsonl(paths.processed / f"{split}.jsonl")["text"]
    ]
    report = check_gold(gold, taxonomy, synthetic)
    double = gold_dir / "double.jsonl"
    if double.exists():
        report["accord"] = agreement(gold, read_jsonl(double))
        report["ok"] = report["ok"] and report["accord"]["ok"]
    else:
        report["accord"] = None
        report["ok"] = False
        report["problemes"].append("double annotation absente (data/gold/double.jsonl)")
    out = paths.reports / "gold"
    write_json(report, out / "validation.json")
    write_text(validation_markdown(report), out / "validation.md")
    return report


def validation_markdown(r: dict[str, Any]) -> str:
    lines = [
        "# Validation du jeu gold",
        "",
        f"{r['messages']} messages — {'conforme' if r['ok'] else 'NON conforme'}.",
        "",
    ]
    if r.get("composition"):
        lines += ["| Part | Mesurée | Cible |", "|---|---|---|"]
        lines += [
            f"| {k} | {v['part']:.1%} | {v['cible']:.0%} |" for k, v in r["composition"].items()
        ]
        lines.append("")
    if r.get("accord"):
        lines.append("Accord inter-annotateurs : " + json.dumps(r["accord"], ensure_ascii=False))
        lines.append("")
    items = [f"- {p}" for p in r["problemes"]] or ["- aucun"]
    lines += ["Problèmes :", *items, ""]
    return "\n".join(lines)


def run_evaluate(paths: Paths, model: str, device: str | None) -> dict[str, Any]:
    """Final evaluation on the gold set and synthetic-to-real gap (once, Figure 15)."""
    from darijacare.nlu.cli import _service, load_train_config
    from darijacare.nlu.evaluate import run_predictions
    from darijacare.nlu.metrics import headline_metrics, metrics_by_group

    gold = read_jsonl(paths.root / "data" / "gold" / "gold.jsonl")
    service = _service(paths, load_train_config(paths), model, device)
    pred = run_predictions(service, gold)
    overall = headline_metrics(gold, pred)
    test_report = paths.reports / "nlu" / model / "test" / "metrics.json"
    test = json.loads(test_report.read_text(encoding="utf-8"))["overall"]
    report = {
        "modele": model,
        "messages": len(gold),
        "gold": overall,
        "par_ecriture": metrics_by_group(gold, pred, "script"),
        "ecart_test_moins_gold_points": {
            k: round(100 * (test[k] - overall[k]), 2)
            for k in ("intent_f1_macro", "intent_end_to_end")
        },
    }
    write_json(report, paths.reports / "gold" / f"evaluation_{model}.json")
    return report


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="python -m darijacare.data.gold")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="contrôles du jeu gold et accord inter-annotateurs")
    ev = sub.add_parser("evaluate", help="évaluation finale (une seule fois)")
    ev.add_argument("--model", default="v5")
    ev.add_argument("--device", default=None)
    args = parser.parse_args(argv)
    paths = get_paths()
    if args.cmd == "validate":
        r = run_validate(paths)
        log.info("jeu gold %s", "conforme" if r["ok"] else f"non conforme : {r['problemes']}")
        return 0 if r["ok"] else 1
    r = run_evaluate(paths, args.model, args.device)
    log.info("écart test - gold : %s", r["ecart_test_moins_gold_points"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
