"""批量选色替换：支持同步多组颜色参数。"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SpinBox,
    StrongBodyLabel,
)

from ...models import ColorMethod, ColorPair, FillMode, RemoveParams
from ...paths import OUTPUT_DIR
from .. import icons as I
from ..theme import CTRL_HEIGHT, SPACE_SM, apply_control_font


class BatchPage(QWidget):
    status = Signal(str)
    request_job = Signal(object)
    log = Signal(str)
    sync_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._files: List[str] = []
        self._params: Optional[RemoveParams] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SPACE_SM)

        card = CardWidget()
        lay = QVBoxLayout(card)
        lay.addWidget(StrongBodyLabel("批量选色替换"))
        lay.addWidget(
            BodyLabel(
                "对多个 PDF 使用同一套颜色组参数批量导出。"
                "推荐先在「选色替换」调好多组颜色，再点「从选色页同步」。"
            )
        )

        bar = QHBoxLayout()
        add_btn = PushButton("添加文件…")
        add_btn.setIcon(I.ICO_ADD.icon())
        add_btn.clicked.connect(self.add_files)
        clear_btn = PushButton("清空列表")
        clear_btn.setIcon(I.ICO_CLEAR.icon())
        clear_btn.clicked.connect(self.clear)
        sync_btn = PrimaryPushButton("从选色页同步")
        sync_btn.setIcon(I.ICO_SYNC.icon())
        sync_btn.clicked.connect(lambda: self.sync_requested.emit())
        for b in (add_btn, clear_btn, sync_btn):
            apply_control_font(b)
            b.setFixedHeight(CTRL_HEIGHT)
        bar.addWidget(add_btn)
        bar.addWidget(clear_btn)
        bar.addWidget(sync_btn)
        bar.addStretch(1)
        lay.addLayout(bar)

        self.list = QListWidget()
        self.list.setMinimumHeight(120)
        lay.addWidget(self.list)

        lay.addWidget(StrongBodyLabel("颜色参数"))
        self.pairs_view = QListWidget()
        self.pairs_view.setMaximumHeight(120)
        self.pairs_view.addItem("尚未同步：请点「从选色页同步」，或下方填写单组 RGB")
        lay.addWidget(self.pairs_view)

        row = QHBoxLayout()
        self.r = SpinBox()
        self.g = SpinBox()
        self.b = SpinBox()
        for s in (self.r, self.g, self.b):
            s.setRange(0, 255)
        self.r.setValue(200)
        self.g.setValue(200)
        self.b.setValue(200)
        self.tol = SpinBox()
        self.tol.setRange(5, 120)
        self.tol.setValue(30)
        self.dpi = SpinBox()
        self.dpi.setRange(72, 600)
        self.dpi.setValue(200)
        row.addWidget(BodyLabel("备用单组 RGB"))
        row.addWidget(self.r)
        row.addWidget(self.g)
        row.addWidget(self.b)
        row.addWidget(BodyLabel("容差"))
        row.addWidget(self.tol)
        row.addWidget(BodyLabel("DPI"))
        row.addWidget(self.dpi)
        lay.addLayout(row)
        lay.addWidget(
            BodyLabel("若已同步多组，将优先使用同步参数；未同步时使用上方备用 RGB。")
        )

        out_row = QHBoxLayout()
        self.out_dir = LineEdit()
        self.out_dir.setText(str(OUTPUT_DIR))
        browse = PushButton("输出目录…")
        browse.setIcon(I.NAV_OUTPUT.icon())
        browse.clicked.connect(self._browse_out)
        apply_control_font(browse)
        browse.setFixedHeight(CTRL_HEIGHT)
        out_row.addWidget(self.out_dir, 1)
        out_row.addWidget(browse)
        lay.addLayout(out_row)

        run = PrimaryPushButton("开始批量处理")
        run.setIcon(I.ICO_PLAY.icon())
        apply_control_font(run)
        run.setFixedHeight(CTRL_HEIGHT)
        run.clicked.connect(self.run)
        lay.addWidget(run)
        root.addWidget(card)
        root.addStretch(1)

    def apply_remove_params(self, params: RemoveParams) -> None:
        """从选色替换页同步完整参数（含多组）。"""
        self._params = params
        self.tol.setValue(int(params.tolerance))
        self.dpi.setValue(int(params.dpi))
        pairs = params.resolved_pairs()
        self.pairs_view.clear()
        if not pairs:
            self.pairs_view.addItem("选色页尚无可用颜色组")
            return
        for i, pair in enumerate(pairs, 1):
            self.pairs_view.addItem(f"{i}. {pair.label()}")
        # 同步第一组到备用 RGB 显示
        p0 = pairs[0].primary()
        if p0:
            self.r.setValue(p0[0])
            self.g.setValue(p0[1])
            self.b.setValue(p0[2])

    def add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "选择 PDF", "", "PDF (*.pdf)")
        for f in files:
            if f not in self._files:
                self._files.append(f)
                self.list.addItem(f)
        self.status.emit(f"队列 {len(self._files)} 个文件")

    def clear(self) -> None:
        self._files.clear()
        self.list.clear()

    def _browse_out(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "输出目录", self.out_dir.text())
        if d:
            self.out_dir.setText(d)

    def _build_params(self) -> RemoveParams:
        if self._params is not None and self._params.resolved_pairs():
            p = self._params
            # 允许用当前 UI 覆盖容差/DPI
            return RemoveParams(
                method=p.method,
                pairs=list(p.resolved_pairs()),
                watermark_colors=list(p.watermark_colors),
                background=p.background,
                tolerance=float(self.tol.value()),
                fill_mode=p.fill_mode,
                morph_open=p.morph_open,
                morph_close=p.morph_close,
                contrast=p.contrast,
                sharpen=p.sharpen,
                dpi=int(self.dpi.value()),
                resolution_factor=p.resolution_factor,
                image_format=p.image_format,
                jpeg_quality=int(getattr(p, "jpeg_quality", 92)),
                avoid_upsample=bool(getattr(p, "avoid_upsample", True)),
                export_preset=str(getattr(p, "export_preset", "custom")),
            )
        from ...models import ImageFormat

        return RemoveParams(
            method=ColorMethod.COLOR_PICK,
            pairs=[
                ColorPair(
                    samples=[(self.r.value(), self.g.value(), self.b.value())],
                    background=(255, 255, 255),
                )
            ],
            watermark_colors=[(self.r.value(), self.g.value(), self.b.value())],
            tolerance=float(self.tol.value()),
            fill_mode=FillMode.SOLID,
            contrast=1.2,
            dpi=int(self.dpi.value()),
            image_format=ImageFormat.JPEG,
            jpeg_quality=92,
            avoid_upsample=True,
            export_preset="balanced",
        )

    def run(self) -> None:
        from ..workers import JobRequest

        if not self._files:
            self.status.emit("请先添加 PDF")
            return
        out = self.out_dir.text().strip() or str(OUTPUT_DIR)
        Path(out).mkdir(parents=True, exist_ok=True)
        params = self._build_params()
        if not params.resolved_pairs():
            self.status.emit("没有可用的颜色组参数")
            return
        req = JobRequest(
            kind="batch_remove",
            params=params,
            batch_files=list(self._files),
            batch_output_dir=out,
            output_path=out,
        )
        n = len(params.resolved_pairs())
        self.log.emit(f"批量处理 {len(self._files)} 个文件 · {n} 组颜色 → {out}")
        self.request_job.emit(req)
