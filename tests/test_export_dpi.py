"""导出 DPI 解析与预设。"""

from __future__ import annotations

from pdf_dewatermark.models import (
    EXPORT_PRESET_VALUES,
    ExportPreset,
    ImageFormat,
    RemoveParams,
    apply_export_preset,
)
from pdf_dewatermark.pdf.render import resolve_export_dpi


class _FakeRect:
    def __init__(self, w: float, h: float) -> None:
        self.width = w
        self.height = h


class _FakePage:
    def __init__(self, w_pt: float, h_pt: float, img_w: int, img_h: int) -> None:
        self.rect = _FakeRect(w_pt, h_pt)
        self._img = (1, 0, img_w, img_h, 8, "DeviceRGB", "", "X", "FlateDecode")

    def get_images(self, full: bool = True):
        return [self._img]


def test_resolve_export_dpi_caps_upsample():
    # A4 ≈ 595x842, image 1588x2245 → native ~192 DPI
    page = _FakePage(595.32, 841.92, 1588, 2245)
    dpi = resolve_export_dpi(page, 300, avoid_upsample=True)
    assert dpi < 220
    assert dpi > 180


def test_resolve_export_dpi_respects_lower_request():
    page = _FakePage(595.32, 841.92, 1588, 2245)
    dpi = resolve_export_dpi(page, 150, avoid_upsample=True)
    assert abs(dpi - 150) < 1e-6


def test_resolve_export_dpi_allow_upsample():
    page = _FakePage(595.32, 841.92, 1588, 2245)
    dpi = resolve_export_dpi(page, 300, avoid_upsample=False)
    assert abs(dpi - 300) < 1e-6


def test_balanced_preset_jpeg():
    p = RemoveParams()
    apply_export_preset(p, ExportPreset.BALANCED)
    assert p.image_format == ImageFormat.JPEG
    assert p.dpi == 200
    assert p.jpeg_quality == 92
    assert p.avoid_upsample is True
    assert ExportPreset.BALANCED.value in EXPORT_PRESET_VALUES
