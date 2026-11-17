"""Command-line entry point for the data pipeline stages.

Usage::

    python -m darijacare.data.cli {ingest,validate,normalize,split,eda,all}
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from typing import Any

from darijacare.config import Paths, get_paths, load_data_config

Stage = Callable[[Paths, dict[str, Any]], Any]


def _stages() -> dict[str, Stage]:
    from darijacare.data.eda import run_eda
    from darijacare.data.ingest import ingest
    from darijacare.data.normalize import run_normalize
    from darijacare.data.split import run_split
    from darijacare.data.validate import run_validation

    return {
        "ingest": ingest,
        "validate": run_validation,
        "normalize": run_normalize,
        "split": run_split,
        "eda": run_eda,
    }


def main(argv: list[str] | None = None) -> int:
    """Run one stage (or ``all`` in order). Returns a process exit code."""
    stages = _stages()
    parser = argparse.ArgumentParser(prog="darijacare-data", description=__doc__)
    parser.add_argument("stage", choices=[*stages, "all"])
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")

    paths = get_paths()
    config = load_data_config(paths)
    names = list(stages) if args.stage == "all" else [args.stage]
    for name in names:
        logging.getLogger("darijacare").info("=== étape %s ===", name)
        try:
            stages[name](paths, config)
        except Exception as exc:
            logging.getLogger("darijacare").error("Échec de l'étape %s : %s", name, exc)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
