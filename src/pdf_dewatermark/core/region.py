"""区域遮盖：矢量 PDF 矩形 + 位图预览/组合用像素填充。"""

from __future__ import annotations

from typing import Any, Sequence, Tuple

import numpy as np

RGB = Tuple[int, int, int]
RectPx = Tuple[int, int, int, int]  # x0,y0,x1,y1
PdfRect = Tuple[float, float, float, float]  # x0,y0,x1,y1 in PDF points


def fill_rects_array(
    img: np.ndarray,
    rects: Sequence[RectPx],
    color: RGB = (255, 255, 255),
) -> np.ndarray:
    """在已渲染位图上填充矩形（预览 / 与选色·灰度组合时用）。"""
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


def rgb_to_pdf_color(color: RGB) -> Tuple[float, float, float]:
    """0–255 RGB → MuPDF 0–1 浮点色。"""
    r, g, b = color
    return (max(0, min(255, int(r))) / 255.0, max(0, min(255, int(g))) / 255.0, max(0, min(255, int(b))) / 255.0)


def draw_filled_rects_on_page(
    page: Any,
    rects: Sequence[Tuple[PdfRect, RGB]],
) -> int:
    """
    在 PDF 页面上绘制矢量填充矩形（不光栅化整页）。

    rects: ((x0,y0,x1,y1), rgb) 列表，坐标为 PDF 点。
    返回实际绘制数量。
    """
    import fitz

    n = 0
    for rect, color in rects:
        x0, y0, x1, y1 = rect
        xa, xb = float(min(x0, x1)), float(max(x0, x1))
        ya, yb = float(min(y0, y1)), float(max(y0, y1))
        if xb <= xa or yb <= ya:
            continue
        fill = rgb_to_pdf_color(color)
        page.draw_rect(fitz.Rect(xa, ya, xb, yb), color=fill, fill=fill, width=0)
        n += 1
    return n
