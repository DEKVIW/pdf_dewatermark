"""区域遮盖：矢量导出应保留原页内容与清晰度（不整页光栅化）。"""

from __future__ import annotations

from pathlib import Path

import fitz
import numpy as np

from pdf_dewatermark.models import RegionRect
from pdf_dewatermark.processor import (
    PIPELINE_STEP_REGION,
    process_pdf_pipeline,
    process_pdf_regions,
)


def _make_text_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.draw_rect(page.rect, color=(1, 1, 1), fill=(1, 1, 1))
    # 正文文字：矢量路径应仍可提取
    page.insert_text((40, 80), "KEEP_TEXT", fontsize=18, color=(0, 0, 0))
    # 页眉区域一块灰（将被白矩形盖住）
    page.draw_rect(fitz.Rect(20, 10, 280, 40), color=None, fill=(0.7, 0.7, 0.7))
    doc.save(path)
    doc.close()


def test_region_export_is_vector_keeps_text(tmp_path: Path):
    src = tmp_path / "src.pdf"
    out = tmp_path / "out.pdf"
    _make_text_pdf(src)

    regions = [
        RegionRect(page_index=0, x0=20, y0=10, x1=280, y1=40, color=(255, 255, 255)),
    ]
    process_pdf_regions(src, out, regions)

    doc = fitz.open(out)
    try:
        assert len(doc) == 1
        text = doc[0].get_text()
        assert "KEEP_TEXT" in text, "矢量导出应保留可选文字；若整页光栅化则提取为空"
        # 页眉矩形区域渲染后应接近白色
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
        # 取样页眉中心附近
        patch = arr[15:35, 100:200]
        assert float(patch.mean()) > 240, f"遮盖区应接近白，实际 mean={patch.mean():.1f}"
    finally:
        doc.close()


def test_pipeline_region_only_uses_vector(tmp_path: Path):
    src = tmp_path / "src.pdf"
    out = tmp_path / "pipe.pdf"
    _make_text_pdf(src)
    regions = [
        RegionRect(page_index=0, x0=20, y0=10, x1=280, y1=40, color=(255, 255, 255)),
    ]
    process_pdf_pipeline(src, out, [PIPELINE_STEP_REGION], regions=regions)
    doc = fitz.open(out)
    try:
        assert "KEEP_TEXT" in doc[0].get_text()
    finally:
        doc.close()


def test_region_page_subset(tmp_path: Path):
    src = tmp_path / "multi.pdf"
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page(width=100, height=100)
        page.insert_text((10, 50), f"P{i}", fontsize=12)
    doc.save(src)
    doc.close()

    out = tmp_path / "sub.pdf"
    regions = [RegionRect(1, 0, 0, 30, 20, color=(255, 0, 0))]
    process_pdf_regions(src, out, regions, page_indices=[1])
    doc = fitz.open(out)
    try:
        assert len(doc) == 1
        assert "P1" in doc[0].get_text()
    finally:
        doc.close()
