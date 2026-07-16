"""区域遮盖：在图像坐标下填充矩形。"""

from __future__ import annotations

from typing import Iterable, Sequence, Tuple

import numpy as np

RGB = Tuple[int, int, int]
RectPx = Tuple[int, int, int, int]  # x0,y0,x1,y1


def fill_rects_array(
    img: np.ndarray,
    rects: Sequence[RectPx],
    color: RGB = (255, 255, 255),
) -> np.ndarray:
    out = img[..., :3].copy()
    h, w = out.shape[:2]
    c = np.array(color, dtype=np.uint8)
    for x0, y0, x1, y1 in rects:
        xa, xb = max(0, min(x0, x1)), min(w, max(x0, x1))
        ya, yb = max(0, min(y0, y1)), min(h, max(y0, y1))
        if xa < xb and ya < yb:
            out[ya:yb, xa:xb] = c
    return out


def pdf_rect_to_pixel(
    rect: Tuple[float, float, float, float],
    page_width: float,
    page_height: float,
    pix_width: int,
    pix_height: int,
) -> RectPx:
    """将 PDF 点坐标矩形映射到渲染像素坐标。"""
    x0, y0, x1, y1 = rect
    sx = pix_width / page_width if page_width else 1.0
    sy = pix_height / page_height if page_height else 1.0
    return (
        int(round(min(x0, x1) * sx)),
        int(round(min(y0, y1) * sy)),
        int(round(max(x0, x1) * sx)),
        int(round(max(y0, y1) * sy)),
    )
