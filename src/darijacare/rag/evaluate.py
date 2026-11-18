"""Retrieval evaluation: Recall@k and MRR, with and without the intent filter (hypothesis H4).

Labelled queries are the dataset messages of a split; the expected fiche is the one of
the gold intent. Settings:

* ``sans_filtre``: hybrid search over all 75 fiches;
* ``filtre_predit``: filter on the intent predicted by the NLU model (+ neighbours),
  so NLU errors propagate, as in production; ranking by retrieval only;
* ``filtre_predit_rrf``: same filter, NLU ranking fused as a third RRF list;
* ``filtre_predit_premier``: same filter, predicted intent's fiche first, retrieval
  orders the alternatives;
* ``nlu_seul``: no search at all, fiches ranked as [predicted intent, neighbours…]
  (what the NLU alone would give);
* ``filtre_oracle``: filter on the gold intent (+ neighbours), retrieval ranking only.

Query encodings are cached in ``reports/rag/<split>/query_cache.*`` (not versioned),
so settings can be compared without re-encoding thousands of messages.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from darijacare.config import Paths
from darijacare.io import read_jsonl, write_json, write_text
from darijacare.rag.index import Encoded
from darijacare.rag.retrieve import Retriever

log = logging.getLogger(__name__)

SETTINGS = (
    "sans_filtre",
    "filtre_predit",
    "filtre_predit_rrf",
    "filtre_predit_premier",
    "nlu_seul",
    "filtre_oracle",
)


def rank_of(expected: str, ranked: list[str]) -> int | None:
    """1-based rank of ``expected`` in ``ranked`` (``None`` when absent)."""
    return ranked.index(expected) + 1 if expected in ranked else None


def summarize(ranks: list[int | None], ks: tuple[int, ...] = (1, 3)) -> dict[str, float]:
    """Recall@k and MRR from a list of ranks."""
    n = len(ranks) or 1
    out = {f"recall@{k}": sum(1 for r in ranks if r is not None and r <= k) / n for k in ks}
    out["mrr"] = sum(1.0 / r for r in ranks if r is not None) / n
    return out


def encode_cached(retriever: Retriever, texts: list[str], cache_dir: Path) -> Encoded:
    """Encode ``texts`` once; reuse ``query_cache.npz`` / ``.json`` when the texts match."""
    key = hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()
    npz, js = cache_dir / "query_cache.npz", cache_dir / "query_cache.json"
    if npz.exists() and js.exists():
        meta = json.loads(js.read_text(encoding="utf-8"))
        if meta.get("key") == key:
            log.info("Encodages des requêtes relus depuis le cache")
            return Encoded(np.load(npz)["dense"], meta["sparse"])
    log.info("Encodage de %d requêtes", len(texts))
    enc = retriever.embedder.encode(texts)
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(npz, dense=enc.dense)
    js.write_text(json.dumps({"key": key, "sparse": enc.sparse}), encoding="utf-8")
    return enc


def run_rag_evaluation(
    paths: Paths,
    retriever: Retriever,
    split: str,
    nlu_model: str,
    rounds: list[int] | None = None,
) -> dict[str, Any]:
    """Evaluate retrieval on ``split`` and write ``reports/rag/<name>/``.

    With ``rounds``, only messages of those generation rounds are evaluated (e.g. the
    rounds a model never saw); the whole split is still encoded once and cached.
    """
    gold = read_jsonl(paths.processed / f"{split}.jsonl")
    pred_path = paths.reports / "nlu" / nlu_model / split / "predictions.jsonl"
    pred = read_jsonl(pred_path) if pred_path.exists() else None
    enc = encode_cached(retriever, gold["text"].tolist(), paths.reports / "rag" / split)
    name_parts = (
        [split] if not rounds else [split, nlu_model, "rondes-" + "-".join(map(str, rounds))]
    )
    out = paths.reports / "rag" / "_".join(name_parts)
    out.mkdir(parents=True, exist_ok=True)
    keep = gold["round"].isin(rounds).to_numpy() if rounds else np.ones(len(gold), bool)

    rows = []
    for i, r in enumerate(gold.itertuples(index=False)):
        if not keep[i]:
            continue
        dense, sparse = enc.dense[i].tolist(), enc.sparse[i]
        gold_intent = str(r.intent)
        row: dict[str, Any] = {"id": r.id, "script": r.script, "intent": gold_intent}
        # name -> (intent used for the filter, filter on, NLU prior mode)
        runs: dict[str, tuple[str | None, bool, str]] = {
            "sans_filtre": (None, False, "none"),
            "filtre_oracle": (gold_intent, True, "none"),
        }
        if pred is not None:
            predicted = str(pred["intent"].iloc[i])
            runs["filtre_predit"] = (predicted, True, "none")
            runs["filtre_predit_rrf"] = (predicted, True, "rrf")
            runs["filtre_predit_premier"] = (predicted, True, "first")
            nlu_ranking = (retriever.candidates(predicted) or [predicted])[: retriever.top_n]
            row["nlu_seul_rank"] = rank_of(gold_intent, nlu_ranking)
            row["nlu_seul_top1"] = predicted
        for name, (intent, flt, prior) in runs.items():
            res = retriever.search_encoded(dense, sparse, intent, use_filter=flt, use_prior=prior)
            row[f"{name}_rank"] = rank_of(gold_intent, res.intents)
            row[f"{name}_top1"] = res.intents[0] if res.intents else None
            row[f"{name}_dense"] = res.fiches[0].best_dense if res.fiches else None
            row[f"{name}_reliable"] = res.reliable
        rows.append(row)
        if (i + 1) % 500 == 0:
            log.info("%d/%d", i + 1, len(gold))
    df = pd.DataFrame(rows)

    summary: dict[str, Any] = {
        "split": split,
        "n": len(df),
        "nlu_model": nlu_model,
        "rounds": rounds,
        "production_prior": retriever.prior_mode,
    }
    for name in SETTINGS:
        col = f"{name}_rank"
        if col not in df:
            continue
        ranks = [None if pd.isna(x) else int(x) for x in df[col]]
        summary[name] = summarize(ranks)
        summary[name]["par_script"] = {
            s: summarize([None if pd.isna(x) else int(x) for x in g[col]])
            for s, g in df.groupby("script")
        }
        if f"{name}_reliable" in df:
            summary[name]["fiable"] = float(df[f"{name}_reliable"].mean())
    # Dense score of the top fiche when it is right vs wrong (reliability threshold).
    for name in ("sans_filtre", "filtre_predit_premier"):
        if f"{name}_top1" not in df:
            continue
        ok = df[f"{name}_top1"] == df["intent"]
        summary[f"score_dense_top1_{name}"] = {
            "juste_mediane": float(np.nanmedian(df.loc[ok, f"{name}_dense"])),
            "faux_mediane": (
                float(np.nanmedian(df.loc[~ok, f"{name}_dense"])) if (~ok).any() else None
            ),
        }
    df.to_csv(out / "details.csv", index=False, encoding="utf-8", lineterminator="\n")
    write_json(summary, out / "summary.json")
    write_text(_markdown(summary), out / "README.md")
    return {"summary": summary}


LABELS = {
    "sans_filtre": "Sans filtre (75 fiches)",
    "filtre_predit": "Filtre intention prédite, classement recherche",
    "filtre_predit_rrf": "Filtre prédit + priorité NLU par RRF",
    "filtre_predit_premier": "Filtre prédit + fiche de l'intention prédite en tête",
    "nlu_seul": "NLU seul (intention prédite puis voisines)",
    "filtre_oracle": "Filtre vraie intention, classement recherche (borne)",
}


def _markdown(s: dict[str, Any]) -> str:
    lines = [
        f"# Évaluation de la recherche — {s['split']} ({s['n']} requêtes"
        + (f", rondes {s['rounds']}" if s.get("rounds") else "")
        + ")",
        "",
        "Requête = message du jeu ; fiche attendue = fiche de l'intention annotée. "
        f"Intention prédite par le modèle NLU `{s['nlu_model']}`. Données synthétiques. "
        f"Mode de production : `nlu_prior: {s['production_prior']}`.",
        "",
        "| Réglage | Recall@1 | Recall@3 | MRR | arabe R@3 | arabizi R@3 | mixte R@3 |",
        "|---|---|---|---|---|---|---|",
    ]
    for name in SETTINGS:
        if name not in s:
            continue
        m = s[name]
        ps = m["par_script"]
        lines.append(
            f"| {LABELS[name]} | {m['recall@1']:.3f} | {m['recall@3']:.3f} | {m['mrr']:.3f} | "
            + " | ".join(
                f"{ps.get(x, {}).get('recall@3', float('nan')):.3f}"
                for x in ("arabic", "arabizi", "mixed")
            )
            + " |"
        )
    return "\n".join(lines) + "\n"
