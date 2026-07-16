"""页面渲染。"""

from __future__ import annotations

from typing import Optional, Tuple

import fitz
import numpy as np
from PIL import Image


def dpi_matrix(dpi: float) -> fitz.Matrix:
    zoom = float(dpi) / 72.0
    return fitz.Matrix(zoom, zoom)


def mupdf_store_shrink(percent: int = 100) -> None:
    """释放 MuPDF 内部缓存。percent=100 清空 store，不改变渲染结果。"""
    try:
        fitz.TOOLS.store_shrink(int(percent))
    except Exception:
        pass


def estimate_page_raster_dpi(page: fitz.Page) -> Optional[float]:
    """
    估计页面主位图的等效 DPI。

    扫描/伪扫描页通常是整页一张大图；返回其宽高相对页面尺寸的等效 DPI。
    矢量页或无可用图时返回 None。
    """
    rect = page.rect
    if rect.width <= 1e-3 or rect.height <= 1e-3:
        return None
    try:
        images = page.get_images(full=True)
    except Exception:
        return None
    if not images:
        return None

    best_w, best_h, best_area = 0, 0, 0
    for img in images:
        # (xref, smask, width, height, bpc, colorspace, alt, name, filter, ...)
        try:
            iw, ih = int(img[2]), int(img[3])
        except (IndexError, TypeError, ValueError):
            continue
        area = iw * ih
        if area > best_area:
            best_area = area
            best_w, best_h = iw, ih
    if best_w < 32 or best_h < 32:
        return None

    dpi_x = best_w / (rect.width / 72.0)
    dpi_y = best_h / (rect.height / 72.0)
    native = (dpi_x + dpi_y) / 2.0
    # 异常值保护
    if native < 36 or native > 1200:
        return None
    return float(native)


def resolve_export_dpi(
    page: fitz.Page,
    requested_dpi: float,
    *,
    avoid_upsample: bool = True,
) -> float:
    """
    导出用 DPI：可按用户请求；扫描页可选不超过原图等效 DPI。

    不抬高超过原图 → 不引入插值虚边，且体积不无谓膨胀。
    用户请求更低 DPI 时仍尊重（小体积预设）。
    """
    req = max(36.0, float(requested_dpi))
    if not avoid_upsample:
        return req
    native = estimate_page_raster_dpi(page)
    if native is None:
        return req
    # 略留 2% 余量，避免取整差 1px
    return min(req, native * 1.02)


def page_to_pixmap(page: fitz.Page, dpi: float = 200, grayscale: bool = False) -> fitz.Pixmap:
    matrix = dpi_matrix(dpi)
    if grayscale:
        return page.get_pixmap(matrix=matrix, colorspace=fitz.csGRAY, alpha=False)
    return page.get_pixmap(matrix=matrix, alpha=False)


def page_to_image(page: fitz.Page, dpi: float = 200, grayscale: bool = False) -> Image.Image:
    """
    渲染页面为 PIL Image。

    使用 samples_mv 避免额外 bytes 拷贝；读完后释放 Pixmap。
    像素内容与原先 samples 路径一致。
    """
    pix = page_to_pixmap(page, dpi=dpi, grayscale=grayscale)
    try:
        samples = pix.samples_mv if hasattr(pix, "samples_mv") else pix.samples
        if pix.n == 1:
            img = Image.frombytes("L", (pix.width, pix.height), samples).convert("RGB")
        else:
            img = Image.frombytes("RGB", (pix.width, pix.height), samples)
        return img
    finally:
        # 尽快释放底层缓冲，降低大文档导出时的峰值内存
        pix = None  # noqa: F841


def page_to_numpy(page: fitz.Page, dpi: float = 200, grayscale: bool = False) -> np.ndarray:
    return np.array(page_to_image(page, dpi=dpi, grayscale=grayscale))


def page_size(page: fitz.Page) -> Tuple[float, float]:
    r = page.rect
    return r.width, r.height
