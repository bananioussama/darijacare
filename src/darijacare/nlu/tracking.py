"""Thin MLflow wrapper: every run records params, seeds, data hashes and code version.

Tracking URI: ``MLFLOW_TRACKING_URI`` if set (e.g. the docker-compose server),
otherwise a local SQLite store ``mlflow.db`` at the repository root.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from darijacare.config import Paths

EXPERIMENT = "darijacare-nlu"


def data_hashes(paths: Paths) -> dict[str, str]:
    """MD5 of every DVC data output recorded in ``dvc.lock``."""
    lock_path = paths.root / "dvc.lock"
    if not lock_path.exists():
        return {}
    lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    return {
        out["path"]: out["md5"]
        for stage in lock.get("stages", {}).values()
        for out in stage.get("outs", [])
        if out["path"].startswith("data/")
    }


def git_commit(root: Path) -> str:
    """Current git commit (``unknown`` outside a repository), suffixed when dirty."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return f"{sha}-dirty" if dirty else sha
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _flatten(d: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, Mapping):
            out.update(_flatten(v, f"{key}."))
        else:
            out[key] = v
    return out


@dataclass
class Run:
    """Handle returned by :func:`start_run`."""

    run_id: str

    def log_metrics(self, metrics: Mapping[str, float], step: int | None = None) -> None:
        import mlflow

        mlflow.log_metrics({k: float(v) for k, v in metrics.items()}, step=step)

    def log_artifact(self, path: Path, artifact_path: str | None = None) -> None:
        import mlflow

        mlflow.log_artifact(str(path), artifact_path=artifact_path)

    def set_tags(self, tags: Mapping[str, str]) -> None:
        import mlflow

        mlflow.set_tags(dict(tags))


@contextmanager
def start_run(name: str, params: Mapping[str, Any], paths: Paths) -> Iterator[Run]:
    """Open an MLflow run with standard tags (data hashes, git commit, library versions)."""
    import mlflow
    import sklearn

    uri = (
        os.environ.get("MLFLOW_TRACKING_URI")
        or f"sqlite:///{(paths.root / 'mlflow.db').as_posix()}"
    )
    mlflow.set_tracking_uri(uri)
    if mlflow.get_experiment_by_name(EXPERIMENT) is None:
        mlflow.create_experiment(
            EXPERIMENT, artifact_location=(paths.root / "mlartifacts").as_uri()
        )
    mlflow.set_experiment(EXPERIMENT)
    # MLflow's SQLite store runs alembic, whose fileConfig() disables existing loggers.
    import logging

    for logger_name in list(logging.root.manager.loggerDict):
        if logger_name.startswith("darijacare"):
            logging.getLogger(logger_name).disabled = False
    with mlflow.start_run(run_name=name) as active:
        flat = {k: str(v)[:500] for k, v in _flatten(params).items()}
        mlflow.log_params(flat)
        tags = {f"data.{k}": v for k, v in data_hashes(paths).items()}
        tags["git_commit"] = git_commit(paths.root)
        tags["sklearn_version"] = sklearn.__version__
        mlflow.set_tags(tags)
        yield Run(active.info.run_id)
