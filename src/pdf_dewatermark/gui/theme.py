"""界面字号、间距与通用样式（全应用统一）。"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QWidget

# —— 字号（pt）——
FS_TITLE = 16
FS_SECTION = 13
FS_BODY = 12
FS_CAPTION = 11

# —— 间距 ——
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16

CTRL_HEIGHT = 32
TOOLBAR_HEIGHT = 40

# 颜色
CLR_TEXT = "#111827"
CLR_MUTED = "#6b7280"
CLR_BORDER = "#e5e7eb"
CLR_SURFACE = "#f9fafb"
CLR_CANVAS = "#1f1f1f"
CLR_ACCENT = "#0ea5e9"


def font_title() -> QFont:
    f = QFont()
    f.setPointSize(FS_TITLE)
    f.setWeight(QFont.DemiBold)
    return f


def font_section() -> QFont:
    f = QFont()
    f.setPointSize(FS_SECTION)
    f.setWeight(QFont.Medium)
    return f


def font_body() -> QFont:
    f = QFont()
    f.setPointSize(FS_BODY)
    f.setWeight(QFont.Normal)
    return f


def font_caption() -> QFont:
    f = QFont()
    f.setPointSize(FS_CAPTION)
    f.setWeight(QFont.Normal)
    return f


def apply_label(label: QLabel, kind: str = "body") -> QLabel:
    mapping = {
        "title": font_title(),
        "section": font_section(),
        "body": font_body(),
        "caption": font_caption(),
    }
    label.setFont(mapping.get(kind, font_body()))
    if kind == "caption":
        label.setStyleSheet(f"color: {CLR_MUTED};")
    elif kind == "section":
        label.setStyleSheet(f"color: {CLR_TEXT};")
    elif kind == "title":
        label.setStyleSheet(f"color: {CLR_TEXT};")
    return label


def style_caption_muted() -> str:
    return f"color: {CLR_MUTED}; font-size: {FS_CAPTION}pt;"


def style_section() -> str:
    return f"color: {CLR_TEXT}; font-size: {FS_SECTION}pt; font-weight: 600;"


def apply_control_font(widget: QWidget) -> None:
    widget.setFont(font_body())


def toolbar_frame_style() -> str:
    return (
        f"QFrame#appToolbar {{"
        f" background: {CLR_SURFACE};"
        f" border-bottom: 1px solid {CLR_BORDER};"
        f"}}"
    )


def doc_toolbar_style() -> str:
    return (
        f"QFrame#docToolbar {{"
        f" background: transparent;"
        f" border-bottom: 1px solid {CLR_BORDER};"
        f"}}"
    )


def empty_state_style() -> str:
    return (
        f"QFrame#emptyState {{"
        f" background: {CLR_SURFACE};"
        f" border: 2px dashed {CLR_BORDER};"
        f" border-radius: 12px;"
        f"}}"
    )


def statusbar_style() -> str:
    return (
        f"QStatusBar {{"
        f" background: {CLR_SURFACE};"
        f" border-top: 1px solid {CLR_BORDER};"
        f" color: {CLR_MUTED};"
        f" font-size: {FS_CAPTION}pt;"
        f"}}"
    )


# 细滚动条宽度（px）。参数抽屉/PDF 预览统一用细条，避免粗条挤占内容
SCROLLBAR_THICK = 8


def thin_scrollbar_style(*, dark: bool = False) -> str:
    """
    细滚动条样式（约 8px）。

    dark=True：PDF 深色预览区——轨道与页面底区分、滑块提高对比，仍保持细条。
    dark=False：浅色参数面板等。
    去掉上下箭头，避免粗控件感。
    """
    t = SCROLLBAR_THICK
    if dark:
        # 预览底约 #2b2b2b：轨道略亮 + 左边/顶部分隔，滑块明显更亮
        track = "#3a3a3a"
        handle = "#9ca3af"
        handle_hover = "#d1d5db"
        handle_press = "#e5e7eb"
        border = "#1f1f1f"
        v_extra = f"border-left: 1px solid {border};"
        h_extra = f"border-top: 1px solid {border};"
    else:
        track = "#f3f4f6"
        handle = "#c5c9d0"
        handle_hover = "#a8adb6"
        handle_press = "#8b919a"
        v_extra = ""
        h_extra = ""
    return f"""
        QScrollBar:vertical {{
            width: {t}px;
            margin: 0px;
            background: {track};
            border: none;
            {v_extra}
        }}
        QScrollBar:horizontal {{
            height: {t}px;
            margin: 0px;
            background: {track};
            border: none;
            {h_extra}
        }}
        QScrollBar::handle:vertical {{
            background: {handle};
            min-height: 32px;
            border-radius: {max(2, t // 2 - 1)}px;
            margin: 2px 1px;
        }}
        QScrollBar::handle:horizontal {{
            background: {handle};
            min-width: 32px;
            border-radius: {max(2, t // 2 - 1)}px;
            margin: 1px 2px;
        }}
        QScrollBar::handle:vertical:hover,
        QScrollBar::handle:horizontal:hover {{
            background: {handle_hover};
        }}
        QScrollBar::handle:vertical:pressed,
        QScrollBar::handle:horizontal:pressed {{
            background: {handle_press};
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical,
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {{
            height: 0px;
            width: 0px;
            border: none;
            background: none;
        }}
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical,
        QScrollBar::add-page:horizontal,
        QScrollBar::sub-page:horizontal {{
            background: transparent;
        }}
    """
