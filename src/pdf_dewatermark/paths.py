"""运行时路径（开发 / 打包通用）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # src/pdf_dewatermark/paths.py → parents[2] = project root
    here = Path(__file__).resolve()
    return here.parents[2]


def ensure_runtime_dirs() -> None:
    root = get_app_root()
    for name in ("data", "output", "logs"):
        (root / name).mkdir(parents=True, exist_ok=True)


APP_ROOT = get_app_root()
DATA_DIR = APP_ROOT / "data"
OUTPUT_DIR = APP_ROOT / "output"
LOGS_DIR = APP_ROOT / "logs"


def default_output_path(source: Path | str, suffix: str = "去水印") -> Path:
    src = Path(source)
    out_dir = OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{src.stem}_{suffix}{src.suffix or '.pdf'}"
