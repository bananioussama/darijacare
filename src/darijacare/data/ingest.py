"""Versioned ingestion of the public dataset (cahier des charges, F-DAT-01).

Copies ``train.jsonl``, ``test.jsonl``, ``telecom_taxonomy.json`` and the dataset
card into ``data/raw`` (bronze zone, immutable), from a local folder or from the
Hugging Face Hub at a pinned revision. Each file's SHA-256 must match the value
in ``configs/data.yaml``; any mismatch stops the pipeline.

The outputs are deterministic (no timestamps, no machine-specific paths), so a
rerun gives the same hashes, which DVC records in ``dvc.lock``.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from darijacare.config import Paths
from darijacare.io import sha256_file, write_json, write_text

log = logging.getLogger(__name__)


class IngestError(RuntimeError):
    """Raised when a source file is missing or its hash does not match."""


def _local_dir(paths: Paths, source: dict[str, Any]) -> Path:
    env = os.environ.get("DARIJACARE_SOURCE_DIR")
    base = Path(env) if env else Path(source.get("local_dir", ".."))
    return base if base.is_absolute() else (paths.root / base).resolve()


def _find_local(local_dir: Path, names: list[str]) -> Path | None:
    for name in names:
        candidate = local_dir / name
        if candidate.is_file():
            return candidate
    return None


def _download(source: dict[str, Any], hub_path: str) -> Path:
    """Download one file from the Hub at the pinned revision (uses the local HF cache)."""
    from huggingface_hub import hf_hub_download

    return Path(
        hf_hub_download(
            repo_id=source["repo_id"],
            filename=hub_path,
            repo_type=source.get("repo_type", "dataset"),
            revision=source["revision"],
        )
    )


def _license_text(source: dict[str, Any]) -> str:
    return (
        f"{source['title']}\n"
        f"Auteur : {source['author']} ({source['year']})\n"
        f"Source : {source['url']}\n"
        f"Révision : {source['revision']}\n"
        f"Licence : {source['license']} — {source['license_url']}\n\n"
        "Ces données sont redistribuées et modifiées dans le cadre du projet académique\n"
        "DarijaCare conformément à la licence Creative Commons Attribution 4.0.\n"
        "Les modifications apportées sont décrites dans ATTRIBUTION.md.\n"
    )


def _attribution_md(source: dict[str, Any]) -> str:
    return f"""# Attribution

- **Titre** : {source['title']}
- **Auteur** : {source['author']}
- **Année** : {source['year']}
- **Lien** : {source['url']}
- **Révision figée** : `{source['revision']}`
- **Licence** : [{source['license']}]({source['license_url']})

Données **synthétiques** générées par des modèles de langage, non relues par des
locuteurs natifs (voir `DATASET_CARD.md`).

## Modifications apportées par DarijaCare

Les fichiers de `data/raw/` sont des copies **non modifiées**. Les étapes suivantes
du pipeline produisent des données dérivées :

1. **Validation** : suppression des doublons exacts (les doublons dont les labels
   divergent sont retirés car ambigus) ; contrôle des labels et du script.
2. **Normalisation** : ajout d'une colonne `text_norm` (Unicode NFKC, suppression des
   diacritiques et du tatweel, unification des alef/ya, chiffres arabo-indiens en
   ASCII, minuscules, réduction des allongements, masquage `<TEL>`/`<URL>`/`<EMAIL>`).
   Le texte d'origine est conservé dans `text`.
3. **Découpage** : création d'un jeu de validation (≈ 10 % du train officiel, stratifié
   par intention, script et générateur) ; le test officiel est conservé tel quel.
"""


def ingest(paths: Paths, config: dict[str, Any]) -> dict[str, Any]:
    """Copy or download the source files into ``data/raw`` and verify their hashes.

    Returns:
        The manifest written to ``data/raw/manifest.json``.

    Raises:
        IngestError: if a file cannot be found or its SHA-256 differs from the config.
    """
    source = config["source"]
    mode = source.get("mode", "auto")
    if mode not in {"auto", "local", "hub"}:
        raise IngestError(f"source.mode invalide : {mode!r}")
    local_dir = _local_dir(paths, source)
    raw = paths.raw
    if raw.exists():
        shutil.rmtree(raw)
    raw.mkdir(parents=True)

    files_manifest: dict[str, Any] = {}
    for target, spec in source["files"].items():
        origin: Path | None = None
        if mode in {"auto", "local"}:
            origin = _find_local(local_dir, spec.get("local_names", [target]))
            if origin is None and mode == "local":
                raise IngestError(f"{target} introuvable dans {local_dir}")
        if origin is None:
            log.info("Téléchargement de %s @ %s", spec["hub_path"], source["revision"][:8])
            origin = _download(source, spec["hub_path"])
        else:
            log.info("Copie locale de %s", origin.name)
        dest = raw / target
        shutil.copyfile(origin, dest)
        digest = sha256_file(dest)
        if digest != spec["sha256"]:
            raise IngestError(
                f"Empreinte inattendue pour {target} : {digest} (attendu {spec['sha256']}). "
                "La source ne correspond pas à la révision figée."
            )
        files_manifest[target] = {
            "hub_path": spec["hub_path"],
            "sha256": digest,
            "bytes": dest.stat().st_size,
        }

    write_text(_license_text(source), raw / "LICENSE.txt")
    write_text(_attribution_md(source), raw / "ATTRIBUTION.md")
    manifest = {
        "dataset": source["repo_id"],
        "revision": source["revision"],
        "license": source["license"],
        "author": source["author"],
        "files": files_manifest,
    }
    write_json(manifest, raw / "manifest.json")
    return manifest
