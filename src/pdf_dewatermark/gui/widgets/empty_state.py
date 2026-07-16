"""空状态：未打开文档时的规范引导区（点击 / 拖入）。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import PrimaryPushButton

from .. import icons as I
from ..theme import (
    CTRL_HEIGHT,
    SPACE_MD,
    SPACE_SM,
    apply_control_font,
    apply_label,
    empty_state_style,
    font_title,
)


class EmptyState(QFrame):
    """居中空状态：主操作「打开」+ 拖放 PDF。"""

    open_clicked = Signal()
    file_dropped = Signal(str)

    def __init__(
        self,
        title: str = "打开 PDF 开始处理",
        hint: str = "将文件拖到此处，或使用菜单「文件 → 打开」",
        button_text: str = "打开 PDF…",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("emptyState")
        self.setStyleSheet(empty_state_style())
        self.setAcceptDrops(True)
        self.setMinimumHeight(280)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(SPACE_MD)
        lay.setContentsMargins(SPACE_MD * 2, SPACE_MD * 2, SPACE_MD * 2, SPACE_MD * 2)

        icon_lab = QLabel()
        try:
            pm = I.ICO_DOCUMENT.icon().pixmap(48, 48)
            icon_lab.setPixmap(pm)
            icon_lab.setAlignment(Qt.AlignCenter)
            lay.addWidget(icon_lab, 0, Qt.AlignCenter)
        except Exception:
            pass

        self.title_lab = QLabel(title)
        self.title_lab.setFont(font_title())
        self.title_lab.setAlignment(Qt.AlignCenter)
        self.title_lab.setStyleSheet("color: #111827; background: transparent; border: none;")
        lay.addWidget(self.title_lab)

        self.hint_lab = QLabel(hint)
        apply_label(self.hint_lab, "caption")
        self.hint_lab.setAlignment(Qt.AlignCenter)
        self.hint_lab.setWordWrap(True)
        self.hint_lab.setStyleSheet(
            self.hint_lab.styleSheet() + " background: transparent; border: none;"
        )
        lay.addWidget(self.hint_lab)

        self.open_btn = PrimaryPushButton(button_text)
        self.open_btn.setIcon(I.ICO_OPEN.icon())
        apply_control_font(self.open_btn)
        self.open_btn.setFixedHeight(CTRL_HEIGHT)
        self.open_btn.setMinimumWidth(160)
        self.open_btn.clicked.connect(self.open_clicked.emit)
        lay.addWidget(self.open_btn, 0, Qt.AlignCenter)

        tip = QLabel("快捷键 Ctrl+O")
        apply_label(tip, "caption")
        tip.setAlignment(Qt.AlignCenter)
        tip.setStyleSheet(tip.styleSheet() + " background: transparent; border: none;")
        lay.addWidget(tip)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf") and Path(path).is_file():
                self.file_dropped.emit(path)
                event.acceptProposedAction()
                return
        event.ignore()
