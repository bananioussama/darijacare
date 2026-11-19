"""Reference data written at start-up (steering and knowledge domains of the class diagram).

* :class:`ConfigDecision`: ``configs/decision.yaml``, identified by its content hash
  and marked active;
* :class:`ModeleNLU`: the served model (version, encoder, published and reproduced
  metrics, MLflow run when it is the registry champion), other versions are archived;
* :class:`ExecutionEvaluation`: the official-test evaluation of that model
  (``reports/nlu/<model>/``);
* :class:`FicheKB` and :class:`Chunk`: a mirror of ``kb/`` and of the Qdrant points
  (``kb/`` stays the source of truth, the mirror is rewritten each time).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from darijacare.api.models import Chunk, ConfigDecision, ExecutionEvaluation, FicheKB, ModeleNLU
from darijacare.config import Paths
from darijacare.rag.index import chunk_fiches
from darijacare.rag.kb import HEADINGS, LANGS, SECTION_KEYS, Fiche

log = logging.getLogger("darijacare.api")


def config_id(raw_yaml: str) -> str:
    """Identifier of a decision configuration: SHA-256 prefix of the YAML text."""
    return hashlib.sha256(raw_yaml.encode("utf-8")).hexdigest()[:16]


def sync_decision_config(db: Session, cfg: Mapping[str, Any], raw_yaml: str) -> ConfigDecision:
    """Store the configuration if new and make it the only active one."""
    cid = config_id(raw_yaml)
    row = db.get(ConfigDecision, cid)
    if row is None:
        row = ConfigDecision(
            id=cid,
            confidence_threshold=float(cfg["thresholds"]["intent_confidence"]),
            needs_human_threshold=float(cfg["thresholds"]["needs_human"]),
            priority_weights=dict(cfg["priority"]["weights"]),
            content=json.loads(json.dumps(cfg)),
        )
        db.add(row)
        db.flush()
    db.execute(update(ConfigDecision).where(ConfigDecision.id != cid).values(active=False))
    row.active = True
    return row


def ensure_model(
    db: Session,
    version: str,
    encoder: str = "inconnu",
    metrics: Mapping[str, Any] | None = None,
    mlflow_run: str | None = None,
) -> ModeleNLU:
    """Return the model row, created if needed and marked in service; others are archived.

    ``mlflow_run`` links the served model to its evaluation run (MLflow registry, F-OPS-01).
    """
    row = db.get(ModeleNLU, version)
    if row is None:
        row = ModeleNLU(version=version, encoder=encoder, metrics=dict(metrics or {}))
        db.add(row)
        db.flush()
    elif metrics:
        row.metrics = dict(metrics)
    if mlflow_run:
        row.mlflow_run = mlflow_run
    row.status = "en_service"
    db.execute(
        update(ModeleNLU)
        .where(ModeleNLU.version != version, ModeleNLU.status == "en_service")
        .values(status="archive")
    )
    return row


def served_model_info(paths: Paths, train_cfg: Mapping[str, Any], name: str) -> dict[str, Any]:
    """Version, encoder and metrics of a published model, read from its files and reports."""
    spec = train_cfg["published_models"][name]
    model_dir = paths.root / spec["path"]
    agent_cfg = model_dir / "rl_agent_config.json"
    encoder = (
        json.loads(agent_cfg.read_text(encoding="utf-8")).get("encoder", "inconnu")
        if agent_cfg.exists()
        else "inconnu"
    )
    metrics: dict[str, Any] = {"published": spec.get("published", {})}
    report = paths.reports / "nlu" / name / "test" / "metrics.json"
    if report.exists():
        metrics["reproduced_test"] = json.loads(report.read_text(encoding="utf-8"))["overall"]
    return {
        "version": f"{name}@{spec['revision'][:8]}",
        "encoder": encoder,
        "metrics": metrics,
        "mlflow_run": champion_run(paths, name),
    }


def champion_run(paths: Paths, name: str) -> str | None:
    """MLflow run of ``name`` if it is the registry champion (``reports/nlu/registry.json``)."""
    registry = paths.reports / "nlu" / "registry.json"
    if not registry.exists():
        log.warning("registre de modèles absent (python -m darijacare.nlu.registry promote)")
        return None
    current = json.loads(registry.read_text(encoding="utf-8")).get("champion", {})
    if current.get("modele") != name:
        log.warning(
            "le modèle servi (%s) n'est pas le champion du registre (%s)",
            name,
            current.get("modele"),
        )
        return None
    run: str | None = current.get("run_id")
    return run


def sync_evaluations(db: Session, paths: Paths, name: str, version: str) -> int:
    """Import the official-test evaluation of model ``name`` (0 if the report is missing)."""
    report = paths.reports / "nlu" / name / "test" / "metrics.json"
    if not report.exists():
        return 0
    m = json.loads(report.read_text(encoding="utf-8"))
    ece = None
    calibration = paths.reports / "nlu" / name / "calibration" / "calibration.json"
    if calibration.exists():
        c = json.loads(calibration.read_text(encoding="utf-8"))
        # The served model keeps its published temperatures: ECE "avant" our re-calibration.
        ece = c.get("ece", {}).get("test", {}).get("intent_end_to_end", {}).get("avant")
    source = report.relative_to(paths.root).as_posix()
    row = db.scalar(
        select(ExecutionEvaluation).where(
            ExecutionEvaluation.model_version == version,
            ExecutionEvaluation.dataset == "test",
            ExecutionEvaluation.source == source,
        )
    )
    if row is None:
        row = ExecutionEvaluation(model_version=version, dataset="test", source=source)
        db.add(row)
    overall = m.get("overall", {})
    row.f1_macro = overall.get("intent_f1_macro")
    row.ece = ece
    row.metrics = {"overall": overall, "intent_by_script": m.get("intent_by_script", {})}
    return 1


def fiche_part_text(f: Fiche, lang: str) -> str:
    """One language part of a fiche as Markdown sections."""
    parts = []
    for key in SECTION_KEYS:
        value = f.sections[lang][key]
        body = "\n".join(f"- {v}" for v in value) if isinstance(value, list) else str(value)
        parts.append(f"## {HEADINGS[lang][key]}\n{body}")
    return "\n\n".join(parts)


def sync_knowledge_base(db: Session, fiches: Mapping[str, Fiche]) -> tuple[int, int]:
    """Rewrite the ``fiche_kb`` / ``chunk`` mirror of ``kb/``; return (parts, chunks)."""
    db.execute(delete(Chunk))
    db.execute(delete(FicheKB))
    n_parts = 0
    for f in fiches.values():
        for lang in LANGS:
            db.add(
                FicheKB(
                    id=f"{f.id}:{lang}",
                    fiche_id=f.id,
                    intent=f.intent,
                    lang=lang,
                    title=f.titles[lang],
                    content=fiche_part_text(f, lang),
                    version=f.version,
                    status=f.status,
                )
            )
            n_parts += 1
    db.flush()
    chunks = chunk_fiches(fiches)
    db.add_all(
        Chunk(
            id=uuid.UUID(c.point_id),
            fiche_kb_id=f"{c.fiche_id}:{c.lang}",
            section=c.section,
            text=c.text,
            vector_id=c.point_id,
            payload=c.payload(),
        )
        for c in chunks
    )
    return n_parts, len(chunks)
