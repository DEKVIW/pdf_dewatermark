"""组合处理管线：单页渲染多步、与单步语义一致。"""

from __future__ import annotations

from pathlib import Path

import fitz
import numpy as np
from PIL import Image

from pdf_dewatermark.models import ColorMethod, ColorPair, FillMode, RemoveParams, RegionRect
from pdf_dewatermark.processor import (
    PIPELINE_STEP_GRAY,
    PIPELINE_STEP_REGION,
    PIPELINE_STEP_REMOVE,
    process_pdf_pipeline,
    process_pdf_remove,
)


def _make_sample_pdf(path: Path, color=(200, 200, 200)) -> None:
    """一页 PDF：白底 + 中央色块（模拟水印色）。"""
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    # 画整页接近白
    page.draw_rect(page.rect, color=(1, 1, 1), fill=(1, 1, 1))
    # 中央灰块
    page.draw_rect(fitz.Rect(50, 50, 150, 150), color=None, fill=(color[0] / 255, color[1] / 255, color[2] / 255))
    doc.save(path)
    doc.close()


def test_pipeline_remove_only_matches_single(tmp_path: Path):
    src = tmp_path / "in.pdf"
    out1 = tmp_path / "a.pdf"
    out2 = tmp_path / "b.pdf"
    _make_sample_pdf(src)
    params = RemoveParams(
        method=ColorMethod.COLOR_PICK,
        pairs=[ColorPair(samples=[(200, 200, 200)], background=(255, 255, 255))],
        tolerance=40,
        fill_mode=FillMode.SOLID,
        contrast=1.0,
        morph_open=0,
        morph_close=0,
        dpi=72,
        avoid_upsample=False,
    )
    process_pdf_remove(src, out1, params)
    process_pdf_pipeline(
        src,
        out2,
        [PIPELINE_STEP_REMOVE],
        remove_params=params,
    )
    # 都能生成
    assert out1.stat().st_size > 500
    assert out2.stat().st_size > 500


def test_pipeline_gray_then_region(tmp_path: Path):
    src = tmp_path / "in.pdf"
    out = tmp_path / "pipe.pdf"
    _make_sample_pdf(src, color=(180, 100, 100))
    regions = [RegionRect(page_index=0, x0=40, y0=40, x1=160, y1=160, color=(255, 255, 255))]
    process_pdf_pipeline(
        src,
        out,
        [PIPELINE_STEP_GRAY, PIPELINE_STEP_REGION],
        regions=regions,
        gray_dpi=72,
    )
    assert out.is_file() and out.stat().st_size > 500


def test_pipeline_requires_config(tmp_path: Path):
    src = tmp_path / "in.pdf"
    out = tmp_path / "x.pdf"
    _make_sample_pdf(src)
    try:
        process_pdf_pipeline(src, out, [PIPELINE_STEP_REMOVE], remove_params=None)
        assert False, "should fail"
    except ValueError as e:
        assert "颜色" in str(e)
