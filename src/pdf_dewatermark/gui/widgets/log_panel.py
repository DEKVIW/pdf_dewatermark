"""底部日志面板。"""

from __future__ import annotations

from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

from ..theme import SPACE_XS, apply_label, font_caption


class LogPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_XS)

        from PySide6.QtWidgets import QLabel

        self.title = QLabel("运行日志")
        apply_label(self.title, "section")
        layout.addWidget(self.title)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(2000)
        font = QFont("Consolas", 10)
        if not font.exactMatch():
            font = font_caption()
            font.setFamilies(["Consolas", "Cascadia Mono", "Microsoft YaHei UI"])
            font.setPointSize(10)
        self.view.setFont(font)
        self.view.setMinimumHeight(40)
        self.view.setMaximumHeight(72)
        self.view.setPlaceholderText("处理进度与提示会显示在这里…")
        self.view.setStyleSheet(
            "QPlainTextEdit { background: #f9fafb; border: 1px solid #e5e7eb;"
            " border-radius: 6px; padding: 6px; color: #374151; }"
        )
        layout.addWidget(self.view)

    def append(self, text: str) -> None:
        self.view.appendPlainText(text.rstrip())
        self.view.moveCursor(QTextCursor.End)

    def clear(self) -> None:
        self.view.clear()
