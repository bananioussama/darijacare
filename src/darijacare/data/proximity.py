"""Near-duplicate search with character n-gram Jaccard similarity.

Each text is turned into its *set* of character n-grams (binary sparse vector).
For two sets A and B, ``|A ∩ B|`` is a sparse dot product, so
``J = |A ∩ B| / (|A| + |B| - |A ∩ B|)``. Queries are processed in chunks so
memory stays bounded (chunk_size x n_reference dense block).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer


@dataclass(frozen=True)
class NearPair:
    """A query/reference pair above the similarity threshold."""

    query_index: int
    reference_index: int
    jaccard: float


def ngram_set(text: str, n: int = 3) -> set[str]:
    """Return the set of character ``n``-grams of ``text`` (padded with spaces)."""
    padded = f" {text} "
    if len(padded) < n:
        return {padded}
    return {padded[i : i + n] for i in range(len(padded) - n + 1)}


def jaccard(a: str, b: str, n: int = 3) -> float:
    """Exact character n-gram Jaccard similarity of two strings (reference implementation)."""
    sa, sb = ngram_set(a, n), ngram_set(b, n)
    union = len(sa | sb)
    return len(sa & sb) / union if union else 1.0


def _binary_matrix(
    texts_a: Sequence[str], texts_b: Sequence[str], n: int
) -> tuple[sparse.csr_matrix, sparse.csr_matrix]:
    # analyzer="char" with ngram_range (n, n) pads words, so we pass a callable
    # that matches ngram_set() exactly.
    vec = CountVectorizer(analyzer=lambda t: list(ngram_set(t, n)), binary=True, dtype=np.int32)
    vec.fit(list(texts_a) + list(texts_b))
    a = vec.transform(texts_a).tocsr()
    b = vec.transform(texts_b).tocsr()
    return a, b


def find_near_pairs(
    queries: Sequence[str],
    references: Sequence[str],
    *,
    n: int = 3,
    threshold: float = 0.8,
    chunk_size: int = 512,
    exclude_self: bool = False,
) -> list[NearPair]:
    """Return every (query, reference) pair with Jaccard >= ``threshold``.

    Args:
        queries: texts to check.
        references: texts to compare against.
        n: character n-gram size.
        threshold: minimum Jaccard similarity.
        chunk_size: number of queries per dense block.
        exclude_self: when ``queries`` and ``references`` are the same list,
            skip the diagonal and report each unordered pair once.
    """
    if len(queries) == 0 or len(references) == 0:
        return []
    q, r = _binary_matrix(queries, references, n)
    q_sizes = np.asarray(q.sum(axis=1)).ravel()
    r_sizes = np.asarray(r.sum(axis=1)).ravel()
    r_t = r.T.tocsc()
    pairs: list[NearPair] = []
    for start in range(0, q.shape[0], chunk_size):
        stop = min(start + chunk_size, q.shape[0])
        inter = (q[start:stop] @ r_t).toarray()
        union = q_sizes[start:stop, None] + r_sizes[None, :] - inter
        with np.errstate(divide="ignore", invalid="ignore"):
            sim = np.where(union > 0, inter / union, 1.0)
        rows, cols = np.nonzero(sim >= threshold)
        for i, j in zip(rows.tolist(), cols.tolist(), strict=True):
            qi = start + i
            if exclude_self and j <= qi:
                continue
            pairs.append(NearPair(qi, j, float(sim[i, j])))
    return pairs


def near_pairs_frame(
    query_df: pd.DataFrame,
    ref_df: pd.DataFrame,
    pairs: Sequence[NearPair],
    text_col: str = "text_norm",
) -> pd.DataFrame:
    """Describe ``pairs`` as a DataFrame (ids, intents, texts, similarity)."""
    records = []
    for p in pairs:
        qrow = query_df.iloc[p.query_index]
        rrow = ref_df.iloc[p.reference_index]
        records.append(
            {
                "query_id": qrow["id"],
                "reference_id": rrow["id"],
                "query_intent": qrow["intent"],
                "reference_intent": rrow["intent"],
                "same_intent": qrow["intent"] == rrow["intent"],
                "jaccard": round(p.jaccard, 4),
                "query_text": qrow[text_col],
                "reference_text": rrow[text_col],
            }
        )
    cols = [
        "query_id",
        "reference_id",
        "query_intent",
        "reference_intent",
        "same_intent",
        "jaccard",
        "query_text",
        "reference_text",
    ]
    return pd.DataFrame(records, columns=cols).sort_values(
        ["query_id", "reference_id"], ignore_index=True
    )
