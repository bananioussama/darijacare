"""Hybrid retrieval filtered by the predicted intent (cahier des charges, F-KB-03).

1. Candidate intents = predicted intent + its top confused neighbours (from a
   confusion matrix measured on data the model never saw), unless the filter is off.
2. Dense search and sparse search, each limited to ``top_k`` chunks, with a
   payload filter ``intent ∈ candidates``.
3. Reciprocal Rank Fusion at chunk level: ``score = Σ 1 / (rrf_k + rank)``.
4. Fiches are ranked by their best chunk, then the NLU prior is applied
   (``nlu_prior``): ``first`` puts the predicted intent's fiche first and lets
   retrieval order the alternatives; ``rrf`` adds the NLU ranking as a third RRF
   list at fiche level; ``none`` keeps the retrieval ranking. Retrieval alone ranks
   the right fiche first only ~60 % of the time among the candidates, while the NLU
   intent is right ~90 % of the time (see docs/rag.md).
5. ``top_n`` fiches are returned; a fiche is "reliable" when its best dense
   similarity reaches ``min_dense_score``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from darijacare.rag.index import Embedder, sparse_vector


@dataclass(frozen=True)
class Hit:
    """One retrieved chunk."""

    point_id: str
    payload: dict[str, Any]
    rrf: float
    dense_score: float | None
    sparse_score: float | None


@dataclass
class FicheHit:
    """A fiche with its fused score and supporting chunks."""

    fiche_id: str
    intent: str
    version: int
    score: float
    best_dense: float
    chunks: list[Hit] = field(default_factory=list)


@dataclass
class RetrievalResult:
    """Ranked fiches for one query."""

    fiches: list[FicheHit]
    candidates: list[str] | None
    reliable: bool

    @property
    def intents(self) -> list[str]:
        return [f.intent for f in self.fiches]


def rrf_fuse(rankings: Sequence[Sequence[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion of several ranked id lists (rank starts at 1)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, pid in enumerate(ranking, start=1):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank)
    return scores


PRIOR_MODES = ("first", "rrf", "none")


def prior_mode(value: str | bool) -> str:
    """Normalise the ``nlu_prior`` setting (booleans kept for compatibility)."""
    if isinstance(value, bool):
        return "rrf" if value else "none"
    if value not in PRIOR_MODES:
        raise ValueError(f"nlu_prior invalide : {value!r} (attendu {PRIOR_MODES})")
    return value


def load_neighbours(path: Path) -> dict[str, list[str]]:
    """``{intent: [neighbour, ...]}`` from a ``top_confusions`` JSON file (empty if absent)."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: [n["label"] for n in v] for k, v in data.items()}


class Retriever:
    """Hybrid, intent-filtered retriever over the Qdrant collection."""

    def __init__(
        self,
        client: Any,
        collection: str,
        embedder: Embedder,
        cfg: Mapping[str, Any],
        neighbours: Mapping[str, list[str]] | None = None,
    ) -> None:
        self.client = client
        self.collection = collection
        self.embedder = embedder
        self.top_k = int(cfg["top_k"])
        self.rrf_k = int(cfg["rrf_k"])
        self.top_n = int(cfg["top_n"])
        self.n_neighbours = int(cfg.get("neighbours", 3))
        self.min_dense = float(cfg["min_dense_score"])
        self.use_filter = bool(cfg.get("use_intent_filter", True))
        self.prior_mode = prior_mode(cfg.get("nlu_prior", "first"))
        self.neighbours = dict(neighbours or {})

    def candidates(self, intent: str | None) -> list[str] | None:
        """Predicted intent + neighbours, or ``None`` (no filter)."""
        if not self.use_filter or intent is None:
            return None
        return [intent, *self.neighbours.get(intent, [])[: self.n_neighbours]]

    def _filter(self, candidates: list[str] | None) -> Any:
        if candidates is None:
            return None
        from qdrant_client import models

        return models.Filter(
            must=[models.FieldCondition(key="intent", match=models.MatchAny(any=list(candidates)))]
        )

    def search(
        self,
        query: str,
        intent: str | None = None,
        use_filter: bool | None = None,
        use_prior: str | bool | None = None,
    ) -> RetrievalResult:
        """Retrieve the ``top_n`` fiches for ``query`` (filtered by ``intent`` if enabled)."""
        enc = self.embedder.encode([query])
        return self.search_encoded(
            enc.dense[0].tolist(), enc.sparse[0], intent, use_filter, use_prior
        )

    def search_encoded(
        self,
        dense: list[float],
        sparse: Mapping[str, float],
        intent: str | None = None,
        use_filter: bool | None = None,
        use_prior: str | bool | None = None,
    ) -> RetrievalResult:
        """Same as :meth:`search` with a pre-computed query encoding (batch evaluation).

        ``use_prior`` overrides the configured NLU prior: ``"first"``, ``"rrf"``,
        ``"none"`` (``True`` means ``"rrf"``, ``False`` means ``"none"``).
        """
        filtering = self.use_filter if use_filter is None else use_filter
        prior = self.prior_mode if use_prior is None else prior_mode(use_prior)
        cands = self.candidates(intent) if filtering else None
        flt = self._filter(cands)
        dense_pts = self.client.query_points(
            self.collection,
            query=dense,
            using="dense",
            query_filter=flt,
            limit=self.top_k,
            with_payload=True,
        ).points
        sv = sparse_vector(sparse)
        sparse_pts = (
            self.client.query_points(
                self.collection,
                query=sv,
                using="sparse",
                query_filter=flt,
                limit=self.top_k,
                with_payload=True,
            ).points
            if sv.indices
            else []
        )
        fused = rrf_fuse(
            [[str(p.id) for p in dense_pts], [str(p.id) for p in sparse_pts]], self.rrf_k
        )
        payloads = {str(p.id): p.payload for p in [*dense_pts, *sparse_pts]}
        d_scores = {str(p.id): float(p.score) for p in dense_pts}
        s_scores = {str(p.id): float(p.score) for p in sparse_pts}
        by_fiche: dict[str, FicheHit] = {}
        for pid, score in sorted(fused.items(), key=lambda kv: (-kv[1], kv[0])):
            pl = payloads[pid]
            hit = Hit(pid, pl, score, d_scores.get(pid), s_scores.get(pid))
            fh = by_fiche.get(pl["fiche_id"])
            if fh is None:
                fh = FicheHit(pl["fiche_id"], pl["intent"], int(pl["version"]), score, -1.0)
                by_fiche[pl["fiche_id"]] = fh
            fh.chunks.append(hit)
            if hit.dense_score is not None:
                fh.best_dense = max(fh.best_dense, hit.dense_score)
        if prior == "rrf" and cands:
            # NLU prior as a third RRF list at fiche level: predicted intent, then neighbours.
            for rank, cand in enumerate(cands, start=1):
                for fh in by_fiche.values():
                    if fh.intent == cand:
                        fh.score += 1.0 / (self.rrf_k + rank)
        ranked = sorted(by_fiche.values(), key=lambda f: (-f.score, f.fiche_id))
        if prior == "first" and cands:
            # The predicted intent's fiche leads; retrieval orders the alternatives.
            lead = next((f for f in ranked if f.intent == cands[0]), None)
            if lead is None:
                lead = self._fetch_fiche(dense, cands[0])
            elif lead.best_dense < 0:
                # Found through sparse search only: measure its dense support explicitly.
                fetched = self._fetch_fiche(dense, cands[0])
                if fetched is not None:
                    lead.best_dense = fetched.best_dense
            if lead is not None:
                ranked = [lead, *(f for f in ranked if f.fiche_id != lead.fiche_id)]
        ranked = ranked[: self.top_n]
        reliable = bool(ranked) and ranked[0].best_dense >= self.min_dense
        return RetrievalResult(ranked, cands, reliable)

    def _fetch_fiche(self, dense: list[float], intent: str) -> FicheHit | None:
        """Best chunk of one intent's fiche (used when the search returned none of it)."""
        pts = self.client.query_points(
            self.collection,
            query=dense,
            using="dense",
            query_filter=self._filter([intent]),
            limit=1,
            with_payload=True,
        ).points
        if not pts:
            return None
        p = pts[0]
        hit = Hit(str(p.id), p.payload, 0.0, float(p.score), None)
        return FicheHit(
            p.payload["fiche_id"], intent, int(p.payload["version"]), 0.0, float(p.score), [hit]
        )
