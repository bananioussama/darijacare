"""Deterministic file I/O helpers (JSONL, JSON, hashes).

Every writer produces byte-identical output for identical input so that
``dvc repro`` yields the same hashes across runs and machines
(UTF-8, ``\\n`` line endings, stable key order, no timestamps).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

COLUMNS = [
    "id",
    "text",
    "script",
    "category",
    "intent",
    "product",
    "urgency",
    "needs_human",
    "persona",
    "generator",
    "round",
]


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Return the hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path: Path) -> pd.DataFrame:
    """Read a JSONL file into a DataFrame, keeping ``id`` and ``text`` as strings."""
    rows = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: JSON invalide ({exc})") from exc
    return pd.DataFrame(rows)


def _to_builtin(value: Any) -> Any:
    """Convert numpy / pandas scalars into JSON-serialisable Python objects."""
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        return value.item()
    return value


def write_jsonl(df: pd.DataFrame, path: Path) -> None:
    """Write ``df`` as UTF-8 JSONL (one object per row, column order preserved)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(df.columns)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for record in df.itertuples(index=False, name=None):
            obj = {c: _to_builtin(v) for c, v in zip(cols, record, strict=True)}
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def write_json(obj: Mapping[str, Any] | Iterable[Any], path: Path) -> None:
    """Write ``obj`` as pretty, key-sorted UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=_to_builtin)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def write_text(text: str, path: Path) -> None:
    """Write UTF-8 text with ``\\n`` line endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
