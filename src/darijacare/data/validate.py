"""Blocking data validation (cahier des charges, F-DAT-02 and Table 20).

Checks, in order (any failure raises :class:`ValidationFailed`):

1. Pandera schema: types, allowed labels (taxonomy), urgency 0–3, unique ids,
   non-empty text, and *intent belongs to its category* (100 %).
2. Expected row counts.
3. Script coherent with the text for at least ``min_script_coherence`` of rows
   (exceptions are listed for review, not removed).
4. No id and no exact text shared between train and test.
5. Train/test near-duplicates (character n-gram Jaccard on normalised text):
   blocking for same-intent pairs, reported for cross-intent pairs.

Exact duplicates *inside* a split are not an error (Table 20: "dédoublonnage"):
identical copies are collapsed to the first one; copies with conflicting labels
are removed according to ``duplicate_conflict_policy``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

from darijacare.config import Paths
from darijacare.data.normalize import Normalizer, NormalizerConfig
from darijacare.data.proximity import find_near_pairs, near_pairs_frame
from darijacare.data.scripts import is_script_coherent
from darijacare.data.taxonomy import SCRIPTS, URGENCY_LEVELS, Taxonomy, load_taxonomy
from darijacare.io import read_jsonl, write_json, write_jsonl

log = logging.getLogger(__name__)

LABEL_COLUMNS = ["script", "category", "intent", "product", "urgency", "needs_human"]
GENERATORS = ("claude-opus-5.5", "gemini-3.8-flash", "gemini-4-argon")


class ValidationFailed(RuntimeError):
    """Raised when a blocking data-quality check fails."""


@dataclass
class SplitReport:
    """Validation outcome for one split."""

    rows_in: int
    rows_out: int
    script_coherence: float
    script_coherence_by_script: dict[str, float]
    script_exceptions: list[dict[str, Any]] = field(default_factory=list)
    duplicates_removed: list[dict[str, Any]] = field(default_factory=list)


def build_schema(taxonomy: Taxonomy) -> pa.DataFrameSchema:
    """Return the Pandera schema for one split of the dataset."""
    i2c = taxonomy.intent_to_category

    def intent_in_category(df: pd.DataFrame) -> pd.Series:
        return df["intent"].map(i2c) == df["category"]

    return pa.DataFrameSchema(
        {
            "id": pa.Column(str, unique=True, nullable=False),
            "text": pa.Column(
                str,
                checks=pa.Check(lambda s: s.str.strip().str.len() > 0, name="texte_non_vide"),
                nullable=False,
            ),
            "script": pa.Column(str, pa.Check.isin(SCRIPTS)),
            "category": pa.Column(str, pa.Check.isin(list(taxonomy.categories))),
            "intent": pa.Column(str, pa.Check.isin(taxonomy.intents)),
            "product": pa.Column(str, pa.Check.isin(taxonomy.products)),
            "urgency": pa.Column(int, pa.Check.isin(URGENCY_LEVELS)),
            "needs_human": pa.Column(bool),
            "persona": pa.Column(str, nullable=False),
            "generator": pa.Column(str, pa.Check.isin(GENERATORS)),
            "round": pa.Column(int, pa.Check.ge(1)),
        },
        checks=[pa.Check(intent_in_category, name="intention_dans_categorie")],
        strict=True,
        ordered=False,
        coerce=False,
    )


def check_schema(df: pd.DataFrame, schema: pa.DataFrameSchema, split: str) -> None:
    """Validate ``df`` against ``schema`` and raise a readable error listing all failures."""
    try:
        schema.validate(df, lazy=True)
    except SchemaErrors as exc:
        cases = exc.failure_cases
        summary = (
            cases.groupby(["column", "check"], dropna=False).size().to_string()
            if isinstance(cases, pd.DataFrame) and not cases.empty
            else str(exc)
        )
        raise ValidationFailed(f"[{split}] schéma invalide :\n{summary}") from exc


def deduplicate(
    df: pd.DataFrame, conflict_policy: str
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Collapse exact text duplicates.

    Identical copies keep the first row (by id). Copies whose labels disagree are
    all dropped (``drop_all``) or reduced to the first one (``keep_first``).

    Returns:
        The deduplicated frame (original order) and a description of removed rows.
    """
    if conflict_policy not in {"drop_all", "keep_first"}:
        raise ValueError(f"duplicate_conflict_policy invalide : {conflict_policy!r}")
    ordered = df.sort_values("id", kind="stable")
    dup_mask = ordered["text"].duplicated(keep=False)
    removed: list[dict[str, Any]] = []
    drop_ids: set[str] = set()
    for text, group in ordered[dup_mask].groupby("text", sort=True):
        conflicting = len(group[LABEL_COLUMNS].drop_duplicates()) > 1
        if conflicting and conflict_policy == "drop_all":
            to_drop = group
            reason = "labels_divergents"
        else:
            to_drop = group.iloc[1:]
            reason = "labels_divergents" if conflicting else "copie_identique"
        for _, row in to_drop.iterrows():
            drop_ids.add(row["id"])
            removed.append(
                {
                    "id": row["id"],
                    "text": text,
                    "intent": row["intent"],
                    "reason": reason,
                    "kept_id": (
                        None
                        if reason == "labels_divergents" and conflict_policy == "drop_all"
                        else group.iloc[0]["id"]
                    ),
                }
            )
    out = df[~df["id"].isin(drop_ids)].reset_index(drop=True)
    return out, sorted(removed, key=lambda r: r["id"])


def script_coherence(df: pd.DataFrame) -> tuple[pd.Series, list[dict[str, Any]]]:
    """Return a boolean coherence mask and the list of incoherent rows."""
    mask = pd.Series(
        [is_script_coherent(t, s) for t, s in zip(df["text"], df["script"], strict=True)],
        index=df.index,
    )
    exceptions = [
        {"id": r.id, "script": r.script, "text": r.text}
        for r in df.loc[~mask, ["id", "script", "text"]].itertuples(index=False)
    ]
    return mask, exceptions


def validate_split(
    df: pd.DataFrame, split: str, schema: pa.DataFrameSchema, vcfg: dict[str, Any]
) -> tuple[pd.DataFrame, SplitReport]:
    """Run the per-split checks and deduplication."""
    check_schema(df, schema, split)
    expected = vcfg.get("expected_rows", {}).get(split)
    if expected is not None and len(df) != expected:
        raise ValidationFailed(f"[{split}] {len(df)} lignes au lieu de {expected}")
    mask, exceptions = script_coherence(df)
    rate = float(mask.mean())
    by_script = {s: round(float(mask[df["script"] == s].mean()), 4) for s in SCRIPTS}
    if rate < vcfg["min_script_coherence"]:
        raise ValidationFailed(
            f"[{split}] cohérence script/texte {rate:.4f} < {vcfg['min_script_coherence']}"
        )
    clean, removed = deduplicate(df, vcfg["duplicate_conflict_policy"])
    report = SplitReport(
        rows_in=len(df),
        rows_out=len(clean),
        script_coherence=round(rate, 4),
        script_coherence_by_script=by_script,
        script_exceptions=exceptions,
        duplicates_removed=removed,
    )
    return clean, report


def check_cross_split(
    train: pd.DataFrame,
    test: pd.DataFrame,
    pcfg: dict[str, Any],
    normalizer: Normalizer,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Check id/text leakage and near-duplicates between train and test."""
    shared_ids = sorted(set(train["id"]) & set(test["id"]))
    if shared_ids:
        raise ValidationFailed(f"ids communs train/test : {shared_ids[:5]}")
    shared_text = sorted(set(train["text"]) & set(test["text"]))
    if shared_text:
        raise ValidationFailed(f"{len(shared_text)} textes identiques entre train et test")

    tr = train.assign(text_norm=train["text"].map(normalizer))
    te = test.assign(text_norm=test["text"].map(normalizer))
    pairs = find_near_pairs(
        te["text_norm"].tolist(),
        tr["text_norm"].tolist(),
        n=pcfg["ngram"],
        threshold=pcfg["threshold"],
    )
    frame = near_pairs_frame(te, tr, pairs)
    same = int(frame["same_intent"].sum()) if not frame.empty else 0
    summary = {
        "ngram": pcfg["ngram"],
        "threshold": pcfg["threshold"],
        "pairs_total": len(frame),
        "pairs_same_intent": same,
        "pairs_cross_intent": len(frame) - same,
        "test_rows_with_near_train": int(frame["query_id"].nunique()) if not frame.empty else 0,
    }
    blocking = same if pcfg.get("block_on", "same_intent") == "same_intent" else len(frame)
    if blocking > pcfg.get("max_allowed_pairs", 0):
        raise ValidationFailed(
            f"{blocking} paires train/test quasi identiques (Jaccard ≥ {pcfg['threshold']}) "
            f"au-delà du maximum autorisé ({pcfg.get('max_allowed_pairs', 0)})"
        )
    return frame, summary


def run_validation(paths: Paths, config: dict[str, Any]) -> dict[str, Any]:
    """Validate the raw splits, write cleaned copies to ``data/interim`` and a report.

    Outputs:
        ``data/interim/validated/{train,test}.jsonl`` and ``reports/validation/``.
    """
    vcfg = config["validation"]
    taxonomy = load_taxonomy(paths.raw / "telecom_taxonomy.json")
    expected_tax = vcfg.get("expected_taxonomy", {"categories": 12, "intents": 75})
    if (len(taxonomy.categories), len(taxonomy.intents)) != (
        expected_tax["categories"],
        expected_tax["intents"],
    ):
        raise ValidationFailed(
            f"Taxonomie inattendue : {len(taxonomy.categories)} catégories, "
            f"{len(taxonomy.intents)} intentions"
        )
    schema = build_schema(taxonomy)
    normalizer = Normalizer(NormalizerConfig.from_mapping(config["normalize"]))

    out_dir = paths.interim / "validated"
    rep_dir = paths.reports / "validation"
    rep_dir.mkdir(parents=True, exist_ok=True)
    clean: dict[str, pd.DataFrame] = {}
    split_reports: dict[str, Any] = {}
    for split in ("train", "test"):
        df = read_jsonl(paths.raw / f"{split}.jsonl")
        clean[split], rep = validate_split(df, split, schema, vcfg)
        split_reports[split] = {
            "rows_in": rep.rows_in,
            "rows_out": rep.rows_out,
            "script_coherence": rep.script_coherence,
            "script_coherence_by_script": rep.script_coherence_by_script,
            "script_exceptions": len(rep.script_exceptions),
            "duplicates_removed": rep.duplicates_removed,
        }
        pd.DataFrame(rep.script_exceptions, columns=["id", "script", "text"]).to_csv(
            rep_dir / f"script_exceptions_{split}.csv",
            index=False,
            encoding="utf-8",
            lineterminator="\n",
        )
        log.info(
            "[%s] %d -> %d lignes ; cohérence script %.4f",
            split,
            rep.rows_in,
            rep.rows_out,
            rep.script_coherence,
        )

    near, near_summary = check_cross_split(
        clean["train"], clean["test"], vcfg["proximity"], normalizer
    )
    near.to_csv(
        rep_dir / "train_test_near_pairs.csv", index=False, encoding="utf-8", lineterminator="\n"
    )

    for split, df in clean.items():
        write_jsonl(df, out_dir / f"{split}.jsonl")

    report = {
        "status": "ok",
        "taxonomy": {
            "name": taxonomy.name,
            "categories": len(taxonomy.categories),
            "intents": len(taxonomy.intents),
            "products": len(taxonomy.products),
        },
        "splits": split_reports,
        "train_test_proximity": near_summary,
    }
    write_json(report, rep_dir / "report.json")
    return report
