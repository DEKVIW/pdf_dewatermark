"""颜色空间与掩码生成。"""

from __future__ import annotations

from typing import List, Sequence, Tuple

import numpy as np

RGB = Tuple[int, int, int]


def rgb_to_lab_approx(rgb: np.ndarray) -> np.ndarray:
    """
    sRGB → 近似 Lab（无需 skimage）。
    输入 float/uint8 形状 (..., 3)，输出 float64 Lab。
    """
    x = rgb.astype(np.float64) / 255.0
    # sRGB 线性化
    lim = 0.04045
    linear = np.where(x <= lim, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
    r, g, b = linear[..., 0], linear[..., 1], linear[..., 2]
    # sRGB D65 → XYZ
    x_ = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y_ = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z_ = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
    # 归一化到 D65 白点
    x_ /= 0.95047
    y_ /= 1.00000
    z_ /= 1.08883

    def f(t: np.ndarray) -> np.ndarray:
        delta = 6 / 29
        return np.where(t > delta**3, np.cbrt(t), t / (3 * delta**2) + 4 / 29)

    fx, fy, fz = f(x_), f(y_), f(z_)
    L = 116 * fy - 16
    a = 500 * (fx - fy)
    b_ = 200 * (fy - fz)
    return np.stack([L, a, b_], axis=-1)


def _distance_map(
    img: np.ndarray,
    target: RGB,
    method: str,
) -> np.ndarray:
    """返回每个像素到目标色的距离。"""
    if method == "distance_lab":
        lab_img = rgb_to_lab_approx(img)
        lab_t = rgb_to_lab_approx(np.array(target, dtype=np.float64).reshape(1, 1, 3))[0, 0]
        diff = lab_img - lab_t
        return np.sqrt(np.sum(diff * diff, axis=-1))
    # RGB 欧氏距离
    t = np.array(target, dtype=np.float64)
    diff = img.astype(np.float64) - t
    return np.sqrt(np.sum(diff * diff, axis=-1))


def build_color_mask(
    img: np.ndarray,
    colors: Sequence[RGB],
    tolerance: float,
    method: str = "distance",
) -> Tuple[np.ndarray, np.ndarray]:
    """
    根据一个或多个目标色生成布尔掩码。

    返回:
        mask: bool (H, W)
        min_dist: float (H, W) 到最近目标色的距离（用于 soft 填充）
    """
    if img.ndim != 3 or img.shape[2] < 3:
        raise ValueError("期望 RGB 图像数组")
    if not colors:
        h, w = img.shape[:2]
        z = np.zeros((h, w), dtype=bool)
        return z, np.full((h, w), np.inf, dtype=np.float64)

    rgb = img[..., :3]
    min_dist = None
    for c in colors:
        d = _distance_map(rgb, tuple(int(x) for x in c), method)
        min_dist = d if min_dist is None else np.minimum(min_dist, d)
    assert min_dist is not None
    mask = min_dist < float(tolerance)
    return mask, min_dist


def colors_from_samples(samples: List[RGB]) -> List[RGB]:
    """多点取样：返回中位数色作为主色，并保留全部样本供匹配。"""
    if not samples:
        return []
    # 匹配时用全部样本更稳；GUI 显示中位数
    return list(samples)
