"""Command-line entry point for the NLU stages.

Usage::

    python -m darijacare.nlu.cli baseline
    python -m darijacare.nlu.cli evaluate --model v5 --split test
    python -m darijacare.nlu.cli calibrate --model v5
    python -m darijacare.nlu.cli predict --model v5 "chargit 20dh w ma wslatni walo"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from darijacare.config import Paths, get_paths, load_yaml
from darijacare.io import sha256_file

log = logging.getLogger("darijacare.nlu")


def load_train_config(paths: Paths) -> dict[str, Any]:
    """Load ``configs/train.yaml``."""
    return load_yaml(paths.configs / "train.yaml")


def model_spec(paths: Paths, cfg: dict[str, Any], name: str) -> dict[str, Any]:
    """Return the published-model entry and check its weights' SHA-256."""
    try:
        spec = dict(cfg["published_models"][name])
    except KeyError as exc:
        raise SystemExit(f"Modèle inconnu : {name}") from exc
    path = paths.root / spec["path"]
    weights = path / "model.safetensors"
    if not weights.exists():
        raise SystemExit(f"Poids absents : {weights}")
    digest = sha256_file(weights)
    if digest != spec["weights_sha256"]:
        raise SystemExit(f"Empreinte des poids inattendue pour {name} : {digest}")
    spec["abs_path"] = path
    return spec


def _service(paths: Paths, cfg: dict[str, Any], name: str, device: str | None) -> Any:
    from darijacare.nlu.service import LayaTelecomModel

    spec = model_spec(paths, cfg, name)
    return LayaTelecomModel(
        spec["abs_path"], device=device, model_version=f"{name}@{spec['revision'][:8]}"
    )


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the requested NLU stage."""
    parser = argparse.ArgumentParser(
        prog="darijacare-nlu",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("baseline")
    ev = sub.add_parser("evaluate")
    ev.add_argument(
        "--model", default="v5", help="Modèle publié (v5, v3) ou nom libre avec --checkpoint"
    )
    ev.add_argument(
        "--checkpoint",
        default=None,
        help="Dossier d'un checkpoint laya (ex. models/retrain/seed42/best)",
    )
    ev.add_argument("--split", default="test", choices=["val", "test"])
    ev.add_argument("--device", default=None)
    ca = sub.add_parser("calibrate")
    ca.add_argument("--model", default="v5")
    ca.add_argument(
        "--fit-rounds",
        type=int,
        nargs="*",
        default=None,
        help="Ajuster seulement sur ces rondes (ex. 4 6 : jamais vues par v3)",
    )
    pr = sub.add_parser("predict")
    pr.add_argument("--model", default="v5")
    pr.add_argument("--device", default=None)
    pr.add_argument("texts", nargs="+")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", force=True
    )
    logging.getLogger("alembic").setLevel(logging.WARNING)
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    paths = get_paths()
    cfg = load_train_config(paths)

    if args.cmd == "baseline":
        from darijacare.nlu.baseline import run_baseline

        run_baseline(paths, cfg)
    elif args.cmd == "evaluate":
        from darijacare.data.taxonomy import load_taxonomy
        from darijacare.nlu import tracking
        from darijacare.nlu.evaluate import evaluate_model

        if args.checkpoint:
            from darijacare.nlu.service import LayaTelecomModel

            ckpt = paths.root / args.checkpoint
            spec = {
                "revision": "local",
                "trained_on": str(ckpt),
                "published": cfg["published_models"]["v5"]["published"],
            }
            service = LayaTelecomModel(ckpt, device=args.device, model_version=args.model)
        else:
            spec = model_spec(paths, cfg, args.model)
            service = _service(paths, cfg, args.model, args.device)
        intents = load_taxonomy(paths.raw / "telecom_taxonomy.json").intents
        published = spec["published"] if args.split == "test" else None
        params = {
            "model": args.model,
            "revision": spec["revision"],
            "split": args.split,
            "trained_on": spec["trained_on"],
        }
        with tracking.start_run(f"eval_{args.model}_{args.split}", params, paths) as run:
            report = evaluate_model(
                service,
                paths,
                args.model,
                args.split,
                intents,
                published,
                cfg["reproduction_tolerance_points"],
            )
            run.log_metrics({f"{args.split}_{k}": v for k, v in report["overall"].items()})
            run.log_artifact(paths.reports / "nlu" / args.model / args.split / "metrics.json")
        o = report["overall"]
        log.info(
            "Intention bout en bout %.1f %% ; reproduit : %s",
            100 * o["intent_end_to_end"],
            report.get("reproduced"),
        )
    elif args.cmd == "calibrate":
        from darijacare.nlu.calibrate import run_calibration

        ccfg = {**cfg["calibration"], "processed_dir": str(paths.processed)}
        if args.fit_rounds:
            ccfg["fit_filter"] = {"round": args.fit_rounds}
        rep = run_calibration(paths.reports / "nlu" / args.model, ccfg)
        print(json.dumps({k: rep[k] for k in ("temperatures", "thresholds")}, indent=2))
    elif args.cmd == "predict":
        service = _service(paths, cfg, args.model, args.device)
        for text in args.texts:
            r = service.predict(text).to_dict()
            r.pop("probabilities")
            print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
