"""掩码形态学清理。"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter


def clean_mask(
    mask: np.ndarray,
    open_radius: int = 1,
    close_radius: int = 2,
) -> np.ndarray:
    """
    开运算去孤立噪点，闭运算补水印空洞。
    radius 为 0 时跳过对应步骤；使用奇数核 PIL Min/MaxFilter。
    """
    if mask.dtype != bool:
        mask = mask.astype(bool)
    if open_radius <= 0 and close_radius <= 0:
        return mask

    im = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")

    def _open(image: Image.Image, r: int) -> Image.Image:
        if r <= 0:
            return image
        k = r * 2 + 1
        image = image.filter(ImageFilter.MinFilter(k))
        image = image.filter(ImageFilter.MaxFilter(k))
        return image

    def _close(image: Image.Image, r: int) -> Image.Image:
        if r <= 0:
            return image
        k = r * 2 + 1
        image = image.filter(ImageFilter.MaxFilter(k))
        image = image.filter(ImageFilter.MinFilter(k))
        return image

    im = _open(im, open_radius)
    im = _close(im, close_radius)
    return np.array(im) > 127
