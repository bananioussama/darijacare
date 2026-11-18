"""Command line (migrations, accounts) and reference data (served model, evaluations)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from darijacare.api import cli
from darijacare.api.models import ExecutionEvaluation, ModeleNLU, Utilisateur
from darijacare.api.reference import ensure_model, served_model_info, sync_evaluations
from darijacare.config import get_paths
from darijacare.nlu.cli import load_train_config


def test_cli_migrates_and_creates_accounts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"sqlite:///{(tmp_path / 'cli.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("DARIJACARE_NEW_PASSWORD", "un-mot-de-passe-assez-long")
    monkeypatch.setattr(cli, "configure_json_logging", lambda: None)
    assert cli.main(["db-upgrade"]) == 0  # the migration also runs on SQLite
    assert cli.main(["create-user", "--username", "admin", "--role", "admin"]) == 0
    with pytest.raises(SystemExit):  # duplicate account
        cli.main(["create-user", "--username", "admin", "--role", "admin"])
    monkeypatch.setenv("DARIJACARE_NEW_PASSWORD", "court")
    with pytest.raises(SystemExit):  # too short
        cli.main(["create-user", "--username", "autre", "--role", "ml"])
    engine = create_engine(url)
    try:
        with Session(engine) as db:
            users = db.scalars(select(Utilisateur)).all()
            assert [(u.username, u.role) for u in users] == [("admin", "admin")]
            assert users[0].password_hash.startswith("$argon2id$")
    finally:
        engine.dispose()


def test_served_model_info_comes_from_the_published_files() -> None:
    paths = get_paths()
    cfg = load_train_config(paths)
    if not (paths.root / cfg["published_models"]["v5"]["path"] / "rl_agent_config.json").exists():
        pytest.skip("modèle v5 absent (models/ n'est pas versionné)")
    info = served_model_info(paths, cfg, "v5")
    assert info["version"] == "v5@8e694ecf"
    assert info["encoder"] == "jhu-clsp/mmBERT-base"
    assert info["metrics"]["published"]["intent_end_to_end"] == 89.6


def test_evaluation_import_and_model_versions(engine: Engine) -> None:
    paths = get_paths()
    with Session(engine) as db:
        ensure_model(db, "v5@8e694ecf", "jhu-clsp/mmBERT-base", {"published": {}})
        if sync_evaluations(db, paths, "v5", "v5@8e694ecf") == 0:
            pytest.skip("rapport reports/nlu/v5/test/metrics.json absent")
        assert sync_evaluations(db, paths, "v5", "v5@8e694ecf") == 1  # idempotent
        db.commit()
        evaluation = db.scalar(select(ExecutionEvaluation))
        assert evaluation is not None and evaluation.dataset == "test"
        assert evaluation.f1_macro == pytest.approx(0.895, abs=1e-3)
        assert evaluation.ece == pytest.approx(0.045, abs=1e-3)
        assert db.scalar(select(func.count()).select_from(ExecutionEvaluation)) == 1
        ensure_model(db, "v6@00000000", "jhu-clsp/mmBERT-base")
        db.commit()
        statuses = dict(db.execute(select(ModeleNLU.version, ModeleNLU.status)).all())
        assert statuses == {"v5@8e694ecf": "archive", "v6@00000000": "en_service"}
