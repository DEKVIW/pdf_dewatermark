"""处理参数与结果模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple

RGB = Tuple[int, int, int]


class ColorMethod(str, Enum):
    COLOR_PICK = "color_pick"  # 颜色点选：RGB 欧氏距离 + 硬替换
    THRESHOLD = "threshold"  # 色阶阈值：通道区间 OR + 硬替换


class FillMode(str, Enum):
    SOLID = "solid"
    SOFT = "soft"
    NEIGHBOR = "neighbor"


class ImageFormat(str, Enum):
    PNG = "png"
    JPEG = "jpeg"


class ExportPreset(str, Enum):
    """导出体积/清晰度预设（GUI 主控，可切自定义）。"""

    BALANCED = "balanced"  # 均衡推荐
    QUALITY = "quality"  # 高清
    SMALL = "small"  # 小体积
    CUSTOM = "custom"  # 自定义


# 预设 → 具体导出参数（避免无脑 300+PNG 胀文件）
EXPORT_PRESET_VALUES: dict[str, dict] = {
    ExportPreset.BALANCED.value: {
        "dpi": 200,
        "resolution_factor": 3.0,
        "image_format": ImageFormat.JPEG,
        "jpeg_quality": 92,
        "avoid_upsample": True,
    },
    ExportPreset.QUALITY.value: {
        "dpi": 250,
        "resolution_factor": 3.5,
        "image_format": ImageFormat.JPEG,
        "jpeg_quality": 95,
        "avoid_upsample": True,
    },
    ExportPreset.SMALL.value: {
        "dpi": 150,
        "resolution_factor": 2.5,
        "image_format": ImageFormat.JPEG,
        "jpeg_quality": 85,
        "avoid_upsample": True,
    },
}


def apply_export_preset(params: "RemoveParams", preset: ExportPreset | str) -> "RemoveParams":
    """就地写入预设导出字段（custom 不改）。"""
    key = preset.value if isinstance(preset, ExportPreset) else str(preset)
    if key == ExportPreset.CUSTOM.value or key not in EXPORT_PRESET_VALUES:
        return params
    cfg = EXPORT_PRESET_VALUES[key]
    params.dpi = int(cfg["dpi"])
    params.resolution_factor = float(cfg["resolution_factor"])
    params.image_format = cfg["image_format"]
    params.jpeg_quality = int(cfg["jpeg_quality"])
    params.avoid_upsample = bool(cfg["avoid_upsample"])
    params.export_preset = key
    return params


@dataclass
class ColorPair:
    """
    一组替换关系：目标色（可多样本）→ 替换为背景色。

    多组时可一次处理多种水印色，无需反复导出导入。
    """

    samples: List[RGB] = field(default_factory=list)
    background: RGB = (255, 255, 255)

    def primary(self) -> Optional[RGB]:
        return self.samples[-1] if self.samples else None

    def is_ready(self) -> bool:
        return bool(self.samples)

    def label(self) -> str:
        if not self.samples:
            return "（未取目标色）"
        t = self.samples[-1]
        b = self.background
        extra = f" +{len(self.samples) - 1}" if len(self.samples) > 1 else ""
        return f"RGB{t[0]},{t[1]},{t[2]}{extra} → {b[0]},{b[1]},{b[2]}"


@dataclass
class RemoveParams:
    """选色替换参数。支持多组 ColorPair 一次处理。"""

    method: ColorMethod = ColorMethod.COLOR_PICK
    # 多组：优先使用 pairs；为空时回退 watermark_colors + background
    pairs: List[ColorPair] = field(default_factory=list)
    watermark_colors: List[RGB] = field(default_factory=list)
    background: RGB = (255, 255, 255)
    tolerance: float = 30.0
    fill_mode: FillMode = FillMode.SOLID
    soft_feather: float = 8.0
    morph_open: int = 0
    morph_close: int = 0
    contrast: float = 1.2
    sharpen: bool = False
    sharpen_strength: float = 1.0
    # 导出默认：均衡（JPEG + 200 DPI + 扫描不放大）
    dpi: int = 200
    resolution_factor: float = 3.0
    image_format: ImageFormat = ImageFormat.JPEG
    jpeg_quality: int = 92
    # 扫描整页图：渲染 DPI 不超过原图等效分辨率，防放大虚化并控体积
    avoid_upsample: bool = True
    export_preset: str = ExportPreset.BALANCED.value

    def resolved_pairs(self) -> List[ColorPair]:
        """得到可执行的颜色组列表。"""
        ready = [p for p in self.pairs if p.is_ready()]
        if ready:
            return ready
        if self.watermark_colors:
            return [
                ColorPair(
                    samples=list(self.watermark_colors),
                    background=self.background,
                )
            ]
        return []

    def primary_color(self) -> Optional[RGB]:
        pairs = self.resolved_pairs()
        if pairs:
            return pairs[0].primary()
        return self.watermark_colors[-1] if self.watermark_colors else None

    def render_dpi(self) -> float:
        method = self.method.value if hasattr(self.method, "value") else str(self.method)
        if method == ColorMethod.THRESHOLD.value:
            return float(self.resolution_factor) * 72.0
        return float(self.dpi)


@dataclass
class RegionRect:
    page_index: int
    x0: float
    y0: float
    x1: float
    y1: float
    color: RGB = (255, 255, 255)

    def normalized(self) -> Tuple[float, float, float, float]:
        return (
            min(self.x0, self.x1),
            min(self.y0, self.y1),
            max(self.x0, self.x1),
            max(self.y0, self.y1),
        )


@dataclass
class GrayscaleParams:
    dpi: int = 200
    workers: int = 0


@dataclass
class ProcessProgress:
    current: int
    total: int
    message: str = ""


def median_color(colors: Sequence[RGB]) -> RGB:
    if not colors:
        return (128, 128, 128)
    import numpy as np

    arr = np.array(colors, dtype=np.float64)
    med = np.median(arr, axis=0)
    return tuple(int(round(c)) for c in med)  # type: ignore[return-value]
