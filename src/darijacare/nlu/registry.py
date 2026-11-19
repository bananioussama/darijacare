"""MLflow model registry and explicit promotion (F-OPS-01, Tableau 35 « non-régression »).

Registered model ``darijacare-nlu``. A model version is created from the evaluation run
of a model on the frozen set (``eval_<model>_<split>``, written by
``python -m darijacare.nlu.cli evaluate``), so that every deployed model is linked to a
run, to its weights (SHA-256, Hub revision) and to the data version (``dvc.lock`` hashes
recorded as run tags).

Promotion is explicit and moves the ``champion`` alias. It is refused when a guarded
metric drops by more than one point against the current champion, unless a written
justification is given (cahier des charges, Tableau 35: « aucune baisse > 1 point de F1
macro sans justification »). The decision is recorded on the model version and in
``reports/nlu/registry.json``, which the API reads to store the run of the served model.

    python -m darijacare.nlu.registry register --model v5
    python -m darijacare.nlu.registry compare --candidate v3 --reference v5
    python -m darijacare.nlu.registry promote --model v5 [--justification "..."]
    python -m darijacare.nlu.registry status
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from darijacare.config import Paths, get_paths
from darijacare.io import write_json

log = logging.getLogger("darijacare.nlu")

REGISTERED_MODEL = "darijacare-nlu"
CHAMPION = "champion"
TOLERANCE_POINTS = 1.0
GUARDED: tuple[str, ...] = (
    "intent_f1_macro",
    "intent_end_to_end",
    "category_f1_macro",
    "product_f1_macro",
    "needs_human_f1_macro",
)


class PromotionRefused(RuntimeError):
    """Raised when the candidate regresses and no justification is given."""

    def __init__(self, comparison: Mapping[str, Any]) -> None:
        super().__init__(
            "Promotion refusée : baisse de plus de "
            f"{comparison['tolerance_points']} point(s) sur {', '.join(comparison['regressions'])}"
        )
        self.comparison = dict(comparison)


def compare_metrics(
    candidate: Mapping[str, float],
    reference: Mapping[str, float],
    tolerance_points: float = TOLERANCE_POINTS,
    guarded: Sequence[str] = GUARDED,
) -> dict[str, Any]:
    """Metric-by-metric comparison (in points); a drop beyond the tolerance is a regression."""
    rows = []
    for metric in guarded:
        if metric not in candidate or metric not in reference:
            continue
        delta = round(100 * (float(candidate[metric]) - float(reference[metric])), 2)
        rows.append(
            {
                "metrique": metric,
                "candidat": round(float(candidate[metric]), 4),
                "reference": round(float(reference[metric]), 4),
                "ecart_points": delta,
                "regression": delta < -tolerance_points,
            }
        )
    regressions = [r["metrique"] for r in rows if r["regression"]]
    return {
        "lignes": rows,
        "regressions": regressions,
        "ok": not regressions,
        "tolerance_points": tolerance_points,
    }


def overall_metrics(paths: Paths, model: str, split: str) -> dict[str, float]:
    """``overall`` metrics of ``reports/nlu/<model>/<split>/metrics.json``."""
    path = paths.reports / "nlu" / model / split / "metrics.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} absent : lancer `python -m darijacare.nlu.cli evaluate --model {model} "
            f"--split {split}`"
        )
    overall: dict[str, float] = json.loads(path.read_text(encoding="utf-8"))["overall"]
    return overall


def tracking_uri(paths: Paths) -> str:
    """Same rule as :func:`darijacare.nlu.tracking.start_run`."""
    return (
        os.environ.get("MLFLOW_TRACKING_URI")
        or f"sqlite:///{(paths.root / 'mlflow.db').as_posix()}"
    )


def make_client(paths: Paths) -> Any:
    from mlflow import MlflowClient

    uri = tracking_uri(paths)
    return MlflowClient(tracking_uri=uri, registry_uri=uri)


def eval_run(client: Any, model: str, split: str) -> Any:
    """Latest run named ``eval_<model>_<split>`` of the NLU experiment."""
    from darijacare.nlu.tracking import EXPERIMENT

    experiment = client.get_experiment_by_name(EXPERIMENT)
    if experiment is None:
        raise LookupError(f"Expérience MLflow « {EXPERIMENT} » absente")
    runs = client.search_runs(
        [experiment.experiment_id],
        filter_string=f"tags.mlflow.runName = 'eval_{model}_{split}'",
        order_by=["attributes.start_time DESC"],
        max_results=1,
    )
    if not runs:
        raise LookupError(f"Aucun run eval_{model}_{split} : évaluer le modèle d'abord")
    return runs[0]


def model_source(spec: Mapping[str, Any]) -> str:
    """Where the weights come from: the Hub revision, or the local folder."""
    if spec.get("repo"):
        return f"hf://{spec['repo']}@{spec['revision']}"
    return str(spec["path"])


def is_registered(client: Any) -> bool:
    """Whether the registered model exists (``search_registered_models``)."""
    return bool(client.search_registered_models(filter_string=f"name = '{REGISTERED_MODEL}'"))


def find_version(client: Any, model: str, weights_sha256: str) -> Any | None:
    """Existing version of ``model`` with these weights (registration is idempotent)."""
    if not is_registered(client):
        return None
    for v in client.search_model_versions(f"name = '{REGISTERED_MODEL}'"):
        if v.tags.get("modele") == model and v.tags.get("weights_sha256") == weights_sha256:
            return v
    return None


def register(paths: Paths, model: str, split: str = "test", client: Any = None) -> Any:
    """Create (once) the model version of ``model``, linked to its evaluation run."""
    from darijacare.nlu.cli import load_train_config, model_spec

    client = client or make_client(paths)
    spec = model_spec(paths, load_train_config(paths), model)  # checks the weights' SHA-256
    existing = find_version(client, model, spec["weights_sha256"])
    if existing is not None:
        return existing
    run = eval_run(client, model, split)
    if not is_registered(client):
        client.create_registered_model(
            REGISTERED_MODEL,
            description="NLU DarijaCare (catégorie, intention, produit, urgence, needs_human).",
        )
    data = {k: v for k, v in run.data.tags.items() if k.startswith("data.")}
    metrics = overall_metrics(paths, model, split)
    tags = {
        "modele": model,
        "revision": str(spec["revision"]),
        "weights_sha256": str(spec["weights_sha256"]),
        "evaluation": f"eval_{model}_{split}",
        **data,
        **{f"metrique.{k}": f"{metrics[k]:.4f}" for k in GUARDED if k in metrics},
    }
    version = client.create_model_version(
        REGISTERED_MODEL,
        source=model_source(spec),
        run_id=run.info.run_id,
        tags=tags,
        description=str(spec.get("trained_on", "")),
    )
    log.info("version %s enregistrée pour %s (run %s)", version.version, model, run.info.run_id)
    return version


def champion(client: Any) -> Any | None:
    """Current champion version, or ``None``."""
    if not is_registered(client):
        return None
    try:
        return client.get_model_version_by_alias(REGISTERED_MODEL, CHAMPION)
    except Exception:  # alias not set yet (MlflowException)
        return None


def promote(
    paths: Paths,
    model: str,
    split: str = "test",
    justification: str | None = None,
    client: Any = None,
) -> dict[str, Any]:
    """Move ``champion`` to ``model`` if it does not regress (or with a justification)."""
    client = client or make_client(paths)
    candidate = register(paths, model, split, client)
    current = champion(client)
    if current is not None and current.version == candidate.version:
        return {"modele": model, "version": candidate.version, "deja_champion": True}
    if current is None:
        comparison: dict[str, Any] = {"lignes": [], "regressions": [], "ok": True}
        previous = None
    else:
        previous = current.tags.get("modele")
        comparison = compare_metrics(
            overall_metrics(paths, model, split), overall_metrics(paths, str(previous), split)
        )
        if not comparison["ok"] and not justification:
            raise PromotionRefused(comparison)
    when = datetime.now(UTC).isoformat(timespec="seconds")
    client.set_registered_model_alias(REGISTERED_MODEL, CHAMPION, candidate.version)
    for key, value in {
        "promotion.date": when,
        "promotion.precedent": previous or "aucun",
        "promotion.justification": justification or "aucune régression",
    }.items():
        client.set_model_version_tag(REGISTERED_MODEL, candidate.version, key, value)
    record = {
        "registered_model": REGISTERED_MODEL,
        "alias": CHAMPION,
        "modele": model,
        "version": candidate.version,
        "run_id": candidate.run_id,
        "source": candidate.source,
        "promu_le": when,
        "precedent": previous,
        "justification": justification,
        "comparaison": comparison,
    }
    write_registry(paths, record)
    return record


def write_registry(paths: Paths, record: Mapping[str, Any]) -> None:
    """``reports/nlu/registry.json``: current champion and promotion history."""
    path = paths.reports / "nlu" / "registry.json"
    history: list[dict[str, Any]] = []
    if path.exists():
        history = json.loads(path.read_text(encoding="utf-8")).get("historique", [])
    write_json({"champion": dict(record), "historique": [*history, dict(record)]}, path)


def read_registry(paths: Paths) -> dict[str, Any] | None:
    """Content of ``reports/nlu/registry.json`` (``None`` when absent)."""
    path = paths.reports / "nlu" / "registry.json"
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def comparison_markdown(candidate: str, reference: str, c: Mapping[str, Any]) -> str:
    lines = [
        f"Comparaison {candidate} (candidat) / {reference} (référence), tolérance "
        f"{c['tolerance_points']} point :",
        "",
        "| Métrique | Candidat | Référence | Écart (points) | Régression |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| {r['metrique']} | {r['candidat']:.4f} | {r['reference']:.4f} | "
        f"{r['ecart_points']:+.2f} | {'OUI' if r['regression'] else 'non'} |"
        for r in c["lignes"]
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Command line: register, compare, promote, status."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="python -m darijacare.nlu.registry")
    sub = parser.add_subparsers(dest="cmd", required=True)
    reg = sub.add_parser("register", help="enregistrer un modèle évalué")
    reg.add_argument("--model", required=True)
    reg.add_argument("--split", default="test")
    cmp_ = sub.add_parser("compare", help="test de non-régression entre deux modèles")
    cmp_.add_argument("--candidate", required=True)
    cmp_.add_argument("--reference", default=None, help="défaut : le champion actuel")
    cmp_.add_argument("--split", default="test")
    pro = sub.add_parser("promote", help="promotion explicite (alias champion)")
    pro.add_argument("--model", required=True)
    pro.add_argument("--split", default="test")
    pro.add_argument("--justification", default=None)
    sub.add_parser("status", help="champion actuel")
    args = parser.parse_args(argv)
    paths = get_paths()
    if args.cmd == "register":
        v = register(paths, args.model, args.split)
        print(f"{REGISTERED_MODEL} version {v.version} : {args.model} (run {v.run_id})")
    elif args.cmd == "compare":
        reference = args.reference
        if reference is None:
            current = champion(make_client(paths))
            if current is None:
                raise SystemExit("Aucun champion : préciser --reference")
            reference = current.tags["modele"]
        c = compare_metrics(
            overall_metrics(paths, args.candidate, args.split),
            overall_metrics(paths, reference, args.split),
        )
        print(comparison_markdown(args.candidate, reference, c))
        return 0 if c["ok"] else 1
    elif args.cmd == "promote":
        try:
            r = promote(paths, args.model, args.split, args.justification)
        except PromotionRefused as e:
            print(str(e))
            print(comparison_markdown(args.model, "champion", e.comparison))
            return 1
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        current = champion(make_client(paths))
        print("aucun champion" if current is None else json.dumps(dict(current.tags), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
