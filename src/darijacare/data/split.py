"""Reproducible train / validation / test split (cahier des charges, F-DAT-04, §12.5).

* The official test set is kept exactly as published (only ``text_norm`` is added).
* About 10 % of the official train set becomes validation, stratified by
  intent x script x generator. Strata smaller than ``min_stratum_size`` fall
  back to coarser keys (intent x script, then intent) so every stratum can be split.
* Proximity control: validation rows whose character n-gram Jaccard with any
  training row reaches the threshold are moved back to train, so no validation
  message is a near copy of a training message.
* The class distributions of train and validation must stay within
  ``max_distribution_gap_points`` (Table 20), otherwise the stage fails.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from sklearn.model_selection import train_test_split

from darijacare.config import Paths
from darijacare.data.proximity import find_near_pairs, near_pairs_frame
from darijacare.io import read_jsonl, write_json, write_jsonl

log = logging.getLogger(__name__)


class SplitFailed(RuntimeError):
    """Raised when the split does not satisfy the acceptance checks."""


def stratification_key(
    df: pd.DataFrame,
    primary: list[str],
    fallbacks: list[list[str]],
    min_size: int,
) -> pd.Series:
    """Build a stratum label per row, falling back to coarser keys for rare strata.

    Each row gets the finest key whose stratum, counted among the rows not yet
    assigned, has at least ``min_size`` rows. Rows left over after the last key
    go to a shared ``rest`` stratum (merged into the largest stratum if it would
    hold a single row, which a stratified split cannot handle).
    """
    levels = [primary, *fallbacks]
    key = pd.Series([None] * len(df), index=df.index, dtype=object)
    for depth, cols in enumerate(levels):
        free = key.isna()
        if not free.any():
            break
        candidate = df.loc[free, cols].astype(str).agg("|".join, axis=1)
        counts = candidate.map(candidate.value_counts())
        take = counts[counts >= min_size].index
        key[take] = f"L{depth}:" + candidate[take]
    rest = key.isna()
    if rest.any():
        if rest.sum() >= 2:
            key[rest] = "rest"
        else:
            key[rest] = key.value_counts().idxmax()
    return key


def distribution_gaps(
    train: pd.DataFrame, val: pd.DataFrame, columns: list[str]
) -> dict[str, float]:
    """Return, per column, the largest absolute gap (percentage points) between splits."""
    gaps: dict[str, float] = {}
    for col in columns:
        p = train[col].astype(str).value_counts(normalize=True)
        q = val[col].astype(str).value_counts(normalize=True)
        diff = p.sub(q, fill_value=0).abs().max() * 100
        gaps[col] = round(float(diff), 3)
    return gaps


def make_split(
    train_full: pd.DataFrame, cfg: dict[str, Any], seed: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Split ``train_full`` into train and validation.

    Returns:
        ``(train, val, moved_pairs, info)`` where ``moved_pairs`` lists the
        validation rows moved back to train by the proximity control.
    """
    df = train_full.sort_values("id", kind="stable").reset_index(drop=True)
    key = stratification_key(
        df, cfg["stratify_by"], cfg.get("fallback_keys", []), cfg["min_stratum_size"]
    )
    tr_idx, va_idx = train_test_split(
        df.index.to_numpy(),
        test_size=cfg["val_fraction"],
        random_state=seed,
        shuffle=True,
        stratify=key.to_numpy(),
    )
    train = df.loc[sorted(tr_idx)].reset_index(drop=True)
    val = df.loc[sorted(va_idx)].reset_index(drop=True)

    pcfg = cfg["proximity"]
    pairs = find_near_pairs(
        val["text_norm"].tolist(),
        train["text_norm"].tolist(),
        n=pcfg["ngram"],
        threshold=pcfg["threshold"],
    )
    moved = near_pairs_frame(val, train, pairs)
    if pcfg.get("action", "move_to_train") != "move_to_train":
        raise SplitFailed(f"split.proximity.action inconnue : {pcfg.get('action')!r}")
    moved_ids = set(moved["query_id"])
    if moved_ids:
        back = val[val["id"].isin(moved_ids)]
        val = val[~val["id"].isin(moved_ids)].reset_index(drop=True)
        train = pd.concat([train, back]).sort_values("id", kind="stable").reset_index(drop=True)

    # The proximity control must now hold: re-check the final validation set.
    remaining = find_near_pairs(
        val["text_norm"].tolist(),
        train["text_norm"].tolist(),
        n=pcfg["ngram"],
        threshold=pcfg["threshold"],
    )
    if remaining:
        raise SplitFailed(f"{len(remaining)} lignes de validation encore trop proches du train")

    gaps = distribution_gaps(train, val, cfg["check_columns"])
    worst = max(gaps.values()) if gaps else 0.0
    if worst > cfg["max_distribution_gap_points"]:
        raise SplitFailed(
            f"Écart de distribution train/validation {worst:.2f} pts > "
            f"{cfg['max_distribution_gap_points']} pts : {gaps}"
        )
    info = {
        "strata": int(key.nunique()),
        "strata_by_level": {
            lvl: int(n)
            for lvl, n in key.str.split(":", n=1).str[0].value_counts().sort_index().items()
        },
        "val_moved_to_train": len(moved_ids),
        "distribution_gap_points": gaps,
    }
    return train, val, moved, info


def run_split(paths: Paths, config: dict[str, Any]) -> dict[str, Any]:
    """Pipeline stage: write ``data/processed/{train,val,test}.jsonl`` and a report."""
    cfg = config["split"]
    seed = int(config["seed"])
    train_full = read_jsonl(paths.interim / "normalized" / "train.jsonl")
    test = read_jsonl(paths.interim / "normalized" / "test.jsonl")
    train, val, moved, info = make_split(train_full, cfg, seed)

    if set(train["id"]) & set(val["id"]):
        raise SplitFailed("Des ids sont à la fois dans train et validation")
    if len(train) + len(val) != len(train_full):
        raise SplitFailed("Des lignes ont été perdues pendant le découpage")

    out = paths.processed
    write_jsonl(train, out / "train.jsonl")
    write_jsonl(val, out / "val.jsonl")
    write_jsonl(test, out / "test.jsonl")

    rep_dir = paths.reports / "split"
    rep_dir.mkdir(parents=True, exist_ok=True)
    moved.to_csv(
        rep_dir / "val_moved_to_train.csv", index=False, encoding="utf-8", lineterminator="\n"
    )
    report = {
        "seed": seed,
        "rows": {"train": len(train), "val": len(val), "test": len(test)},
        "val_fraction_effective": round(len(val) / len(train_full), 4),
        **info,
        "val_by_script": val["script"].value_counts().sort_index().to_dict(),
        "val_by_generator": val["generator"].value_counts().sort_index().to_dict(),
        "val_intents": int(val["intent"].nunique()),
        "val_min_per_intent": int(val["intent"].value_counts().min()),
    }
    write_json(report, rep_dir / "report.json")
    log.info("Découpage : %s", report["rows"])
    return report
