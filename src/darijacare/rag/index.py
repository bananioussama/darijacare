"""Vector index of the knowledge base (cahier des charges, F-KB-02).

* Chunking by section: one chunk per (fiche, language, section), prefixed with
  the fiche title so short sections keep their context (5 sections x 2 languages).
* BGE-M3 dense + sparse vectors through the official ``FlagEmbedding`` library
  (``BGEM3FlagModel.encode(..., return_dense=True, return_sparse=True)``).
* Qdrant collection with named vectors ``dense`` (cosine) and ``sparse`` and a
  payload ``fiche_id, intent, category, lang, section, version, status, text``.
* Idempotent: point ids are UUID5 of ``intent/lang/section``; re-indexing
  overwrites them and removes points that no longer exist (deleted section, etc.).
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from darijacare.rag.kb import HEADINGS, LANGS, SECTION_KEYS, Fiche

log = logging.getLogger(__name__)

NAMESPACE = uuid.UUID("6f1f6c1e-3d0c-4b4f-9a57-6b0a8c2f4d21")


@dataclass(frozen=True)
class Chunk:
    """A searchable piece of a fiche."""

    fiche_id: str
    intent: str
    category: str
    lang: str
    section: str
    version: int
    status: str
    text: str

    @property
    def point_id(self) -> str:
        return str(uuid.uuid5(NAMESPACE, f"{self.intent}/{self.lang}/{self.section}"))

    def payload(self) -> dict[str, Any]:
        return {
            "fiche_id": self.fiche_id,
            "intent": self.intent,
            "category": self.category,
            "lang": self.lang,
            "section": self.section,
            "version": self.version,
            "status": self.status,
            "text": self.text,
        }


@dataclass
class Encoded:
    """Dense (n, d) matrix and sparse ``{token_id: weight}`` dicts for n texts."""

    dense: np.ndarray
    sparse: list[dict[str, float]]


class Embedder(Protocol):
    """What indexing and retrieval need from an embedding model."""

    dim: int

    def encode(self, texts: Sequence[str]) -> Encoded: ...


class BGEM3Embedder:
    """BGE-M3 dense + sparse, as documented by ``FlagEmbedding`` (``BGEM3FlagModel``)."""

    dim = 1024

    def __init__(
        self,
        model_path: str | Path,
        batch_size: int = 16,
        max_length: int = 512,
        use_fp16: bool = False,
        device: str | None = None,
    ) -> None:
        from FlagEmbedding import BGEM3FlagModel

        self.model = BGEM3FlagModel(str(model_path), use_fp16=use_fp16, devices=device)
        self.batch_size = batch_size
        self.max_length = max_length

    def encode(self, texts: Sequence[str]) -> Encoded:
        out = self.model.encode(
            list(texts),
            batch_size=self.batch_size,
            max_length=self.max_length,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        dense = np.asarray(out["dense_vecs"], dtype=np.float32).reshape(len(texts), -1)
        sparse = [{str(k): float(v) for k, v in d.items()} for d in out["lexical_weights"]]
        return Encoded(dense, sparse)


def chunk_fiches(fiches: Mapping[str, Fiche]) -> list[Chunk]:
    """One chunk per fiche, language and section, with the fiche title as context."""
    chunks = []
    for intent in sorted(fiches):
        f = fiches[intent]
        for lang in LANGS:
            for key in SECTION_KEYS:
                text = f"{f.titles[lang]} — {HEADINGS[lang][key]} : {f.text(lang, key)}"
                chunks.append(
                    Chunk(f.id, f.intent, f.category, lang, key, f.version, f.status, text)
                )
    return chunks


def sparse_vector(weights: Mapping[str, float]) -> Any:
    """Convert BGE-M3 lexical weights to a Qdrant ``SparseVector`` (sorted indices)."""
    from qdrant_client import models

    items = sorted((int(k), float(v)) for k, v in weights.items() if v > 0)
    return models.SparseVector(indices=[i for i, _ in items], values=[v for _, v in items])


def get_client(cfg: Mapping[str, Any], root: Path) -> Any:
    """``QdrantClient`` for ``QDRANT_URL`` (server) or the local embedded store."""
    from qdrant_client import QdrantClient

    url = os.environ.get("QDRANT_URL")
    if url:
        return QdrantClient(url=url)
    path = Path(cfg["local_path"])
    return QdrantClient(path=str(path if path.is_absolute() else root / path))


def ensure_collection(client: Any, name: str, dim: int) -> None:
    """Create the collection with named dense and sparse vectors if it does not exist."""
    from qdrant_client import models

    if client.collection_exists(name):
        return
    client.create_collection(
        name,
        vectors_config={"dense": models.VectorParams(size=dim, distance=models.Distance.COSINE)},
        sparse_vectors_config={"sparse": models.SparseVectorParams()},
    )


def index_chunks(
    client: Any, collection: str, chunks: Sequence[Chunk], embedder: Embedder
) -> dict[str, int]:
    """Upsert chunks (idempotent) and delete points that are no longer in the knowledge base."""
    from qdrant_client import models

    ensure_collection(client, collection, embedder.dim)
    enc = embedder.encode([c.text for c in chunks])
    points = [
        models.PointStruct(
            id=c.point_id,
            payload=c.payload(),
            vector={"dense": enc.dense[i].tolist(), "sparse": sparse_vector(enc.sparse[i])},
        )
        for i, c in enumerate(chunks)
    ]
    for start in range(0, len(points), 128):
        client.upsert(collection, points[start : start + 128])
    keep = {c.point_id for c in chunks}
    stale: list[Any] = []
    offset = None
    while True:
        records, offset = client.scroll(collection, limit=256, offset=offset, with_payload=False)
        stale += [r.id for r in records if str(r.id) not in keep]
        if offset is None:
            break
    if stale:
        client.delete(collection, points_selector=models.PointIdsList(points=stale))
    return {
        "upserted": len(points),
        "deleted": len(stale),
        "total": int(client.count(collection).count),
    }
