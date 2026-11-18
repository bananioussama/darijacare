"""Command-line entry point for the knowledge base and RAG.

Usage::

    python -m darijacare.rag.cli generate-kb [--force]   # kb/_source/*.yaml -> kb/**/*.md
    python -m darijacare.rag.cli validate-kb
    python -m darijacare.rag.cli neighbours               # confusion neighbours (no test data)
    python -m darijacare.rag.cli index
    python -m darijacare.rag.cli search "ma kaynach connexion" --intent home_outage
    python -m darijacare.rag.cli evaluate --split val
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from darijacare.config import Paths, get_paths, load_yaml

log = logging.getLogger("darijacare.rag")


def load_rag_config(paths: Paths) -> dict[str, Any]:
    return load_yaml(paths.configs / "rag.yaml")


def make_embedder(paths: Paths, cfg: dict[str, Any], device: str | None = None) -> Any:
    from darijacare.io import sha256_file
    from darijacare.rag.index import BGEM3Embedder

    e = cfg["embedder"]
    model_dir = paths.root / e["model_path"]
    weights = model_dir / "pytorch_model.bin"
    if not weights.exists():
        raise SystemExit(f"Poids BGE-M3 absents : {weights}")
    if sha256_file(weights) != e["weights_sha256"]:
        raise SystemExit("Empreinte des poids BGE-M3 inattendue")
    return BGEM3Embedder(model_dir, e["batch_size"], e["max_length"], e["use_fp16"], device)


def make_retriever(
    paths: Paths, cfg: dict[str, Any], embedder: Any, qdrant_url: str | None = None
) -> Any:
    """Retriever over the Qdrant server (``qdrant_url`` or ``QDRANT_URL``) or the local store."""
    from darijacare.rag.index import get_client
    from darijacare.rag.retrieve import Retriever, load_neighbours

    client = get_client(cfg["qdrant"], paths.root, qdrant_url)
    nb = load_neighbours(paths.root / cfg["retrieval"]["neighbours_file"])
    return Retriever(client, cfg["qdrant"]["collection"], embedder, cfg["retrieval"], nb)


def compute_neighbours(
    paths: Paths, model: str = "v3", rounds: tuple[int, ...] = (4, 6), k: int = 3
) -> dict[str, Any]:
    """Top-k confused intents from ``model``'s validation errors on ``rounds`` only.

    The official test set is never used, so retrieval can be evaluated on it without
    leakage. For v3, rounds 4 and 6 were never seen in training (Phase 2 analysis).
    """
    from darijacare.data.taxonomy import load_taxonomy
    from darijacare.io import read_jsonl
    from darijacare.nlu.metrics import confusion_frame, top_confusions

    gold = read_jsonl(paths.processed / "val.jsonl")
    pred = read_jsonl(paths.reports / "nlu" / model / "val" / "predictions.jsonl")
    keep = gold["round"].isin(rounds).to_numpy()
    intents = load_taxonomy(paths.raw / "telecom_taxonomy.json").intents
    cm = confusion_frame(gold.loc[keep, "intent"], pred.loc[keep, "intent"], intents)
    return top_confusions(cm, k)


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the requested command."""
    parser = argparse.ArgumentParser(
        prog="darijacare-rag",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate-kb")
    g.add_argument("--force", action="store_true")
    sub.add_parser("validate-kb")
    sub.add_parser("neighbours")
    ix = sub.add_parser("index")
    ix.add_argument("--device", default=None)
    se = sub.add_parser("search")
    se.add_argument("query")
    se.add_argument("--intent", default=None)
    se.add_argument("--no-filter", action="store_true")
    ev = sub.add_parser("evaluate")
    ev.add_argument("--split", default="val", choices=["val", "test"])
    ev.add_argument("--nlu-model", default="v5")
    ev.add_argument(
        "--rounds",
        type=int,
        nargs="*",
        default=None,
        help="Évaluer seulement ces rondes (ex. 4 6 : jamais vues par v3)",
    )
    ev.add_argument("--device", default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", force=True
    )
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    paths = get_paths()
    cfg = load_rag_config(paths)
    kb_dir = paths.root / cfg["kb_dir"]

    if args.cmd == "generate-kb":
        from darijacare.rag.kb import generate_from_source

        written = generate_from_source(kb_dir, force=args.force)
        log.info("%d fiches écrites (fiches existantes conservées sauf --force)", len(written))
    elif args.cmd == "validate-kb":
        from darijacare.data.taxonomy import load_taxonomy
        from darijacare.rag.kb import load_kb, validate_kb

        problems = validate_kb(load_kb(kb_dir), load_taxonomy(paths.raw / "telecom_taxonomy.json"))
        for p in problems:
            log.error(p)
        log.info("%d problème(s)", len(problems))
        return 1 if problems else 0
    elif args.cmd == "neighbours":
        from darijacare.io import write_json

        nb = compute_neighbours(paths)
        out = paths.root / cfg["retrieval"]["neighbours_file"]
        write_json(nb, out)
        log.info("Voisines écrites dans %s", out)
    elif args.cmd == "index":
        from darijacare.rag.index import chunk_fiches, get_client, index_chunks
        from darijacare.rag.kb import load_kb

        embedder = make_embedder(paths, cfg, args.device)
        client = get_client(cfg["qdrant"], paths.root)
        stats = index_chunks(
            client, cfg["qdrant"]["collection"], chunk_fiches(load_kb(kb_dir)), embedder
        )
        log.info("Index : %s", stats)
    elif args.cmd == "search":
        embedder = make_embedder(paths, cfg)
        retriever = make_retriever(paths, cfg, embedder)
        res = retriever.search(args.query, args.intent, use_filter=not args.no_filter)
        print(
            json.dumps(
                {
                    "candidats": res.candidates,
                    "fiable": res.reliable,
                    "fiches": [
                        {
                            "id": f.fiche_id,
                            "score": round(f.score, 4),
                            "dense": round(f.best_dense, 3),
                        }
                        for f in res.fiches
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.cmd == "evaluate":
        from darijacare.rag.evaluate import run_rag_evaluation

        embedder = make_embedder(paths, cfg, args.device)
        retriever = make_retriever(paths, cfg, embedder)
        report = run_rag_evaluation(paths, retriever, args.split, args.nlu_model, args.rounds)
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
