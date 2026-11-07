"""Configuration loading for DataLens."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../DataLens (src/datalens/config.py)
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load the YAML configuration file.

    Raises FileNotFoundError with a clear message if the file is missing, and
    ValueError if the file is empty or not a mapping.
    """
    cfg_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not cfg_path.is_file():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict):
        raise ValueError(f"Config file {cfg_path} must contain a YAML mapping.")
    return cfg


def resolve_path(relative: str | Path) -> Path:
    """Resolve a config path (relative to the project root) to an absolute Path."""
    p = Path(relative)
    return p if p.is_absolute() else PROJECT_ROOT / p
