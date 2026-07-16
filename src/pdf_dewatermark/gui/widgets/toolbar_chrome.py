"""文档/应用工具栏紧凑样式（仅布局，不改业务逻辑）。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget
from qfluentwidgets import PrimaryPushButton, PushButton, TransparentToolButton

from ..theme import CTRL_HEIGHT, apply_control_font

# 工具栏图标按钮统一边长（居中）
TOOL_BTN = 34


def make_tool_button(icon, tooltip: str, parent: QWidget | None = None) -> TransparentToolButton:
    """
    Fluent 透明工具按钮：图标在方框内居中显示。
    icon 传 FluentIcon 枚举（如 I.ICO_ZOOM_IN），不要 .icon()。
    """
    # TransparentToolButton(FluentIcon, parent)
    try:
        btn = TransparentToolButton(icon, parent)
    except TypeError:
        btn = TransparentToolButton(parent)
        try:
            btn.setIcon(icon.icon() if hasattr(icon, "icon") else icon)
        except Exception:
            pass
    btn.setToolTip(tooltip)
    btn.setAccessibleName(tooltip)
    btn.setFixedSize(TOOL_BTN, TOOL_BTN)
    btn.setIconSize(QSize(18, 18))
    return btn


def make_text_tool_button(
    text: str,
    tooltip: str,
    parent: QWidget | None = None,
    *,
    primary: bool = False,
    icon=None,
) -> PushButton:
    """短文案按钮（如「全部」），可选图标。"""
    if primary:
        btn = PrimaryPushButton(text, parent)
        if icon is not None:
            try:
                btn.setIcon(icon.icon() if hasattr(icon, "icon") else icon)
            except Exception:
                pass
    else:
        btn = PushButton(text, parent)
        if icon is not None:
            try:
                btn.setIcon(icon.icon() if hasattr(icon, "icon") else icon)
            except Exception:
                pass
    btn.setToolTip(tooltip)
    btn.setAccessibleName(tooltip)
    btn.setFixedHeight(CTRL_HEIGHT)
    apply_control_font(btn)
    return btn


class ElideLabel(QLabel):
    """单行省略号标签，完整文本在 ToolTip。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumWidth(40)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)

    def set_full_text(self, text: str) -> None:
        self._full = text or ""
        self.setToolTip(self._full)
        self._apply_elide()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        if not self._full:
            super().setText("")
            return
        fm = QFontMetrics(self.font())
        w = max(20, self.width() - 4)
        super().setText(fm.elidedText(self._full, Qt.ElideMiddle, w))
