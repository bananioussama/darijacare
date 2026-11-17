"""Chemins du projet et chargement des fichiers de configuration YAML."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def _find_root() -> Path:
    """Return the repository root (the folder containing ``pyproject.toml``).

    ``DARIJACARE_ROOT`` overrides the lookup (useful in Docker or tests).
    """
    env = os.environ.get("DARIJACARE_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for parent in [Path.cwd(), *here.parents]:
        if (parent / "pyproject.toml").exists() and (parent / "src" / "darijacare").exists():
            return parent
    return here.parents[2]


@dataclass(frozen=True)
class Paths:
    """Canonical locations of data and reports, relative to the repository root."""

    root: Path

    @property
    def configs(self) -> Path:
        return self.root / "configs"

    @property
    def raw(self) -> Path:
        """Bronze zone: immutable copy of the source files."""
        return self.root / "data" / "raw"

    @property
    def interim(self) -> Path:
        """Silver zone: validated and normalised data."""
        return self.root / "data" / "interim"

    @property
    def processed(self) -> Path:
        """Gold zone: train / validation / test splits."""
        return self.root / "data" / "processed"

    @property
    def reports(self) -> Path:
        return self.root / "reports"


def get_paths(root: Path | None = None) -> Paths:
    """Build :class:`Paths` for ``root`` (auto-detected when ``None``)."""
    return Paths(root=(root or _find_root()).resolve())


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping from ``path``."""
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} ne contient pas un dictionnaire YAML")
    return data


def load_data_config(paths: Paths | None = None) -> dict[str, Any]:
    """Load ``configs/data.yaml``."""
    p = paths or get_paths()
    return load_yaml(p.configs / "data.yaml")
