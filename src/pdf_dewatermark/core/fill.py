"""掩码区域填充策略。"""

from __future__ import annotations

from typing import Tuple

import numpy as np

RGB = Tuple[int, int, int]


def apply_fill(
    img: np.ndarray,
    mask: np.ndarray,
    dist: np.ndarray,
    background: RGB,
    mode: str = "soft",
    tolerance: float = 28.0,
    feather: float = 8.0,
    neighbor_radius: int = 2,
) -> np.ndarray:
    """
    在 mask 区域应用填充，返回新的 uint8 RGB 图。
    soft: 靠近阈值边界时按距离羽化混合背景，减少硬边。
    neighbor: 用周围非 mask 像素均值填充（较慢，边缘更自然）。
    """
    out = img[..., :3].copy().astype(np.float64)
    bg = np.array(background, dtype=np.float64)
    m = mask.astype(bool)

    if not np.any(m):
        return img[..., :3].copy()

    if mode == "neighbor":
        return _neighbor_fill(out, m, bg, neighbor_radius)

    if mode == "solid":
        out[m] = bg
        return np.clip(out, 0, 255).astype(np.uint8)

    # soft：核心区完全替换，靠近容差边界羽化，减轻硬边
    feather = max(float(feather), 1e-3)
    d = dist.astype(np.float64)
    # d <= tolerance - feather → alpha=1；d → tolerance → alpha→0
    alpha = np.clip((float(tolerance) - d) / feather, 0.0, 1.0)
    alpha = np.where(m, alpha, 0.0)
    # 掩码内部至少强替换，避免「看起来没去掉」
    alpha = np.where(m, np.maximum(alpha, 0.85), 0.0)
    a = alpha[..., None]
    out = out * (1.0 - a) + bg * a
    return np.clip(out, 0, 255).astype(np.uint8)


def _neighbor_fill(
    out: np.ndarray,
    mask: np.ndarray,
    bg: np.ndarray,
    radius: int,
) -> np.ndarray:
    h, w = mask.shape
    r = max(1, int(radius))
    ys, xs = np.where(mask)
    result = out.copy()
    for y, x in zip(ys, xs):
        y0, y1 = max(0, y - r), min(h, y + r + 1)
        x0, x1 = max(0, x - r), min(w, x + r + 1)
        patch_mask = mask[y0:y1, x0:x1]
        patch = out[y0:y1, x0:x1]
        valid = ~patch_mask
        if np.any(valid):
            result[y, x] = patch[valid].mean(axis=0)
        else:
            result[y, x] = bg
    return np.clip(result, 0, 255).astype(np.uint8)
