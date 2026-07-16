"""将处理后的图像写回 PDF。"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple, Union

import fitz
from PIL import Image


def pil_to_png_bytes(image: Image.Image) -> bytes:
    # compress_level 6：体积与速度折中；optimize 对整页图收益小且慢
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def pil_to_jpeg_bytes(image: Image.Image, quality: int = 92) -> bytes:
    """
    JPEG 导出（默认体积优先路径）。

    quality 92 左右：白底讲义观感接近无损，体积远小于 PNG。
    subsampling=0 减少文字边缘色度抽样发糊（Pillow 支持时）。
    """
    buf = io.BytesIO()
    q = int(max(40, min(100, quality)))
    rgb = image.convert("RGB")
    try:
        rgb.save(
            buf,
            format="JPEG",
            quality=q,
            optimize=True,
            progressive=True,
            subsampling=0,
        )
    except OSError:
        rgb.save(buf, format="JPEG", quality=q, optimize=True)
    return buf.getvalue()


def image_to_pdf_page(
    doc: fitz.Document,
    image: Image.Image,
    width: float,
    height: float,
    fmt: str = "jpeg",
    jpeg_quality: int = 92,
) -> None:
    if fmt.lower() in ("jpg", "jpeg"):
        data = pil_to_jpeg_bytes(image, jpeg_quality)
    else:
        data = pil_to_png_bytes(image)
    page = doc.new_page(width=width, height=height)
    page.insert_image(page.rect, stream=data)


def save_images_as_pdf(
    pages: Sequence[Tuple[Image.Image, float, float]],
    output_path: Union[str, Path],
    fmt: str = "png",
    jpeg_quality: int = 92,
) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    try:
        for image, w, h in pages:
            image_to_pdf_page(doc, image, w, h, fmt=fmt, jpeg_quality=jpeg_quality)
        doc.save(out, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()
    return out
