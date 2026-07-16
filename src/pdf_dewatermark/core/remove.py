"""选色替换核心算法。支持多组「目标色 → 背景色」一次处理。"""

from __future__ import annotations

from typing import List, Sequence, Tuple

import numpy as np
from PIL import Image, ImageEnhance

from ..models import ColorMethod, ColorPair, FillMode, RemoveParams, RGB
from .fill import apply_fill
from .mask import clean_mask


def _as_method(params: RemoveParams) -> str:
    m = params.method
    return m.value if hasattr(m, "value") else str(m)


def _as_fill(params: RemoveParams) -> str:
    f = params.fill_mode
    return f.value if hasattr(f, "value") else str(f)


def _color_pick_mask(
    img: np.ndarray,
    colors: Sequence[RGB],
    tolerance: float,
    *,
    rgb_i: np.ndarray | None = None,
) -> np.ndarray:
    """
    mask = ||pixel - color||_2 < tolerance（多样本 OR）。

    使用平方距离比较（dist² < tol²），与 sqrt 后比较数学等价，结果一致且更快。
    可选传入预转换的 int32 RGB，避免多组时重复 astype。
    """
    if rgb_i is None:
        rgb_i = np.asarray(img[..., :3], dtype=np.int32)
    tol2 = float(tolerance) * float(tolerance)
    mask = np.zeros(rgb_i.shape[:2], dtype=bool)
    for color in colors:
        c0, c1, c2 = int(color[0]), int(color[1]), int(color[2])
        dr = rgb_i[..., 0] - c0
        dg = rgb_i[..., 1] - c1
        db = rgb_i[..., 2] - c2
        mask |= (dr * dr + dg * dg + db * db) < tol2
    return mask


def _color_pick_min_dist(
    rgb_i: np.ndarray,
    colors: Sequence[RGB],
) -> np.ndarray:
    """各像素到样本色的最小欧氏距离（float64），供 soft 填充使用。"""
    dist2 = np.full(rgb_i.shape[:2], np.inf, dtype=np.float64)
    for color in colors:
        c0, c1, c2 = int(color[0]), int(color[1]), int(color[2])
        dr = rgb_i[..., 0] - c0
        dg = rgb_i[..., 1] - c1
        db = rgb_i[..., 2] - c2
        d2 = (dr * dr + dg * dg + db * db).astype(np.float64)
        dist2 = np.minimum(dist2, d2)
    return np.sqrt(dist2)


def _threshold_mask(
    img: np.ndarray,
    color: RGB,
    sensitivity: float,
) -> np.ndarray:
    """色阶：各通道 [c±tol] OR。"""
    rgb = img[..., :3]
    sens = float(sensitivity)
    color_lower = [max(0, int(c) - sens) for c in color]
    color_upper = [min(255, int(c) + sens) for c in color]
    mask = np.zeros(rgb.shape[:2], dtype=bool)
    for i in range(3):
        mask |= (rgb[:, :, i] >= color_lower[i]) & (rgb[:, :, i] <= color_upper[i])
    return mask


def _pair_mask(
    img: np.ndarray,
    pair: ColorPair,
    method: str,
    tolerance: float,
    *,
    rgb_i: np.ndarray | None = None,
) -> np.ndarray:
    colors = list(pair.samples)
    if not colors:
        return np.zeros(img.shape[:2], dtype=bool)
    if method == ColorMethod.THRESHOLD.value:
        mask = np.zeros(img.shape[:2], dtype=bool)
        for c in colors:
            mask |= _threshold_mask(img, c, tolerance)
        return mask
    return _color_pick_mask(img, colors, tolerance, rgb_i=rgb_i)


def remove_watermark_array(
    img: np.ndarray,
    params: RemoveParams,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    对 RGB 数组做选色替换。

    多组 ColorPair：在**原图**上分别匹配，再按顺序写入结果
    （后组覆盖先组的重叠区域），最后统一做对比度/锐化。

    性能优化（结果等价）：
    - color_pick 用平方距离代替 sqrt
    - 整图 int32 只转换一次，多组复用
    - solid 路径直接写 uint8，不进 float 填充
    """
    pairs = params.resolved_pairs()
    if not pairs:
        rgb = np.ascontiguousarray(img[..., :3])
        return rgb.copy(), np.zeros(rgb.shape[:2], dtype=bool)

    method = _as_method(params)
    tol = float(params.tolerance)
    fill = _as_fill(params)
    source = np.ascontiguousarray(img[..., :3])
    out = source.copy()
    combined = np.zeros(source.shape[:2], dtype=bool)

    # color_pick：一次 int32 转换供所有 pair 复用（与逐对 float64 距离比较结果一致）
    rgb_i: np.ndarray | None = None
    if method == ColorMethod.COLOR_PICK.value:
        rgb_i = np.asarray(source, dtype=np.int32)

    use_solid = fill == FillMode.SOLID.value or fill not in (
        FillMode.SOFT.value,
        FillMode.NEIGHBOR.value,
    )

    for pair in pairs:
        mask = _pair_mask(source, pair, method, tol, rgb_i=rgb_i)
        if params.morph_open > 0 or params.morph_close > 0:
            mask = clean_mask(mask, params.morph_open, params.morph_close)
        if not np.any(mask):
            continue

        bg = np.array(pair.background, dtype=np.uint8)
        if use_solid:
            out[mask] = bg
        else:
            if method == ColorMethod.COLOR_PICK.value and rgb_i is not None:
                dist = _color_pick_min_dist(rgb_i, pair.samples)
            else:
                # threshold 等：用 float 距离到各样本（与旧 soft 路径一致）
                rgb_f = source.astype(np.float64)
                dist = np.full(mask.shape, np.inf, dtype=np.float64)
                for color in pair.samples:
                    c = np.array(color, dtype=np.float64)
                    d = np.sqrt(np.sum((rgb_f - c) ** 2, axis=-1))
                    dist = np.minimum(dist, d)
            out = apply_fill(
                out,
                mask,
                dist,
                pair.background,
                mode=fill,
                tolerance=tol,
                feather=params.soft_feather,
            )
        combined |= mask

    if abs(float(params.contrast) - 1.0) > 1e-6:
        pil = Image.fromarray(out)
        pil = ImageEnhance.Contrast(pil).enhance(float(params.contrast))
        out = np.array(pil)

    if params.sharpen:
        pil = Image.fromarray(out)
        pil = ImageEnhance.Sharpness(pil).enhance(float(params.sharpen_strength))
        out = np.array(pil)

    return out, combined


def remove_watermark_image(
    image: Image.Image,
    params: RemoveParams,
) -> Tuple[Image.Image, np.ndarray]:
    rgb = image.convert("RGB")
    # 直接从 buffer 建数组；PIL 保证 RGB 连续时少一次拷贝
    arr = np.asarray(rgb)
    out, mask = remove_watermark_array(arr, params)
    return Image.fromarray(out), mask


def overlay_mask_preview(
    original: np.ndarray,
    mask: np.ndarray,
    color: Tuple[int, int, int] = (255, 64, 64),
    alpha: float = 0.45,
) -> np.ndarray:
    base = original[..., :3].astype(np.float64)
    overlay = base.copy()
    c = np.array(color, dtype=np.float64)
    overlay[mask] = base[mask] * (1 - alpha) + c * alpha
    return np.clip(overlay, 0, 255).astype(np.uint8)
