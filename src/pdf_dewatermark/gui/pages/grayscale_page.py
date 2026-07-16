"""灰度转换页。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SpinBox,
    StrongBodyLabel,
)

from ...models import GrayscaleParams
from ...paths import default_output_path
from .. import icons as I
from ..theme import CTRL_HEIGHT, apply_control_font


class GrayscalePage(QWidget):
    status = Signal(str)
    request_job = Signal(object)
    log = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = CardWidget()
        lay = QVBoxLayout(card)
        lay.addWidget(StrongBodyLabel("彩色 PDF → 灰度"))
        lay.addWidget(
            BodyLabel(
                "将每一页渲染为灰度图后重新生成 PDF。"
                "适合浅色水印与正文色差主要体现在亮度上的文档；"
                "转换后为图片型 PDF，不可选中文字。"
            )
        )

        form = QFormLayout()
        row = QHBoxLayout()
        self.input_edit = LineEdit()
        self.input_edit.setPlaceholderText("选择输入 PDF…")
        browse_in = PushButton("浏览…")
        browse_in.clicked.connect(self._browse_in)
        row.addWidget(self.input_edit, 1)
        row.addWidget(browse_in)
        form.addRow("输入", row)

        row2 = QHBoxLayout()
        self.output_edit = LineEdit()
        self.output_edit.setPlaceholderText("输出路径（可自动生成）")
        browse_out = PushButton("浏览…")
        browse_out.clicked.connect(self._browse_out)
        row2.addWidget(self.output_edit, 1)
        row2.addWidget(browse_out)
        form.addRow("输出", row2)

        self.dpi = SpinBox()
        self.dpi.setRange(72, 600)
        self.dpi.setValue(200)
        form.addRow("DPI", self.dpi)
        lay.addLayout(form)

        self.run_btn = PrimaryPushButton("开始转换")
        self.run_btn.setIcon(I.ICO_PLAY.icon())
        apply_control_font(self.run_btn)
        self.run_btn.setFixedHeight(CTRL_HEIGHT)
        self.run_btn.clicked.connect(self.run)
        lay.addWidget(self.run_btn)
        root.addWidget(card)
        root.addStretch(1)

    def _browse_in(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 PDF", "", "PDF (*.pdf)")
        if path:
            self.input_edit.setText(path)
            if not self.output_edit.text().strip():
                self.output_edit.setText(str(default_output_path(path, suffix="灰度")))

    def _browse_out(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "保存灰度 PDF", "", "PDF (*.pdf)")
        if path:
            self.output_edit.setText(path)

    def run(self) -> None:
        from ..workers import JobRequest

        src = self.input_edit.text().strip()
        if not src or not Path(src).is_file():
            self.status.emit("请选择有效的输入 PDF")
            return
        out = self.output_edit.text().strip() or str(default_output_path(src, suffix="灰度"))
        self.output_edit.setText(out)
        req = JobRequest(
            kind="grayscale",
            input_path=src,
            output_path=out,
            gray_params=GrayscaleParams(dpi=int(self.dpi.value())),
        )
        self.log.emit(f"灰度转换 → {out}")
        self.request_job.emit(req)
