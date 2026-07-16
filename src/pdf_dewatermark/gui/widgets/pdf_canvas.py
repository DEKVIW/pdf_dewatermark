"""PDF 预览画布：大图为主、滚轮缩放、空格/中键拖拽、取色光标。"""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget
from PIL import Image

from ..theme import thin_scrollbar_style

RGB = Tuple[int, int, int]

# 交互模式
MODE_PICK = "pick"
MODE_PAN = "pan"
MODE_RECT = "rect"


def pil_to_qpixmap(image: Image.Image) -> QPixmap:
    """PIL → QPixmap（只在换页时做一次，缩放复用此缓存）。"""
    rgb = image.convert("RGB")
    w, h = rgb.size
    # 使用 bytes 构造；copy 避免底层缓冲释放
    qimg = QImage(rgb.tobytes("raw", "RGB"), w, h, w * 3, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)


def _make_eyedropper_cursor() -> QCursor:
    """
    Photoshop 风格取色吸管光标。
    热点在尖端 (2, 29)，与 PS 吸管一致：点击位置 = 取样像素。
    """
    size = 32
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    # 吸管主体：从左下尖端斜向右上（经典 PS 方向）
    # 尖端
    tip = QPoint(2, 29)
    # 管身路径
    body = [
        QPoint(2, 29),
        QPoint(6, 25),
        QPoint(10, 21),
        QPoint(16, 15),
        QPoint(20, 11),
        QPoint(22, 9),
    ]
    # 白色描边 + 深色填充，提高在深/浅背景上的可见性
    pen_w = QPen(QColor(255, 255, 255), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    pen_b = QPen(QColor(20, 20, 20), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen_w)
    for a, b in zip(body, body[1:]):
        p.drawLine(a, b)
    p.setPen(pen_b)
    for a, b in zip(body, body[1:]):
        p.drawLine(a, b)

    # 滴管头（右上圆 + 小孔）
    p.setBrush(QColor(240, 240, 240))
    p.setPen(QPen(QColor(20, 20, 20), 1.2))
    p.drawEllipse(18, 4, 10, 10)
    p.setBrush(QColor(60, 60, 60))
    p.drawEllipse(21, 7, 4, 4)

    # 取样十字丝（尖端附近，辅助对准）
    p.setPen(QPen(QColor(255, 255, 255), 2))
    p.drawLine(0, 29, 5, 29)
    p.drawLine(2, 27, 2, 31)
    p.setPen(QPen(QColor(0, 120, 215), 1))  # PS 蓝
    p.drawLine(0, 29, 5, 29)
    p.drawLine(2, 27, 2, 31)

    p.end()
    return QCursor(pm, tip.x(), tip.y())


class _ImageLabel(QLabel):
    color_picked = Signal(int, int)  # 源图像素坐标
    rect_drawn = Signal(float, float, float, float)
    pan_delta = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._display: Optional[QPixmap] = None
        self._scale = 1.0
        self._src_w = 0
        self._src_h = 0
        self._mode = MODE_PICK
        self._space_pan = False
        self._panning = False
        self._last_pos = QPoint()
        self._drag_start: Optional[QPoint] = None
        self._drag_current: Optional[QPoint] = None
        self._eyedropper = _make_eyedropper_cursor()
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("background: transparent;")
        self._apply_cursor()

    def set_display(self, pixmap: Optional[QPixmap], scale: float, src_w: int, src_h: int) -> None:
        self._scale = max(0.05, float(scale))
        self._src_w = src_w
        self._src_h = src_h
        self._display = pixmap
        if pixmap is None or pixmap.isNull():
            self.clear()
            self.setFixedSize(200, 200)
            return
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._apply_cursor()

    def set_space_pan(self, on: bool) -> None:
        self._space_pan = on
        self._apply_cursor()

    def _effective_mode(self) -> str:
        if self._space_pan or self._panning:
            return MODE_PAN
        return self._mode

    def _apply_cursor(self) -> None:
        m = self._effective_mode()
        if m == MODE_PAN:
            self.setCursor(Qt.OpenHandCursor if not self._panning else Qt.ClosedHandCursor)
        elif m == MODE_RECT:
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(self._eyedropper)

    def _map_to_source(self, pos: QPoint) -> Optional[Tuple[int, int]]:
        if self._display is None or self._scale <= 0 or self._src_w <= 0:
            return None
        x, y = pos.x(), pos.y()
        if x < 0 or y < 0 or x >= self._display.width() or y >= self._display.height():
            return None
        ix = int(x / self._scale)
        iy = int(y / self._scale)
        if 0 <= ix < self._src_w and 0 <= iy < self._src_h:
            return ix, iy
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        mode = self._effective_mode()
        if event.button() == Qt.MiddleButton or (
            event.button() == Qt.LeftButton and mode == MODE_PAN
        ):
            self._panning = True
            self._last_pos = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._mode == MODE_RECT and not self._space_pan:
            self._drag_start = event.position().toPoint()
            self._drag_current = self._drag_start
            self.update()
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._mode == MODE_PICK and not self._space_pan:
            mapped = self._map_to_source(event.position().toPoint())
            if mapped is not None:
                self.color_picked.emit(mapped[0], mapped[1])
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._panning:
            pos = event.position().toPoint()
            delta = pos - self._last_pos
            self._last_pos = pos
            self.pan_delta.emit(delta.x(), delta.y())
            event.accept()
            return
        if self._mode == MODE_RECT and self._drag_start is not None:
            self._drag_current = event.position().toPoint()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._panning and event.button() in (Qt.MiddleButton, Qt.LeftButton):
            self._panning = False
            self._apply_cursor()
            event.accept()
            return
        if self._mode == MODE_RECT and self._drag_start and event.button() == Qt.LeftButton:
            end = event.position().toPoint()
            a = self._map_to_source(self._drag_start)
            b = self._map_to_source(end)
            self._drag_start = None
            self._drag_current = None
            self.update()
            if a and b and self._src_w > 0 and self._src_h > 0:
                self.rect_drawn.emit(
                    a[0] / self._src_w,
                    a[1] / self._src_h,
                    b[0] / self._src_w,
                    b[1] / self._src_h,
                )
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._mode == MODE_RECT and self._drag_start and self._drag_current:
            painter = QPainter(self)
            pen = QPen(QColor(74, 134, 232), 2, Qt.DashLine)
            painter.setPen(pen)
            x0 = min(self._drag_start.x(), self._drag_current.x())
            y0 = min(self._drag_start.y(), self._drag_current.y())
            painter.drawRect(
                x0,
                y0,
                abs(self._drag_current.x() - self._drag_start.x()),
                abs(self._drag_current.y() - self._drag_start.y()),
            )


class PdfCanvas(QWidget):
    """
    大预览区：
    - 滚轮缩放（无需 Ctrl）
    - 空格 + 拖拽 / 中键拖拽平移（小手）
    - 取色模式使用吸管光标
    """

    color_picked = Signal(int, int)
    rect_drawn = Signal(float, float, float, float)
    scale_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)  # 关键：按图像尺寸滚动，而不是被挤小
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setStyleSheet(
            "QScrollArea { background: #1f1f1f; border: 1px solid #e5e7eb; border-radius: 6px; }"
            + thin_scrollbar_style(dark=True)
        )
        self.scroll.viewport().setStyleSheet("background: #1f1f1f;")
        self.scroll.setFocusPolicy(Qt.StrongFocus)

        self.label = _ImageLabel()
        self.scroll.setWidget(self.label)
        layout.addWidget(self.scroll)

        self._source: Optional[Image.Image] = None
        self._base_pm: Optional[QPixmap] = None
        self._scale = 1.0
        self._mode = MODE_PICK
        self._space_down = False

        self.label.color_picked.connect(self.color_picked.emit)
        self.label.rect_drawn.connect(self.rect_drawn.emit)
        self.label.pan_delta.connect(self._on_pan)

        # 空格拖拽：在 canvas 上装过滤器
        self.scroll.viewport().installEventFilter(self)
        self.installEventFilter(self)

    # ----- public API -----

    def set_image(self, image: Optional[Image.Image], fit: bool = False) -> None:
        """设置源图。fit=True 时按视口宽度适配。同一对象不重复解码。"""
        if image is None:
            self._source = None
            self._base_pm = None
            self.label.set_display(None, 1.0, 0, 0)
            return
        if image is self._source and self._base_pm is not None:
            if fit:
                self.fit_width()
            else:
                self._rebuild_display(smooth=True)
            return
        self._source = image
        self._base_pm = pil_to_qpixmap(image)
        if fit:
            self.fit_width()
        else:
            self._rebuild_display(smooth=True)

    def source_image(self) -> Optional[Image.Image]:
        return self._source

    def set_scale(self, scale: float, smooth: bool = True, anchor: Optional[QPoint] = None) -> None:
        old = self._scale
        self._scale = max(0.08, min(6.0, float(scale)))
        if abs(self._scale - old) < 1e-6 and self.label._display is not None:
            return
        # 以视口中心或锚点为缩放中心
        vp = self.scroll.viewport()
        if anchor is None:
            anchor = QPoint(vp.width() // 2, vp.height() // 2)
        hbar = self.scroll.horizontalScrollBar()
        vbar = self.scroll.verticalScrollBar()
        # 锚点对应的内容坐标（缩放前）
        content_x = hbar.value() + anchor.x()
        content_y = vbar.value() + anchor.y()
        ratio = self._scale / old if old > 1e-6 else 1.0

        self._rebuild_display(smooth=smooth)

        # 恢复锚点
        new_x = int(content_x * ratio - anchor.x())
        new_y = int(content_y * ratio - anchor.y())
        hbar.setValue(max(0, new_x))
        vbar.setValue(max(0, new_y))
        self.scale_changed.emit(self._scale)

    def scale(self) -> float:
        return self._scale

    def fit_width(self) -> None:
        if self._base_pm is None:
            return
        vw = max(1, self.scroll.viewport().width() - 16)
        self._scale = max(0.08, min(6.0, vw / self._base_pm.width()))
        self._rebuild_display(smooth=True)
        self.scale_changed.emit(self._scale)

    def fit_page(self) -> None:
        if self._base_pm is None:
            return
        vw = max(1, self.scroll.viewport().width() - 16)
        vh = max(1, self.scroll.viewport().height() - 16)
        sx = vw / self._base_pm.width()
        sy = vh / self._base_pm.height()
        self._scale = max(0.08, min(6.0, min(sx, sy)))
        self._rebuild_display(smooth=True)
        self.scale_changed.emit(self._scale)

    def set_pick_enabled(self, enabled: bool) -> None:
        self.set_mode(MODE_PICK if enabled else MODE_PAN)

    def set_draw_rect_mode(self, enabled: bool) -> None:
        self.set_mode(MODE_RECT if enabled else MODE_PICK)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self.label.set_mode(mode)

    def mode(self) -> str:
        return self._mode

    def pick_color_at(self, x: int, y: int) -> Optional[RGB]:
        if self._source is None:
            return None
        if 0 <= x < self._source.width and 0 <= y < self._source.height:
            px = self._source.getpixel((x, y))
            if isinstance(px, int):
                return (px, px, px)
            return (int(px[0]), int(px[1]), int(px[2]))
        return None

    # ----- internals -----

    def _rebuild_display(self, smooth: bool = True) -> None:
        if self._base_pm is None:
            self.label.set_display(None, self._scale, 0, 0)
            return
        w = max(1, int(self._base_pm.width() * self._scale))
        h = max(1, int(self._base_pm.height() * self._scale))
        # 缩放过程用快速变换，定稿用平滑
        hint = Qt.SmoothTransformation if smooth else Qt.FastTransformation
        if w == self._base_pm.width() and h == self._base_pm.height():
            pm = self._base_pm
        else:
            pm = self._base_pm.scaled(w, h, Qt.IgnoreAspectRatio, hint)
        src_w = self._source.width if self._source else self._base_pm.width()
        src_h = self._source.height if self._source else self._base_pm.height()
        self.label.set_display(pm, self._scale, src_w, src_h)

    def _on_pan(self, dx: int, dy: int) -> None:
        hbar = self.scroll.horizontalScrollBar()
        vbar = self.scroll.verticalScrollBar()
        hbar.setValue(hbar.value() - dx)
        vbar.setValue(vbar.value() - dy)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        # 滚轮直接缩放（PDF 阅读器常见）；Shift+滚轮横向滚动
        if event.modifiers() & Qt.ShiftModifier:
            hbar = self.scroll.horizontalScrollBar()
            hbar.setValue(hbar.value() - int(event.angleDelta().y() * 0.5))
            event.accept()
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.12 if delta > 0 else 1 / 1.12
        # 以鼠标在视口中的位置为锚点
        pos = event.position().toPoint()
        # 坐标相对 viewport
        global_pos = self.mapToGlobal(pos)
        vp_pos = self.scroll.viewport().mapFromGlobal(global_pos)
        self.set_scale(self._scale * factor, smooth=False, anchor=vp_pos)
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_down = True
            self.label.set_space_pan(True)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_down = False
            self.label.set_space_pan(False)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        et = event.type()
        # 视口滚轮交给 canvas
        if obj is self.scroll.viewport() and et == event.Type.Wheel:
            self.wheelEvent(event)
            return True
        # 空格在子控件上也生效
        if et == event.Type.KeyPress and isinstance(event, QKeyEvent):
            if event.key() == Qt.Key_Space and not event.isAutoRepeat():
                self._space_down = True
                self.label.set_space_pan(True)
                return True
        if et == event.Type.KeyRelease and isinstance(event, QKeyEvent):
            if event.key() == Qt.Key_Space and not event.isAutoRepeat():
                self._space_down = False
                self.label.set_space_pan(False)
                return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(800, 600)
