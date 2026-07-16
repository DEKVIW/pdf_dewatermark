"""业务编排：预览单页、导出 PDF、灰度、区域遮盖。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Sequence, Union

import fitz
from PIL import Image

from .core.grayscale import pixmap_to_gray_rgb
from .core.region import fill_rects_array, pdf_rect_to_pixel
from .core.remove import remove_watermark_image
from .models import ColorMethod, GrayscaleParams, RegionRect, RemoveParams
from .pdf.document import open_document
from .pdf.export import image_to_pdf_page
from .pdf.render import (
    mupdf_store_shrink,
    page_size,
    page_to_image,
    resolve_export_dpi,
)

ProgressCb = Optional[Callable[[int, int, str], None]]
CancelCb = Optional[Callable[[], bool]]

# 每处理 N 页收缩一次 MuPDF store，压峰值内存；不影响像素结果
_STORE_SHRINK_EVERY = 4


def _method_value(params: RemoveParams) -> str:
    m = params.method
    return m.value if hasattr(m, "value") else str(m)


def effective_render_dpi(params: RemoveParams) -> float:
    """color_pick 用 dpi；threshold 用 resolution_factor × 72。"""
    if _method_value(params) == ColorMethod.THRESHOLD.value:
        return float(params.resolution_factor) * 72.0
    return float(params.dpi)


def preview_page(
    doc: fitz.Document,
    page_index: int,
    params: RemoveParams,
    display_dpi: Optional[float] = None,
) -> tuple[Image.Image, Image.Image]:
    """渲染并处理单页。默认用导出 DPI；可指定更低 display_dpi 加速预览。"""
    page = doc[page_index]
    dpi = display_dpi if display_dpi is not None else effective_render_dpi(params)
    original = page_to_image(page, dpi=dpi)
    processed, _ = remove_watermark_image(original, params)
    return original, processed


def _export_page_cleanup(page_i: int) -> None:
    """导出循环内回收 MuPDF 缓存，结果不变。"""
    if page_i > 0 and page_i % _STORE_SHRINK_EVERY == 0:
        mupdf_store_shrink(100)


def process_pdf_remove(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    params: RemoveParams,
    page_indices: Optional[Sequence[int]] = None,
    progress: ProgressCb = None,
    should_cancel: CancelCb = None,
) -> Path:
    """按颜色组去水印并写出 PDF。"""
    src = Path(input_path)
    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    doc = open_document(src)
    out = fitz.open()
    try:
        indices = list(page_indices) if page_indices is not None else list(range(len(doc)))
        total = len(indices)
        fmt = params.image_format.value if hasattr(params.image_format, "value") else str(params.image_format)
        dpi = effective_render_dpi(params)

        avoid_up = bool(getattr(params, "avoid_upsample", True))
        for i, idx in enumerate(indices):
            if should_cancel and should_cancel():
                raise RuntimeError("已取消")
            page = doc[idx]
            w, h = page_size(page)
            page_dpi = resolve_export_dpi(page, dpi, avoid_upsample=avoid_up)
            if progress:
                progress(
                    i,
                    total,
                    f"处理第 {idx + 1} 页（{page_dpi:.0f} DPI · {fmt.upper()}）",
                )
            original = page_to_image(page, dpi=page_dpi)
            # 尽早放下 page 引用，便于 MuPDF 释放页面级资源
            page = None  # noqa: F841
            processed, _ = remove_watermark_image(original, params)
            del original
            image_to_pdf_page(
                out,
                processed,
                w,
                h,
                fmt=fmt,
                jpeg_quality=int(getattr(params, "jpeg_quality", 92)),
            )
            del processed
            _export_page_cleanup(i + 1)
        if progress:
            progress(total, total, "正在保存…")
        out.save(dst, garbage=4, deflate=True, clean=True)
    finally:
        out.close()
        doc.close()
        mupdf_store_shrink(100)
    return dst


def process_pdf_grayscale(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    params: Optional[GrayscaleParams] = None,
    progress: ProgressCb = None,
    should_cancel: CancelCb = None,
) -> Path:
    params = params or GrayscaleParams()
    src = Path(input_path)
    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    doc = open_document(src)
    out = fitz.open()
    try:
        total = len(doc)
        for i in range(total):
            if should_cancel and should_cancel():
                raise RuntimeError("已取消")
            if progress:
                progress(i, total, f"灰度第 {i + 1} 页")
            page = doc[i]
            w, h = page_size(page)
            page_dpi = resolve_export_dpi(page, float(params.dpi), avoid_upsample=True)
            img = page_to_image(page, dpi=page_dpi, grayscale=True)
            page = None  # noqa: F841
            if img.mode != "RGB":
                img = pixmap_to_gray_rgb(img)
            # 灰度页用 JPEG 体积更小，观感通常足够
            image_to_pdf_page(out, img, w, h, fmt="jpeg", jpeg_quality=90)
            del img
            _export_page_cleanup(i + 1)
        if progress:
            progress(total, total, "正在保存…")
        out.save(dst, garbage=4, deflate=True, clean=True)
    finally:
        out.close()
        doc.close()
        mupdf_store_shrink(100)
    return dst


def process_pdf_regions(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    regions: Sequence[RegionRect],
    dpi: int = 200,
    page_indices: Optional[Sequence[int]] = None,
    progress: ProgressCb = None,
    should_cancel: CancelCb = None,
) -> Path:
    src = Path(input_path)
    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    by_page: dict[int, List[RegionRect]] = {}
    for r in regions:
        by_page.setdefault(r.page_index, []).append(r)

    doc = open_document(src)
    out = fitz.open()
    try:
        indices = list(page_indices) if page_indices is not None else list(range(len(doc)))
        total = len(indices)
        for i, idx in enumerate(indices):
            if should_cancel and should_cancel():
                raise RuntimeError("已取消")
            if progress:
                progress(i, total, f"遮盖第 {idx + 1} 页")
            page = doc[idx]
            w, h = page_size(page)
            page_dpi = resolve_export_dpi(page, float(dpi), avoid_upsample=True)
            img = page_to_image(page, dpi=page_dpi)
            page = None  # noqa: F841
            arr = __import__("numpy").array(img)
            rects_px = []
            color = (255, 255, 255)
            for r in by_page.get(idx, []):
                color = r.color
                rects_px.append(
                    pdf_rect_to_pixel(r.normalized(), w, h, img.width, img.height)
                )
            if rects_px:
                arr = fill_rects_array(arr, rects_px, color)
                img = Image.fromarray(arr)
            del arr
            image_to_pdf_page(out, img, w, h, fmt="jpeg", jpeg_quality=92)
            del img
            _export_page_cleanup(i + 1)
        if progress:
            progress(total, total, "正在保存…")
        out.save(dst, garbage=4, deflate=True, clean=True)
    finally:
        out.close()
        doc.close()
        mupdf_store_shrink(100)
    return dst


def process_batch_remove(
    files: Sequence[Union[str, Path]],
    output_dir: Union[str, Path],
    params: RemoveParams,
    progress: ProgressCb = None,
    should_cancel: CancelCb = None,
) -> List[Path]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: List[Path] = []
    total = len(files)
    for i, f in enumerate(files):
        if should_cancel and should_cancel():
            raise RuntimeError("已取消")
        src = Path(f)
        if progress:
            progress(i, total, f"批量: {src.name}")
        dst = out_dir / f"{src.stem}_选色替换.pdf"
        process_pdf_remove(src, dst, params, progress=None, should_cancel=should_cancel)
        results.append(dst)
    if progress:
        progress(total, total, "批量完成")
    return results


# 组合处理合法步骤 id（顺序由调用方 steps 列表决定）
PIPELINE_STEP_GRAY = "grayscale"
PIPELINE_STEP_REMOVE = "remove"
PIPELINE_STEP_REGION = "region"
PIPELINE_STEPS_ALL = (
    PIPELINE_STEP_GRAY,
    PIPELINE_STEP_REMOVE,
    PIPELINE_STEP_REGION,
)


def _apply_regions_to_image(
    img: Image.Image,
    page_index: int,
    page_w: float,
    page_h: float,
    regions: Sequence[RegionRect],
) -> Image.Image:
    """在已渲染位图上应用属于该页的矩形遮盖。"""
    rects_px = []
    color = (255, 255, 255)
    for r in regions:
        if int(r.page_index) != int(page_index):
            continue
        color = r.color
        rects_px.append(
            pdf_rect_to_pixel(r.normalized(), page_w, page_h, img.width, img.height)
        )
    if not rects_px:
        return img
    import numpy as np

    arr = fill_rects_array(np.array(img), rects_px, color)
    return Image.fromarray(arr)


def process_pdf_pipeline(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    steps: Sequence[str],
    *,
    remove_params: Optional[RemoveParams] = None,
    regions: Optional[Sequence[RegionRect]] = None,
    gray_dpi: Optional[int] = None,
    progress: ProgressCb = None,
    should_cancel: CancelCb = None,
) -> Path:
    """
    组合处理：每页只渲染一次，按 steps 顺序在内存中串行处理，再导出一次。

    steps 元素为 grayscale | remove | region（可排序、可子集）。
    单独模块导出仍走 process_pdf_remove / regions / grayscale，互不影响。
    """
    ordered = [str(s).strip() for s in steps if str(s).strip()]
    if not ordered:
        raise ValueError("请至少选择一个处理步骤")
    unknown = [s for s in ordered if s not in PIPELINE_STEPS_ALL]
    if unknown:
        raise ValueError(f"未知步骤: {unknown}")

    need_remove = PIPELINE_STEP_REMOVE in ordered
    need_region = PIPELINE_STEP_REGION in ordered
    need_gray = PIPELINE_STEP_GRAY in ordered

    if need_remove:
        if remove_params is None or not remove_params.resolved_pairs():
            raise ValueError("已启用选色替换，但尚未配置颜色组（请先到选色页取样）")
    if need_region:
        regions = list(regions or [])
        if not regions:
            raise ValueError("已启用区域遮盖，但尚未绘制矩形（请先到区域页绘制）")
    else:
        regions = list(regions or [])

    # 导出编码：有选色参数则跟随其预设；否则均衡默认
    if remove_params is not None:
        fmt = (
            remove_params.image_format.value
            if hasattr(remove_params.image_format, "value")
            else str(remove_params.image_format)
        )
        jpeg_q = int(getattr(remove_params, "jpeg_quality", 92))
        avoid_up = bool(getattr(remove_params, "avoid_upsample", True))
        base_dpi = float(effective_render_dpi(remove_params))
    else:
        fmt = "jpeg"
        jpeg_q = 92
        avoid_up = True
        base_dpi = float(gray_dpi or 200)

    src = Path(input_path)
    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    doc = open_document(src)
    out = fitz.open()
    try:
        total = len(doc)
        for i in range(total):
            if should_cancel and should_cancel():
                raise RuntimeError("已取消")
            page = doc[i]
            w, h = page_size(page)
            page_dpi = resolve_export_dpi(page, base_dpi, avoid_upsample=avoid_up)
            step_names = "→".join(
                {"grayscale": "灰度", "remove": "选色", "region": "区域"}.get(s, s)
                for s in ordered
            )
            if progress:
                progress(i, total, f"组合第 {i + 1}/{total} 页（{page_dpi:.0f} DPI · {step_names}）")

            img = page_to_image(page, dpi=page_dpi)
            page = None  # noqa: F841

            for step in ordered:
                if step == PIPELINE_STEP_GRAY:
                    img = pixmap_to_gray_rgb(img)
                elif step == PIPELINE_STEP_REMOVE:
                    assert remove_params is not None
                    img, _ = remove_watermark_image(img, remove_params)
                elif step == PIPELINE_STEP_REGION:
                    img = _apply_regions_to_image(img, i, w, h, regions)

            image_to_pdf_page(out, img, w, h, fmt=fmt, jpeg_quality=jpeg_q)
            del img
            _export_page_cleanup(i + 1)

        if progress:
            progress(total, total, "正在保存…")
        out.save(dst, garbage=4, deflate=True, clean=True)
    finally:
        out.close()
        doc.close()
        mupdf_store_shrink(100)
    return dst
