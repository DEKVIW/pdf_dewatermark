"""核心算法测试。"""

from __future__ import annotations

import numpy as np

from pdf_dewatermark.core.remove import remove_watermark_array
from pdf_dewatermark.models import ColorMethod, ColorPair, FillMode, RemoveParams


def test_color_pick_formula():
    img = np.ones((40, 40, 3), dtype=np.uint8) * 255
    img[15:25, 15:25] = (210, 210, 210)
    color = np.array([210, 210, 210], dtype=np.float64)
    tol = 30.0
    legacy_mask = np.sqrt(np.sum((img.astype(np.float64) - color) ** 2, axis=-1)) < tol
    legacy = img.copy()
    legacy[legacy_mask] = (255, 255, 255)

    params = RemoveParams(
        method=ColorMethod.COLOR_PICK,
        watermark_colors=[(210, 210, 210)],
        background=(255, 255, 255),
        tolerance=tol,
        fill_mode=FillMode.SOLID,
        morph_open=0,
        morph_close=0,
        contrast=1.0,
    )
    out, mask = remove_watermark_array(img, params)
    assert np.array_equal(mask, legacy_mask)
    assert np.array_equal(out, legacy)


def test_multi_pair_different_backgrounds():
    """两组：灰水印→白，蓝水印→米白，一次处理。"""
    img = np.ones((30, 30, 3), dtype=np.uint8) * 255
    img[5:12, 5:12] = (200, 200, 200)  # 灰
    img[18:25, 18:25] = (180, 200, 220)  # 浅蓝

    params = RemoveParams(
        method=ColorMethod.COLOR_PICK,
        pairs=[
            ColorPair(samples=[(200, 200, 200)], background=(255, 255, 255)),
            ColorPair(samples=[(180, 200, 220)], background=(250, 245, 240)),
        ],
        tolerance=25,
        fill_mode=FillMode.SOLID,
        contrast=1.0,
        morph_open=0,
        morph_close=0,
    )
    out, mask = remove_watermark_array(img, params)
    assert mask[8, 8] and mask[20, 20]
    assert tuple(out[8, 8]) == (255, 255, 255)
    assert tuple(out[20, 20]) == (250, 245, 240)
    # 干净区保持
    assert tuple(out[0, 0]) == (255, 255, 255)


def test_threshold_channel_or():
    img = np.ones((10, 10, 3), dtype=np.uint8) * 255
    img[3:7, 3:7] = (200, 210, 220)
    params = RemoveParams(
        method=ColorMethod.THRESHOLD,
        watermark_colors=[(200, 210, 220)],
        tolerance=15,
        fill_mode=FillMode.SOLID,
        contrast=1.0,
        morph_open=0,
        morph_close=0,
    )
    out, mask = remove_watermark_array(img, params)
    assert mask[5, 5]
    assert out[5, 5, 0] == 255


def test_no_color_returns_copy():
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    img[:] = (30, 40, 50)
    params = RemoveParams(watermark_colors=[], pairs=[])
    out, mask = remove_watermark_array(img, params)
    assert not mask.any()
    assert np.array_equal(out, img)


def test_multi_pair_overlap_later_wins():
    """重叠区域后组覆盖先组（顺序语义不变）。"""
    img = np.ones((20, 20, 3), dtype=np.uint8) * 255
    img[8:12, 8:12] = (190, 190, 190)
    params = RemoveParams(
        method=ColorMethod.COLOR_PICK,
        pairs=[
            ColorPair(samples=[(190, 190, 190)], background=(255, 0, 0)),
            ColorPair(samples=[(190, 190, 190)], background=(0, 255, 0)),
        ],
        tolerance=20,
        fill_mode=FillMode.SOLID,
        contrast=1.0,
        morph_open=0,
        morph_close=0,
    )
    out, mask = remove_watermark_array(img, params)
    assert mask[10, 10]
    assert tuple(out[10, 10]) == (0, 255, 0)


def test_squared_distance_matches_legacy_sqrt():
    """平方距离与 sqrt 后比较在整像素上严格一致。"""
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, size=(48, 48, 3), dtype=np.uint8)
    color = (128, 140, 90)
    tol = 35.0
    c = np.array(color, dtype=np.float64)
    legacy = np.sqrt(np.sum((img.astype(np.float64) - c) ** 2, axis=-1)) < tol
    params = RemoveParams(
        method=ColorMethod.COLOR_PICK,
        watermark_colors=[color],
        background=(255, 255, 255),
        tolerance=tol,
        fill_mode=FillMode.SOLID,
        morph_open=0,
        morph_close=0,
        contrast=1.0,
    )
    _, mask = remove_watermark_array(img, params)
    assert np.array_equal(mask, legacy)
