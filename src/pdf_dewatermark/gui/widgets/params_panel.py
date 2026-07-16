"""选色替换参数面板：多组「目标色 → 背景色」+ 匹配/输出设置。"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CardWidget,
    CheckBox,
    ComboBox,
    DoubleSpinBox,
    PushButton,
    SpinBox,
)

from ...models import (
    EXPORT_PRESET_VALUES,
    ColorMethod,
    ColorPair,
    ExportPreset,
    FillMode,
    ImageFormat,
    RemoveParams,
    apply_export_preset,
)
from ..theme import (
    CTRL_HEIGHT,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
    apply_control_font,
    font_body,
    font_caption,
    font_section,
    style_caption_muted,
    thin_scrollbar_style,
)

RGB = Tuple[int, int, int]

_METHOD_ITEMS: Sequence[Tuple[str, str]] = (
    ("颜色点选", ColorMethod.COLOR_PICK.value),
    ("色阶阈值", ColorMethod.THRESHOLD.value),
)
_FILL_ITEMS: Sequence[Tuple[str, str]] = (
    ("硬替换", FillMode.SOLID.value),
    ("柔和羽化", FillMode.SOFT.value),
    ("邻域推算（慢）", FillMode.NEIGHBOR.value),
)
_FMT_ITEMS: Sequence[Tuple[str, str]] = (
    ("JPEG（推荐，体积小）", ImageFormat.JPEG.value),
    ("PNG（无损，体积大）", ImageFormat.PNG.value),
)
_EXPORT_PRESET_ITEMS: Sequence[Tuple[str, str]] = (
    ("均衡（推荐）", ExportPreset.BALANCED.value),
    ("高清", ExportPreset.QUALITY.value),
    ("小体积", ExportPreset.SMALL.value),
    ("自定义", ExportPreset.CUSTOM.value),
)
_RES_FACTORS = ("2.0", "2.5", "3.0", "3.5", "4.0", "5.0", "6.0")


class ColorSwatch(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(36, 24)
        self.set_color((255, 255, 255))

    def set_color(self, rgb: RGB) -> None:
        r, g, b = rgb
        self.setStyleSheet(
            f"background-color: rgb({r},{g},{b});"
            "border: 1px solid #d1d5db; border-radius: 4px;"
        )


def _fill_combo(combo: ComboBox, items: Sequence[Tuple[str, str]], current: str | None = None) -> None:
    combo.clear()
    for text, _key in items:
        combo.addItem(text)
    for i, (_text, key) in enumerate(items):
        combo.setItemData(i, key)
    if current == "distance":
        current = ColorMethod.COLOR_PICK.value
    if current == "distance_lab":
        current = ColorMethod.COLOR_PICK.value
    if current:
        for i, (_text, key) in enumerate(items):
            if key == current:
                combo.setCurrentIndex(i)
                return
    combo.setCurrentIndex(0)


def _combo_value(combo: ComboBox, items: Sequence[Tuple[str, str]], default: str) -> str:
    data = combo.currentData()
    if data:
        v = str(data)
        if v == "distance":
            return ColorMethod.COLOR_PICK.value
        return v
    idx = combo.currentIndex()
    if 0 <= idx < len(items):
        return items[idx][1]
    return default


def _section_title(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setFont(font_section())
    lab.setStyleSheet("color: #111827; margin-top: 2px;")
    return lab


def _hint(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setFont(font_caption())
    lab.setStyleSheet(style_caption_muted())
    return lab


def _field_label(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setFont(font_body())
    lab.setStyleSheet("color: #374151;")
    lab.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
    return lab


class ParamsPanel(CardWidget):
    params_changed = Signal()
    pick_bg_requested = Signal()
    clear_colors_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # 多组：每组目标样本 + 背景
        self._pairs: List[ColorPair] = [ColorPair()]
        self._current = 0
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # 细滚动条，避免默认粗条把右侧控件「挤不全」
        scroll.setStyleSheet(thin_scrollbar_style(dark=False))
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        # 右侧略留空，细条旁文字/下拉不被挡
        root.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_SM + SPACE_XS, SPACE_MD)
        root.setSpacing(SPACE_MD)

        # —— 颜色组（多对目标→背景）——
        root.addWidget(_section_title("颜色组"))
        root.addWidget(
            _hint(
                "可添加多组「目标色 → 背景色」，一次处理多种水印。"
                "在预览上单击取当前组目标色；需要时再取背景色。"
            )
        )

        self.pair_list = QListWidget()
        self.pair_list.setMinimumHeight(100)
        self.pair_list.setMaximumHeight(160)
        self.pair_list.setFont(font_body())
        self.pair_list.currentRowChanged.connect(self._on_pair_selected)
        root.addWidget(self.pair_list)

        list_btns = QHBoxLayout()
        list_btns.setSpacing(SPACE_SM)
        self.add_pair_btn = PushButton("添加一组")
        self.del_pair_btn = PushButton("删除本组")
        self.clear_all_btn = PushButton("清空全部")
        for b in (self.add_pair_btn, self.del_pair_btn, self.clear_all_btn):
            apply_control_font(b)
            b.setFixedHeight(CTRL_HEIGHT)
        self.add_pair_btn.clicked.connect(self._add_pair)
        self.del_pair_btn.clicked.connect(self._delete_pair)
        self.clear_all_btn.clicked.connect(self._clear_all_pairs)
        list_btns.addWidget(self.add_pair_btn)
        list_btns.addWidget(self.del_pair_btn)
        list_btns.addWidget(self.clear_all_btn)
        root.addLayout(list_btns)

        root.addWidget(_section_title("当前组"))
        cur = QGridLayout()
        cur.setHorizontalSpacing(SPACE_SM)
        cur.setVerticalSpacing(SPACE_SM)

        self.target_swatch = ColorSwatch()
        self.target_label = QLabel("目标色：未取样")
        self.target_label.setFont(font_body())
        cur.addWidget(self.target_swatch, 0, 0)
        cur.addWidget(self.target_label, 0, 1)

        self.bg_swatch = ColorSwatch()
        self.bg_label = QLabel("背景：255, 255, 255")
        self.bg_label.setFont(font_body())
        cur.addWidget(self.bg_swatch, 1, 0)
        cur.addWidget(self.bg_label, 1, 1)
        root.addLayout(cur)

        cur_btns = QHBoxLayout()
        self.clear_target_btn = PushButton("清空目标色")
        self.pick_bg_btn = PushButton("取背景色")
        for b in (self.clear_target_btn, self.pick_bg_btn):
            apply_control_font(b)
            b.setFixedHeight(CTRL_HEIGHT)
        self.clear_target_btn.clicked.connect(self._clear_current_target)
        self.pick_bg_btn.clicked.connect(self.pick_bg_requested.emit)
        cur_btns.addWidget(self.clear_target_btn)
        cur_btns.addWidget(self.pick_bg_btn)
        root.addLayout(cur_btns)
        root.addWidget(_hint("同一组内可多点取样（颜色接近时合并匹配）；不同水印请用多组。"))

        root.addWidget(self._divider())

        # —— 匹配 ——
        root.addWidget(_section_title("匹配"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACE_SM)
        grid.setVerticalSpacing(SPACE_SM)
        grid.setColumnStretch(1, 1)

        self.method = ComboBox()
        _fill_combo(self.method, _METHOD_ITEMS)
        apply_control_font(self.method)
        self.method.setFixedHeight(CTRL_HEIGHT)
        self.method.currentIndexChanged.connect(self._on_method_changed)
        grid.addWidget(_field_label("方法"), 0, 0)
        grid.addWidget(self.method, 0, 1)

        self.tolerance = SpinBox()
        self.tolerance.setRange(5, 100)
        self.tolerance.setValue(30)
        apply_control_font(self.tolerance)
        self.tolerance.setFixedHeight(CTRL_HEIGHT)
        grid.addWidget(_field_label("容差"), 1, 0)
        grid.addWidget(self.tolerance, 1, 1)

        self.contrast = DoubleSpinBox()
        self.contrast.setRange(0.5, 2.5)
        self.contrast.setSingleStep(0.1)
        self.contrast.setValue(1.2)
        apply_control_font(self.contrast)
        self.contrast.setFixedHeight(CTRL_HEIGHT)
        grid.addWidget(_field_label("对比度"), 2, 0)
        grid.addWidget(self.contrast, 2, 1)
        root.addLayout(grid)
        root.addWidget(_hint("颜色点选：与目标色距离小于容差即替换。色阶：RGB 各通道 ±容差。"))

        root.addWidget(self._divider())

        # —— 输出（体积 / 清晰度）——
        root.addWidget(_section_title("导出"))
        grid2 = QGridLayout()
        grid2.setHorizontalSpacing(SPACE_SM)
        grid2.setVerticalSpacing(SPACE_SM)
        grid2.setColumnStretch(1, 1)

        self.export_preset = ComboBox()
        _fill_combo(self.export_preset, _EXPORT_PRESET_ITEMS, ExportPreset.BALANCED.value)
        apply_control_font(self.export_preset)
        self.export_preset.setFixedHeight(CTRL_HEIGHT)
        grid2.addWidget(_field_label("预设"), 0, 0)
        grid2.addWidget(self.export_preset, 0, 1)

        self.dpi = SpinBox()
        self.dpi.setRange(72, 600)
        self.dpi.setSingleStep(25)
        self.dpi.setValue(200)
        apply_control_font(self.dpi)
        self.dpi.setFixedHeight(CTRL_HEIGHT)
        self._dpi_label = _field_label("DPI")
        grid2.addWidget(self._dpi_label, 1, 0)
        grid2.addWidget(self.dpi, 1, 1)

        self.resolution = ComboBox()
        for v in _RES_FACTORS:
            self.resolution.addItem(v)
            self.resolution.setItemData(self.resolution.count() - 1, float(v))
        # 默认 3.0
        for i in range(self.resolution.count()):
            if abs(float(self.resolution.itemData(i) or 0) - 3.0) < 1e-6:
                self.resolution.setCurrentIndex(i)
                break
        apply_control_font(self.resolution)
        self.resolution.setFixedHeight(CTRL_HEIGHT)
        self._res_label = _field_label("分辨率×")
        grid2.addWidget(self._res_label, 2, 0)
        grid2.addWidget(self.resolution, 2, 1)

        self.fmt = ComboBox()
        _fill_combo(self.fmt, _FMT_ITEMS, ImageFormat.JPEG.value)
        apply_control_font(self.fmt)
        self.fmt.setFixedHeight(CTRL_HEIGHT)
        grid2.addWidget(_field_label("格式"), 3, 0)
        grid2.addWidget(self.fmt, 3, 1)

        self.jpeg_quality = SpinBox()
        self.jpeg_quality.setRange(70, 100)
        self.jpeg_quality.setValue(92)
        apply_control_font(self.jpeg_quality)
        self.jpeg_quality.setFixedHeight(CTRL_HEIGHT)
        self._jpeg_q_label = _field_label("JPEG 质量")
        grid2.addWidget(self._jpeg_q_label, 4, 0)
        grid2.addWidget(self.jpeg_quality, 4, 1)

        self.avoid_upsample = CheckBox("扫描页不超过原图分辨率")
        self.avoid_upsample.setChecked(True)
        self.avoid_upsample.setToolTip(
            "整页扫描图不放大超过原图像素，避免虚化并控制体积（推荐开启）"
        )
        apply_control_font(self.avoid_upsample)
        grid2.addWidget(self.avoid_upsample, 5, 0, 1, 2)

        self.sharpen = CheckBox("锐化")
        apply_control_font(self.sharpen)
        grid2.addWidget(self.sharpen, 6, 0, 1, 2)
        root.addLayout(grid2)

        self.export_hint = _hint(
            "均衡：JPEG·200DPI，适合讲义；高清更清晰略大；小体积适合传阅。"
            "扫描页默认不高于原图分辨率。"
        )
        root.addWidget(self.export_hint)

        self.export_preset.currentIndexChanged.connect(self._on_export_preset_changed)
        self.fmt.currentIndexChanged.connect(self._on_fmt_changed)
        for w in (self.dpi, self.resolution, self.fmt, self.jpeg_quality):
            if hasattr(w, "valueChanged"):
                w.valueChanged.connect(self._mark_export_custom)
            if hasattr(w, "currentIndexChanged"):
                w.currentIndexChanged.connect(self._mark_export_custom)
        self.avoid_upsample.stateChanged.connect(self._mark_export_custom)
        self._on_fmt_changed()
        self._sync_export_detail_enabled()

        root.addWidget(self._divider())

        # —— 可选 ——
        root.addWidget(_section_title("可选"))
        grid3 = QGridLayout()
        grid3.setHorizontalSpacing(SPACE_SM)
        grid3.setVerticalSpacing(SPACE_SM)
        grid3.setColumnStretch(1, 1)

        self.fill = ComboBox()
        _fill_combo(self.fill, _FILL_ITEMS, FillMode.SOLID.value)
        apply_control_font(self.fill)
        self.fill.setFixedHeight(CTRL_HEIGHT)
        grid3.addWidget(_field_label("填充"), 0, 0)
        grid3.addWidget(self.fill, 0, 1)

        self.morph_open = SpinBox()
        self.morph_open.setRange(0, 5)
        self.morph_open.setValue(0)
        apply_control_font(self.morph_open)
        self.morph_open.setFixedHeight(CTRL_HEIGHT)
        grid3.addWidget(_field_label("去噪"), 1, 0)
        grid3.addWidget(self.morph_open, 1, 1)

        self.morph_close = SpinBox()
        self.morph_close.setRange(0, 5)
        self.morph_close.setValue(0)
        apply_control_font(self.morph_close)
        self.morph_close.setFixedHeight(CTRL_HEIGHT)
        grid3.addWidget(_field_label("补洞"), 2, 0)
        grid3.addWidget(self.morph_close, 2, 1)
        root.addLayout(grid3)
        root.addWidget(_hint("一般保持硬替换，去噪/补洞为 0。"))

        root.addStretch(1)

        for w in (
            self.method,
            self.fill,
            self.tolerance,
            self.dpi,
            self.contrast,
            self.morph_open,
            self.morph_close,
            self.fmt,
            self.resolution,
            self.export_preset,
            self.jpeg_quality,
        ):
            if hasattr(w, "currentIndexChanged"):
                w.currentIndexChanged.connect(lambda *_: self.params_changed.emit())
            if hasattr(w, "valueChanged"):
                w.valueChanged.connect(lambda *_: self.params_changed.emit())
        self.sharpen.stateChanged.connect(lambda *_: self.params_changed.emit())
        self.avoid_upsample.stateChanged.connect(lambda *_: self.params_changed.emit())

        self._refresh_pair_list()
        self._on_method_changed()

    # ----- pairs -----

    def _ensure_index(self) -> int:
        if not self._pairs:
            self._pairs = [ColorPair()]
            self._current = 0
        self._current = max(0, min(self._current, len(self._pairs) - 1))
        return self._current

    def _refresh_pair_list(self) -> None:
        idx = self._ensure_index()
        self.pair_list.blockSignals(True)
        self.pair_list.clear()
        for i, pair in enumerate(self._pairs):
            mark = "●" if pair.is_ready() else "○"
            text = f"{i + 1}. {mark} {pair.label()}"
            self.pair_list.addItem(QListWidgetItem(text))
        self.pair_list.setCurrentRow(idx)
        self.pair_list.blockSignals(False)
        self._sync_current_widgets()

    def _sync_current_widgets(self) -> None:
        i = self._ensure_index()
        pair = self._pairs[i]
        if pair.samples:
            t = pair.samples[-1]
            self.target_swatch.set_color(t)
            if len(pair.samples) == 1:
                self.target_label.setText(f"目标色：{t[0]}, {t[1]}, {t[2]}")
            else:
                self.target_label.setText(
                    f"目标色：{t[0]}, {t[1]}, {t[2]}（{len(pair.samples)} 点）"
                )
        else:
            self.target_swatch.set_color((255, 255, 255))
            self.target_label.setText("目标色：未取样")
        b = pair.background
        self.bg_swatch.set_color(b)
        self.bg_label.setText(f"背景：{b[0]}, {b[1]}, {b[2]}")

    def _on_pair_selected(self, row: int) -> None:
        if row < 0:
            return
        self._current = row
        self._sync_current_widgets()

    def _add_pair(self) -> None:
        self._pairs.append(ColorPair())
        self._current = len(self._pairs) - 1
        self._refresh_pair_list()
        self.params_changed.emit()

    def _delete_pair(self) -> None:
        if len(self._pairs) <= 1:
            self._pairs = [ColorPair()]
            self._current = 0
        else:
            i = self._ensure_index()
            del self._pairs[i]
            self._current = min(i, len(self._pairs) - 1)
        self._refresh_pair_list()
        self.clear_colors_requested.emit()
        self.params_changed.emit()

    def _clear_all_pairs(self) -> None:
        self._pairs = [ColorPair()]
        self._current = 0
        self._refresh_pair_list()
        self.clear_colors_requested.emit()
        self.params_changed.emit()

    def _clear_current_target(self) -> None:
        i = self._ensure_index()
        self._pairs[i].samples.clear()
        self._refresh_pair_list()
        self.params_changed.emit()

    def add_sample(self, rgb: RGB) -> None:
        """为当前组追加目标色样本。"""
        i = self._ensure_index()
        self._pairs[i].samples.append(rgb)
        self._refresh_pair_list()
        self.params_changed.emit()

    def set_background(self, rgb: RGB) -> None:
        """设置当前组背景色。"""
        i = self._ensure_index()
        self._pairs[i].background = rgb
        self._refresh_pair_list()
        self.params_changed.emit()

    def has_colors(self) -> bool:
        return any(p.is_ready() for p in self._pairs)

    def pair_count_ready(self) -> int:
        return sum(1 for p in self._pairs if p.is_ready())

    # ----- rest -----

    def _on_method_changed(self) -> None:
        # 导出细节可编辑性 + 点选/色阶用 DPI 还是分辨率×
        self._sync_export_detail_enabled()

    def _on_fmt_changed(self) -> None:
        is_jpeg = (
            _combo_value(self.fmt, _FMT_ITEMS, ImageFormat.JPEG.value)
            == ImageFormat.JPEG.value
        )
        self.jpeg_quality.setEnabled(is_jpeg)
        self._jpeg_q_label.setEnabled(is_jpeg)

    def _sync_export_detail_enabled(self) -> None:
        preset = _combo_value(
            self.export_preset, _EXPORT_PRESET_ITEMS, ExportPreset.BALANCED.value
        )
        custom = preset == ExportPreset.CUSTOM.value
        for w in (
            self.dpi,
            self.resolution,
            self.fmt,
            self.jpeg_quality,
            self.avoid_upsample,
        ):
            w.setEnabled(custom)
        self._dpi_label.setEnabled(custom)
        self._res_label.setEnabled(custom)
        self._jpeg_q_label.setEnabled(custom)
        if custom:
            self._on_method_changed_export_only()
            self._on_fmt_changed()

    def _on_method_changed_export_only(self) -> None:
        is_th = _combo_value(self.method, _METHOD_ITEMS, ColorMethod.COLOR_PICK.value) == (
            ColorMethod.THRESHOLD.value
        )
        self.dpi.setEnabled(not is_th)
        self.resolution.setEnabled(is_th)
        self._dpi_label.setEnabled(not is_th)
        self._res_label.setEnabled(is_th)

    def _mark_export_custom(self, *_args) -> None:
        """用户改了细节 → 切到自定义，避免预设与数值不一致。"""
        if getattr(self, "_export_applying", False):
            return
        cur = _combo_value(
            self.export_preset, _EXPORT_PRESET_ITEMS, ExportPreset.BALANCED.value
        )
        if cur != ExportPreset.CUSTOM.value:
            self._export_applying = True
            try:
                _fill_combo(self.export_preset, _EXPORT_PRESET_ITEMS, ExportPreset.CUSTOM.value)
            finally:
                self._export_applying = False
            self._sync_export_detail_enabled()

    def _on_export_preset_changed(self, *_args) -> None:
        if getattr(self, "_export_applying", False):
            return
        key = _combo_value(
            self.export_preset, _EXPORT_PRESET_ITEMS, ExportPreset.BALANCED.value
        )
        if key == ExportPreset.CUSTOM.value:
            self._sync_export_detail_enabled()
            return
        cfg = EXPORT_PRESET_VALUES.get(key)
        if not cfg:
            return
        self._export_applying = True
        try:
            self.dpi.setValue(int(cfg["dpi"]))
            rf = float(cfg["resolution_factor"])
            for i in range(self.resolution.count()):
                data = self.resolution.itemData(i)
                if data is not None and abs(float(data) - rf) < 1e-6:
                    self.resolution.setCurrentIndex(i)
                    break
            fmt = cfg["image_format"]
            fmt_v = fmt.value if hasattr(fmt, "value") else str(fmt)
            _fill_combo(self.fmt, _FMT_ITEMS, fmt_v)
            self.jpeg_quality.setValue(int(cfg["jpeg_quality"]))
            self.avoid_upsample.setChecked(bool(cfg["avoid_upsample"]))
        finally:
            self._export_applying = False
        self._sync_export_detail_enabled()
        hints = {
            ExportPreset.BALANCED.value: "均衡：JPEG 质量 92 · 200 DPI，讲义常用，体积与清晰兼顾。",
            ExportPreset.QUALITY.value: "高清：JPEG 质量 95 · 250 DPI，更清晰，体积略大。",
            ExportPreset.SMALL.value: "小体积：JPEG 质量 85 · 150 DPI，适合分享传阅。",
        }
        self.export_hint.setText(
            hints.get(key, "自定义：可改 DPI / 格式 / 质量；扫描页建议开启「不超过原图分辨率」。")
        )
        self.params_changed.emit()

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #e5e7eb; background: #e5e7eb; max-height: 1px;")
        line.setFixedHeight(1)
        return line

    def build_params(self) -> RemoveParams:
        method_data = _combo_value(self.method, _METHOD_ITEMS, ColorMethod.COLOR_PICK.value)
        fill_data = _combo_value(self.fill, _FILL_ITEMS, FillMode.SOLID.value)
        fmt_data = _combo_value(self.fmt, _FMT_ITEMS, ImageFormat.JPEG.value)
        preset = _combo_value(
            self.export_preset, _EXPORT_PRESET_ITEMS, ExportPreset.BALANCED.value
        )
        res = self.resolution.currentData()
        if res is None:
            try:
                res = float(self.resolution.currentText())
            except ValueError:
                res = 3.0
        pairs = [
            ColorPair(samples=list(p.samples), background=p.background)
            for p in self._pairs
            if p.is_ready()
        ]
        # 兼容字段：第一组写入 watermark_colors / background
        first_colors: List[RGB] = list(pairs[0].samples) if pairs else []
        first_bg = pairs[0].background if pairs else (255, 255, 255)
        params = RemoveParams(
            method=ColorMethod(method_data),
            pairs=pairs,
            watermark_colors=first_colors,
            background=first_bg,
            tolerance=float(self.tolerance.value()),
            fill_mode=FillMode(fill_data),
            morph_open=int(self.morph_open.value()),
            morph_close=int(self.morph_close.value()),
            contrast=float(self.contrast.value()),
            sharpen=self.sharpen.isChecked(),
            dpi=int(self.dpi.value()),
            resolution_factor=float(res),
            image_format=ImageFormat(fmt_data),
            jpeg_quality=int(self.jpeg_quality.value()),
            avoid_upsample=self.avoid_upsample.isChecked(),
            export_preset=preset,
        )
        # 非自定义时以预设表为准，防止 UI 只读不同步
        if preset != ExportPreset.CUSTOM.value:
            apply_export_preset(params, preset)
        return params

    def apply_prefs(self, prefs: dict) -> None:
        preset = str(prefs.get("export_preset", ExportPreset.BALANCED.value))
        self._export_applying = True
        try:
            self.tolerance.setValue(int(prefs.get("tolerance", 30)))
            self.dpi.setValue(int(prefs.get("dpi", 200)))
            self.contrast.setValue(float(prefs.get("contrast", 1.2)))
            self.morph_open.setValue(int(prefs.get("morph_open", 0)))
            self.morph_close.setValue(int(prefs.get("morph_close", 0)))
            method = prefs.get("method", ColorMethod.COLOR_PICK.value)
            _fill_combo(self.method, _METHOD_ITEMS, method)
            fill = prefs.get("fill_mode", FillMode.SOLID.value)
            _fill_combo(self.fill, _FILL_ITEMS, fill)
            _fill_combo(
                self.fmt,
                _FMT_ITEMS,
                prefs.get("image_format", ImageFormat.JPEG.value),
            )
            self.jpeg_quality.setValue(int(prefs.get("jpeg_quality", 92)))
            self.avoid_upsample.setChecked(bool(prefs.get("avoid_upsample", True)))
            rf = str(prefs.get("resolution_factor", "3.0"))
            for i in range(self.resolution.count()):
                if self.resolution.itemText(i) == rf or str(self.resolution.itemData(i)) == rf:
                    self.resolution.setCurrentIndex(i)
                    break
            self.sharpen.setChecked(bool(prefs.get("sharpen", False)))
            _fill_combo(self.export_preset, _EXPORT_PRESET_ITEMS, preset)
        finally:
            self._export_applying = False
        if preset != ExportPreset.CUSTOM.value:
            self._on_export_preset_changed()
        else:
            self._sync_export_detail_enabled()
        self._on_method_changed()

    def to_prefs(self) -> dict:
        res = self.resolution.currentData()
        if res is None:
            res = self.resolution.currentText()
        return {
            "tolerance": self.tolerance.value(),
            "dpi": self.dpi.value(),
            "contrast": self.contrast.value(),
            "morph_open": self.morph_open.value(),
            "morph_close": self.morph_close.value(),
            "method": _combo_value(self.method, _METHOD_ITEMS, ColorMethod.COLOR_PICK.value),
            "fill_mode": _combo_value(self.fill, _FILL_ITEMS, FillMode.SOLID.value),
            "image_format": _combo_value(self.fmt, _FMT_ITEMS, ImageFormat.JPEG.value),
            "jpeg_quality": self.jpeg_quality.value(),
            "avoid_upsample": self.avoid_upsample.isChecked(),
            "export_preset": _combo_value(
                self.export_preset, _EXPORT_PRESET_ITEMS, ExportPreset.BALANCED.value
            ),
            "resolution_factor": str(res),
            "sharpen": self.sharpen.isChecked(),
        }
