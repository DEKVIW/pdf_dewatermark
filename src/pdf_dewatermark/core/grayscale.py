"""灰度相关。"""

from __future__ import annotations

import numpy as np
from PIL import Image


def rgb_to_grayscale_array(img: np.ndarray) -> np.ndarray:
    """RGB → 灰度再扩回 3 通道（便于统一写 PDF）。"""
    rgb = img[..., :3].astype(np.float64)
    gray = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).astype(np.uint8)
    return np.stack([gray, gray, gray], axis=-1)


def pixmap_to_gray_rgb(image: Image.Image) -> Image.Image:
    arr = np.array(image.convert("RGB"))
    return Image.fromarray(rgb_to_grayscale_array(arr))
