"""PDF 文档打开封装。"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import fitz


def open_document(path: Union[str, Path]) -> fitz.Document:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"找不到 PDF: {p}")
    return fitz.open(p)
