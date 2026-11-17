"""Unit tests for versioned ingestion (local mode, hash checks, determinism)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from darijacare.config import get_paths
from darijacare.data.ingest import IngestError, ingest


def _setup(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "repo"
    src = tmp_path / "src"
    root.mkdir()
    src.mkdir()
    files = {}
    for name, content in {"train.jsonl": b'{"a": 1}\n', "README (1).md": b"# card\n"}.items():
        (src / name).write_bytes(content)
    files["train.jsonl"] = {
        "hub_path": "data/train.jsonl",
        "local_names": ["train.jsonl"],
        "sha256": hashlib.sha256(b'{"a": 1}\n').hexdigest(),
    }
    files["DATASET_CARD.md"] = {
        "hub_path": "README.md",
        "local_names": ["README.md", "README (1).md"],
        "sha256": hashlib.sha256(b"# card\n").hexdigest(),
    }
    config = {
        "source": {
            "repo_id": "org/ds",
            "repo_type": "dataset",
            "revision": "abc123",
            "mode": "local",
            "local_dir": str(src),
            "license": "CC-BY-4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "author": "Auteur",
            "title": "Titre",
            "url": "https://example.org",
            "year": 2026,
            "files": files,
        }
    }
    return root, config


def test_ingest_local_copies_and_hashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DARIJACARE_SOURCE_DIR", raising=False)
    root, config = _setup(tmp_path)
    paths = get_paths(root)
    manifest = ingest(paths, config)
    assert (paths.raw / "train.jsonl").read_bytes() == b'{"a": 1}\n'
    assert (paths.raw / "DATASET_CARD.md").exists()  # found under its alternative name
    assert {"LICENSE.txt", "ATTRIBUTION.md", "manifest.json"} <= {
        p.name for p in paths.raw.iterdir()
    }
    assert manifest["revision"] == "abc123"
    assert "CC-BY-4.0" in (paths.raw / "LICENSE.txt").read_text(encoding="utf-8")


def test_ingest_is_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DARIJACARE_SOURCE_DIR", raising=False)
    root, config = _setup(tmp_path)
    paths = get_paths(root)
    ingest(paths, config)
    first = {p.name: p.read_bytes() for p in paths.raw.iterdir()}
    ingest(paths, config)
    second = {p.name: p.read_bytes() for p in paths.raw.iterdir()}
    assert first == second


def test_ingest_rejects_wrong_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DARIJACARE_SOURCE_DIR", raising=False)
    root, config = _setup(tmp_path)
    config["source"]["files"]["train.jsonl"]["sha256"] = "0" * 64
    with pytest.raises(IngestError, match="Empreinte inattendue"):
        ingest(get_paths(root), config)


def test_ingest_local_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DARIJACARE_SOURCE_DIR", raising=False)
    root, config = _setup(tmp_path)
    (Path(config["source"]["local_dir"]) / "train.jsonl").unlink()
    with pytest.raises(IngestError, match="introuvable"):
        ingest(get_paths(root), config)


def test_ingest_invalid_mode(tmp_path: Path) -> None:
    root, config = _setup(tmp_path)
    config["source"]["mode"] = "ftp"
    with pytest.raises(IngestError, match="mode"):
        ingest(get_paths(root), config)
