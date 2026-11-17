"""Compare the data-output hashes of two ``dvc.lock`` files.

Used by CI to check that ``dvc repro`` on a fresh machine rebuilds exactly the
same data (bronze, silver and gold zones). Report folders are excluded because
PNG rendering may differ slightly between operating systems.

Usage::

    python tools/check_lock.py reference.lock dvc.lock
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


def data_hashes(lock_path: Path, prefix: str = "data/") -> dict[str, str]:
    """Return ``{output path: md5}`` for every stage output under ``prefix``."""
    lock: dict[str, Any] = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    hashes: dict[str, str] = {}
    for stage in lock.get("stages", {}).values():
        for out in stage.get("outs", []):
            if out["path"].startswith(prefix):
                hashes[out["path"]] = out["md5"]
    return hashes


def main(argv: list[str]) -> int:
    """Exit 0 when both lock files record the same data hashes."""
    if len(argv) != 2:
        print(__doc__)
        return 2
    ref, new = (data_hashes(Path(p)) for p in argv)
    if not ref:
        print("Aucune sortie de données dans le fichier de référence.")
        return 1
    diff = {
        k: (ref.get(k), new.get(k)) for k in ref.keys() | new.keys() if ref.get(k) != new.get(k)
    }
    for path, (a, b) in sorted(diff.items()):
        print(f"DIFFÉRENT {path}: {a} -> {b}")
    if diff:
        return 1
    print(f"OK : {len(ref)} sorties de données identiques.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
