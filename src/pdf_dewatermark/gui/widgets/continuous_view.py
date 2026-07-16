"""
连续滚动 PDF 视图。

画质策略（对齐常见 PDF 阅读器）：
- 按屏幕 devicePixelRatio 以物理像素渲染，避免高分屏发糊
- 效果预览与原图同分辨率（不再半分辨率放大）
- 缩放时保留旧图、平滑拉伸过渡，防抖后再精渲（避免清晰↔模糊抖动）
- 取色映射到物理像素 1:1 缓冲（导出精度仍走独立 DPI 管线）
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import fitz
from PIL import Image
from PySide6.QtCore import (
    QObject,
    QPoint,
    QRect,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import QScrollBar, QSizePolicy, QWidget

from ..theme import SCROLLBAR_THICK, thin_scrollbar_style
from .pdf_canvas import MODE_PAN, MODE_PICK, MODE_RECT, _make_eyedropper_cursor, pil_to_qpixmap

RGB = Tuple[int, int, int]
ProcessFn = Callable[[Image.Image, int], Image.Image]

# 逻辑宽度上限（物理像素 = 逻辑 × DPR）
MAX_PAGE_DISP_W = 2800
HQ_DEBOUNCE_MS = 60
SCROLL_RENDER_MS = 24
# 预览区细滚动条占位（与 theme.SCROLLBAR_THICK 一致）
_SB = SCROLLBAR_THICK
# 像素预算（物理像素总量）
CACHE_MAX_PIXELS = 64_000_000
EFFECT_CACHE_MAX_PIXELS = 48_000_000
SRC_PIL_MAX_PIXELS = 80_000_000
SRC_PIL_MIN_KEEP = 2


@dataclass
class _PageGeom:
    y: int
    width: int
    height: int
    pdf_w: float
    pdf_h: float


class _LRU:
    """按像素总量淘汰的 LRU。"""

    def __init__(self, max_pixels: int = CACHE_MAX_PIXELS, min_keep: int = 1) -> None:
        self.max_pixels = max(1_000_000, int(max_pixels))
        self.min_keep = max(1, int(min_keep))
        self._data: "OrderedDict[int, QPixmap]" = OrderedDict()
        self._cost: "OrderedDict[int, int]" = OrderedDict()
        self._total = 0

    def get(self, key: int) -> Optional[QPixmap]:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        self._cost.move_to_end(key)
        return self._data[key]

    def put(self, key: int, value: QPixmap) -> None:
        cost = max(1, int(value.width()) * int(value.height()))
        if key in self._data:
            self._total -= self._cost.pop(key, 0)
            del self._data[key]
        self._data[key] = value
        self._cost[key] = cost
        self._total += cost
        self._evict()

    def _evict(self) -> None:
        while self._total > self.max_pixels and len(self._data) > self.min_keep:
            k, _ = self._data.popitem(last=False)
            self._total -= self._cost.pop(k, 0)

    def clear(self) -> None:
        self._data.clear()
        self._cost.clear()
        self._total = 0

    def items(self):
        return list(self._data.items())

    def __contains__(self, key: int) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)


class _Bridge(QObject):
    effect_done = Signal(int, int, object)  # gen, page, QPixmap


class _EffectTask(QRunnable):
    """全分辨率效果（与屏幕栅格同尺寸，不再半分辨率糊化）。"""

    def __init__(
        self,
        bridge: _Bridge,
        gen: int,
        page_index: int,
        img: Image.Image,
        process_fn: ProcessFn,
        dpr: float,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self.bridge = bridge
        self.gen = gen
        self.page_index = page_index
        self.img = img
        self.process_fn = process_fn
        self.dpr = dpr

    def run(self) -> None:  # noqa: N802
        try:
            src = self.img
            out = self.process_fn(src, self.page_index)
            if out.size != src.size:
                out = out.resize(src.size, Image.Resampling.LANCZOS)
            pm = pil_to_qpixmap(out)
            pm.setDevicePixelRatio(self.dpr)
            self.bridge.effect_done.emit(self.gen, self.page_index, pm)
        except Exception:
            pass


class ContinuousPdfView(QWidget):
    page_changed = Signal(int)
    scale_changed = Signal(float)
    color_picked = Signal(int, int, int)
    color_sampled = Signal(int, int, int, int)
    rect_drawn = Signal(int, float, float, float, float)
    status = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(200, 200)
        self.setStyleSheet("background: #2b2b2b;")

        self._doc: Optional[fitz.Document] = None
        self._page_count = 0
        self._geoms: List[_PageGeom] = []
        self._content_h = 0
        self._content_w = 0
        self._scroll_x = 0
        self._scroll_y = 0

        self._page_disp_w = 800
        self._base_fit_w = 800
        self._gap = 12

        self._cache = _LRU(CACHE_MAX_PIXELS, min_keep=2)
        self._effect_cache = _LRU(EFFECT_CACHE_MAX_PIXELS, min_keep=1)
        self._src_pil: "OrderedDict[int, Image.Image]" = OrderedDict()
        self._src_pil_pixels = 0
        self._effect_inflight: set[int] = set()

        self._show_effect = False
        self._process_fn: Optional[ProcessFn] = None

        self._mode = MODE_PICK
        self._space_pan = False
        self._panning = False
        self._last_pos = QPoint()
        self._drag_start: Optional[QPoint] = None
        self._drag_current: Optional[QPoint] = None
        self._eyedropper = _make_eyedropper_cursor()

        self._gen = 0
        self._pool = QThreadPool.globalInstance()
        self._bridge = _Bridge()
        self._bridge.effect_done.connect(self._on_effect_done)

        self._hq_timer = QTimer(self)
        self._hq_timer.setSingleShot(True)
        self._hq_timer.setInterval(HQ_DEBOUNCE_MS)
        self._hq_timer.timeout.connect(self._run_hq_render)

        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(SCROLL_RENDER_MS)
        self._scroll_timer.timeout.connect(self._run_hq_render)

        self._effect_timer = QTimer(self)
        self._effect_timer.setSingleShot(True)
        self._effect_timer.setInterval(180)
        self._effect_timer.timeout.connect(self._flush_effects)

        self._current_page = 0

        # 细滚动条：贴边子控件，可拖滑块快速定位（类似常见 PDF 阅读器）
        sb_css = thin_scrollbar_style(dark=True)
        self._vbar = QScrollBar(Qt.Vertical, self)
        self._hbar = QScrollBar(Qt.Horizontal, self)
        self._vbar.setStyleSheet(sb_css)
        self._hbar.setStyleSheet(sb_css)
        # 强制箭头光标，避免继承预览区的吸管/十字
        self._vbar.setCursor(Qt.ArrowCursor)
        self._hbar.setCursor(Qt.ArrowCursor)
        self._vbar.setContextMenuPolicy(Qt.NoContextMenu)
        self._hbar.setContextMenuPolicy(Qt.NoContextMenu)
        self._vbar.valueChanged.connect(self._on_vbar_changed)
        self._hbar.valueChanged.connect(self._on_hbar_changed)
        self._vbar.hide()
        self._hbar.hide()

        self._last_cursor_key: Optional[str] = None
        self._apply_cursor()

    # ----- public -----

    def set_document(self, doc: Optional[fitz.Document]) -> None:
        self._bump_gen()
        self._doc = doc
        self._page_count = len(doc) if doc else 0
        self._clear_all_caches()
        self._scroll_x = 0
        self._scroll_y = 0
        self._rebuild_layout()
        self._layout_scrollbars()
        self._sync_scrollbars()
        self._run_hq_render()
        self.update()

    def set_process_fn(self, fn: Optional[ProcessFn]) -> None:
        self._process_fn = fn
        self.invalidate_effects(immediate=False)

    def set_show_effect(self, on: bool) -> None:
        self._show_effect = bool(on)
        if self._show_effect:
            self._queue_effects_for_visible()
        self.update()

    def fit_width(self) -> None:
        vw = max(100, self._view_w() - 24)
        new_w = min(vw, MAX_PAGE_DISP_W)
        anchor = QPoint(self._view_w() // 2, self._view_h() // 2)
        self._zoom_to_page_width(new_w, reset_base=True, anchor_viewport=anchor)

    def set_scale(self, scale: float, anchor_viewport: Optional[QPoint] = None) -> None:
        scale = max(0.25, min(4.0, float(scale)))
        if self._base_fit_w <= 0:
            self._base_fit_w = max(100, self._view_w() - 24)
        new_w = min(MAX_PAGE_DISP_W, max(80, int(round(self._base_fit_w * scale))))
        if anchor_viewport is None:
            anchor_viewport = QPoint(self._view_w() // 2, self._view_h() // 2)
        self._zoom_to_page_width(new_w, reset_base=False, anchor_viewport=anchor_viewport)

    def scale(self) -> float:
        if self._base_fit_w <= 0:
            return 1.0
        return self._page_disp_w / self._base_fit_w

    def zoom_by(self, factor: float, anchor_viewport: Optional[QPoint] = None) -> None:
        if anchor_viewport is None:
            anchor_viewport = QPoint(max(0, self._view_w() // 2), max(0, self._view_h() // 2))
        self.set_scale(self.scale() * factor, anchor_viewport=anchor_viewport)

    def goto_page(self, index: int, center: bool = True) -> None:
        if not self._geoms or index < 0 or index >= len(self._geoms):
            return
        g = self._geoms[index]
        if center:
            self._scroll_y = max(0, g.y - max(0, (self._view_h() - g.height) // 2))
        else:
            self._scroll_y = g.y
        self._clamp_scroll()
        self._sync_scrollbars()
        if index != self._current_page:
            self._current_page = index
            self.page_changed.emit(index)
        else:
            self._current_page = index
        self._schedule_scroll_render()
        self.update()

    def current_page(self) -> int:
        return self._current_page

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._last_cursor_key = None
        self._apply_cursor()

    def set_pick_enabled(self, enabled: bool) -> None:
        self.set_mode(MODE_PICK if enabled else MODE_PAN)

    def set_draw_rect_mode(self, enabled: bool) -> None:
        self.set_mode(MODE_RECT if enabled else MODE_PICK)

    def invalidate_effects(self, immediate: bool = False) -> None:
        """参数/取色变化。默认防抖；immediate=True 立刻排队。"""
        self._effect_cache.clear()
        self._effect_inflight.clear()
        self.update()
        if not self._show_effect or self._process_fn is None:
            return
        if immediate:
            self._effect_timer.stop()
            self._flush_effects()
        else:
            self._effect_timer.start()

    def get_page_image(self, page_index: int, processed: bool = False) -> Optional[Image.Image]:
        if processed and self._process_fn and page_index in self._src_pil:
            try:
                return self._process_fn(self._src_pil[page_index].copy(), page_index)
            except Exception:
                pass
        if page_index in self._src_pil:
            return self._src_pil[page_index]
        self._ensure_page_raster(page_index)
        return self._src_pil.get(page_index)

    # ----- viewport / scrollbars -----

    def _view_w(self) -> int:
        """内容视口宽（扣除右侧细竖条）。"""
        if self._doc is None:
            return max(1, self.width())
        return max(1, self.width() - _SB)

    def _view_h(self) -> int:
        """内容视口高（扣除底部细横条）。"""
        if self._doc is None:
            return max(1, self.height())
        return max(1, self.height() - _SB)

    def _layout_scrollbars(self) -> None:
        if self._doc is None:
            self._vbar.hide()
            self._hbar.hide()
            return
        w, h = self.width(), self.height()
        t = _SB
        # 右下角交叉：竖条到底上边、横条到右边
        self._vbar.setGeometry(w - t, 0, t, max(1, h - t))
        self._hbar.setGeometry(0, h - t, max(1, w - t), t)
        self._vbar.show()
        self._hbar.show()
        self._vbar.raise_()
        self._hbar.raise_()

    def _sync_scrollbars(self) -> None:
        if self._doc is None:
            return
        vw, vh = self._view_w(), self._view_h()
        max_y = max(0, self._content_h - vh)
        max_x = max(0, self._content_w - vw)

        self._vbar.blockSignals(True)
        self._vbar.setRange(0, max_y)
        self._vbar.setPageStep(max(1, vh))
        self._vbar.setSingleStep(48)
        self._vbar.setValue(int(max(0, min(self._scroll_y, max_y))))
        self._vbar.setEnabled(max_y > 0)
        self._vbar.blockSignals(False)

        self._hbar.blockSignals(True)
        self._hbar.setRange(0, max_x)
        self._hbar.setPageStep(max(1, vw))
        self._hbar.setSingleStep(32)
        self._hbar.setValue(int(max(0, min(self._scroll_x, max_x))))
        self._hbar.setEnabled(max_x > 0)
        self._hbar.blockSignals(False)

    def _on_vbar_changed(self, value: int) -> None:
        if int(value) == int(self._scroll_y):
            return
        self._scroll_y = int(value)
        self._update_current_page()
        self._schedule_scroll_render()
        self.update()

    def _on_hbar_changed(self, value: int) -> None:
        if int(value) == int(self._scroll_x):
            return
        self._scroll_x = int(value)
        self._schedule_scroll_render()
        self.update()

    def _after_scroll(self, *, render: bool = True) -> None:
        self._clamp_scroll()
        self._sync_scrollbars()
        self._update_current_page()
        if render:
            self._schedule_scroll_render()
        self.update()

    # ----- DPR / raster sizing -----

    def _dpr(self) -> float:
        try:
            d = float(self.devicePixelRatioF())
        except Exception:
            d = 1.0
        return max(1.0, d)

    def _target_raster_size(self, index: int) -> Tuple[int, int]:
        """物理像素尺寸（逻辑布局 × DPR），与阅读器「屏上所见」一致。"""
        dpr = self._dpr()
        if 0 <= index < len(self._geoms):
            g = self._geoms[index]
            tw = max(1, int(round(g.width * dpr)))
            th = max(1, int(round(g.height * dpr)))
            return tw, th
        tw = max(1, int(round(self._page_disp_w * dpr)))
        return tw, tw

    def _pm_matches_geom(self, pm: QPixmap, index: int) -> bool:
        if index < 0 or index >= len(self._geoms) or pm is None or pm.isNull():
            return False
        g = self._geoms[index]
        dpr = float(pm.devicePixelRatio() or 1.0)
        lw = pm.width() / dpr
        lh = pm.height() / dpr
        return abs(lw - g.width) <= 1.5 and abs(lh - g.height) <= 1.5

    def _to_display_pm(self, img: Image.Image) -> QPixmap:
        pm = pil_to_qpixmap(img)
        pm.setDevicePixelRatio(self._dpr())
        return pm

    # ----- zoom with anchor -----

    def _capture_anchor(self, vx: int, vy: int) -> Tuple[Optional[int], float, float, float]:
        content_y = self._scroll_y + vy
        content_y_ratio = content_y / max(1, self._content_h)
        hit = self._hit_page(QPoint(vx, vy))
        if hit is not None:
            pi, lx, ly = hit
            g = self._geoms[pi]
            return pi, lx / max(1, g.width), ly / max(1, g.height), content_y_ratio
        return None, 0.5, 0.5, content_y_ratio

    def _restore_anchor(
        self,
        page_index: Optional[int],
        fx: float,
        fy: float,
        content_y_ratio: float,
        vx: int,
        vy: int,
    ) -> None:
        if page_index is not None and 0 <= page_index < len(self._geoms):
            g = self._geoms[page_index]
            content_y = g.y + fy * g.height
            content_x = fx * g.width
            center = max(0, (self._view_w() - self._page_disp_w) // 2)
            self._scroll_x = int(round(center + content_x - vx))
            self._scroll_y = int(round(content_y - vy))
            self._current_page = page_index
        else:
            self._scroll_y = int(round(content_y_ratio * self._content_h - vy))
            self._scroll_x = 0
        self._clamp_scroll()
        self._sync_scrollbars()
        self._update_current_page()

    def _zoom_to_page_width(
        self,
        new_w: int,
        *,
        reset_base: bool,
        anchor_viewport: QPoint,
    ) -> None:
        if new_w == self._page_disp_w and not reset_base:
            return
        vx, vy = int(anchor_viewport.x()), int(anchor_viewport.y())
        if not self._geoms:
            self._page_disp_w = new_w
            if reset_base:
                self._base_fit_w = new_w
            self.scale_changed.emit(self.scale())
            self.update()
            return

        pi, fx, fy, y_ratio = self._capture_anchor(vx, vy)
        self._page_disp_w = new_w
        if reset_base:
            self._base_fit_w = new_w

        # 缩放：保留旧 pixmap，paint 时平滑拉伸；防抖后再精渲
        # （不再 Fast 生成模糊占位、不再立刻清空缓存 → 消除清晰/模糊抖动）
        self._bump_gen()
        self._effect_cache.clear()
        self._effect_inflight.clear()
        self._rebuild_layout()
        self._restore_anchor(pi, fx, fy, y_ratio, vx, vy)
        self._layout_scrollbars()
        self._sync_scrollbars()
        self.scale_changed.emit(self.scale())
        self.update()
        self._hq_timer.start()

    # ----- cache -----

    def _bump_gen(self) -> None:
        self._gen += 1
        self._effect_inflight.clear()

    def _clear_render_caches(self) -> None:
        self._cache.clear()
        self._effect_cache.clear()
        self._src_pil.clear()
        self._src_pil_pixels = 0

    def _clear_all_caches(self) -> None:
        self._clear_render_caches()

    def _rebuild_layout(self) -> None:
        self._geoms = []
        if not self._doc or self._page_count == 0:
            self._content_h = 0
            self._content_w = self._page_disp_w
            return
        y = self._gap
        for i in range(self._page_count):
            page = self._doc[i]
            pw, ph = page.rect.width, page.rect.height
            if pw <= 0:
                pw, ph = 595.0, 842.0
            h = max(1, int(round(self._page_disp_w * (ph / pw))))
            self._geoms.append(
                _PageGeom(y=y, width=self._page_disp_w, height=h, pdf_w=pw, pdf_h=ph)
            )
            y += h + self._gap
        self._content_h = y
        self._content_w = self._page_disp_w + 24
        self._clamp_scroll()

    def _clamp_scroll(self) -> None:
        max_y = max(0, self._content_h - self._view_h())
        max_x = max(0, self._content_w - self._view_w())
        self._scroll_y = int(max(0, min(self._scroll_y, max_y)))
        self._scroll_x = int(max(0, min(self._scroll_x, max_x)))

    def _page_left(self) -> int:
        return max(0, (self._view_w() - self._page_disp_w) // 2) - self._scroll_x

    def _visible_range(self, buffer: int = 1) -> Tuple[int, int]:
        if not self._geoms:
            return 0, -1
        top = self._scroll_y
        bottom = self._scroll_y + self._view_h()
        first, last = 0, len(self._geoms) - 1
        for i, g in enumerate(self._geoms):
            if g.y + g.height >= top:
                first = i
                break
        for i in range(len(self._geoms) - 1, -1, -1):
            if self._geoms[i].y <= bottom:
                last = i
                break
        first = max(0, first - buffer)
        last = min(len(self._geoms) - 1, last + buffer)
        return first, last

    def _update_current_page(self) -> None:
        if not self._geoms:
            return
        mid = self._scroll_y + self._view_h() // 2
        best = 0
        for i, g in enumerate(self._geoms):
            if g.y <= mid < g.y + g.height + self._gap:
                best = i
                break
            if mid >= g.y:
                best = i
        if best != self._current_page:
            self._current_page = best
            self.page_changed.emit(best)

    # ----- render pipeline -----

    def _src_pil_touch(self, index: int) -> None:
        if index in self._src_pil:
            self._src_pil.move_to_end(index)

    def _src_pil_put(self, index: int, img: Image.Image) -> None:
        w, h = img.size
        cost = max(1, w * h)
        if index in self._src_pil:
            old = self._src_pil.pop(index)
            ow, oh = old.size
            self._src_pil_pixels -= max(1, ow * oh)
        self._src_pil[index] = img
        self._src_pil_pixels += cost
        self._src_pil_evict()

    def _src_pil_evict(self) -> None:
        if self._src_pil_pixels <= SRC_PIL_MAX_PIXELS:
            return
        first, last = self._visible_range(buffer=1)
        for k in list(self._src_pil.keys()):
            if self._src_pil_pixels <= SRC_PIL_MAX_PIXELS:
                break
            if k < first or k > last:
                old = self._src_pil.pop(k)
                ow, oh = old.size
                self._src_pil_pixels -= max(1, ow * oh)
        while self._src_pil_pixels > SRC_PIL_MAX_PIXELS and len(self._src_pil) > SRC_PIL_MIN_KEEP:
            k, old = self._src_pil.popitem(last=False)
            ow, oh = old.size
            self._src_pil_pixels -= max(1, ow * oh)

    def _ensure_page_raster(self, index: int) -> Optional[Image.Image]:
        if not self._doc or index < 0 or index >= self._page_count:
            return None
        tw, th = self._target_raster_size(index)
        if index in self._src_pil:
            img = self._src_pil[index]
            if img.size == (tw, th):
                self._src_pil_touch(index)
                return img

        page = self._doc[index]
        pw = page.rect.width or 595.0
        # 直接按目标物理宽度渲染，避免先低后放
        zoom = tw / pw
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        try:
            samples = pix.samples_mv if hasattr(pix, "samples_mv") else pix.samples
            img = Image.frombytes("RGB", (pix.width, pix.height), samples)
        finally:
            pix = None  # noqa: F841
        if img.size != (tw, th):
            # 仅纠正 1px 级偏差；用 LANCZOS 保清晰
            img = img.resize((tw, th), Image.Resampling.LANCZOS)
        self._src_pil_put(index, img)
        if index % 8 == 0:
            try:
                fitz.TOOLS.store_shrink(100)
            except Exception:
                pass
        return img

    def _render_original(self, index: int) -> Optional[QPixmap]:
        if index in self._cache:
            pm = self._cache.get(index)
            if pm is not None and self._pm_matches_geom(pm, index):
                return pm
        img = self._ensure_page_raster(index)
        if img is None:
            return None
        pm = self._to_display_pm(img)
        self._cache.put(index, pm)
        return pm

    def _queue_effect(self, index: int) -> None:
        if not self._show_effect or self._process_fn is None:
            return
        if index in self._effect_cache:
            pm = self._effect_cache.get(index)
            if pm is not None and self._pm_matches_geom(pm, index):
                return
            # 尺寸过期：丢弃，重新算
            # （LRU 无专用 delete，覆盖 put 即可；先不取）
        if index in self._effect_inflight:
            return
        img = self._ensure_page_raster(index)
        if img is None:
            return
        self._effect_inflight.add(index)
        task = _EffectTask(
            self._bridge,
            self._gen,
            index,
            img,
            self._process_fn,
            dpr=self._dpr(),
        )
        self._pool.start(task)

    def _on_effect_done(self, gen: int, page_index: int, pm: object) -> None:
        self._effect_inflight.discard(page_index)
        if gen != self._gen:
            return
        if not isinstance(pm, QPixmap):
            return
        # 任务里已 setDevicePixelRatio；再保险一次
        if abs(float(pm.devicePixelRatio() or 1.0) - self._dpr()) > 0.01:
            pm.setDevicePixelRatio(self._dpr())
        self._effect_cache.put(page_index, pm)
        self.update()

    def _run_hq_render(self) -> None:
        """主线程：按当前逻辑宽 × DPR 精渲原图；效果丢线程池。"""
        if not self._doc:
            return
        first, last = self._visible_range(buffer=1)
        if last < first:
            return
        for i in range(first, last + 1):
            self._render_original(i)
        self.update()
        if self._show_effect and self._process_fn is not None:
            self._queue_effects_for_visible()

    def _queue_effects_for_visible(self) -> None:
        first, last = self._visible_range(buffer=0)
        if last < first:
            return
        for i in range(first, last + 1):
            self._queue_effect(i)

    def _flush_effects(self) -> None:
        self._effect_cache.clear()
        self._effect_inflight.clear()
        if self._show_effect:
            first, last = self._visible_range(buffer=0)
            for i in range(first, max(first, last + 1)):
                self._render_original(i)
            self._queue_effects_for_visible()
        self.update()

    def _schedule_scroll_render(self) -> None:
        self._scroll_timer.start()

    # ----- paint -----

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#2b2b2b"))
        if not self._geoms:
            p.setPen(QColor("#9ca3af"))
            p.drawText(self.rect(), Qt.AlignCenter, "打开 PDF 后在此连续滚动浏览")
            return

        # 内容区不画进滚动条占位，避免与细条叠色
        p.setClipRect(0, 0, self._view_w(), self._view_h())

        # 缩放过渡时旧图≠新尺寸：用平滑变换绘制，避免 Fast 块状发糊
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.Antialiasing, False)

        page_left = self._page_left()
        first, last = self._visible_range(buffer=1)
        for i in range(first, last + 1):
            g = self._geoms[i]
            y = g.y - self._scroll_y
            x = page_left
            p.fillRect(x - 2, y - 2, g.width + 4, g.height + 4, QColor(0, 0, 0, 40))
            p.fillRect(x, y, g.width, g.height, QColor("#ffffff"))

            use_effect = self._show_effect and self._process_fn is not None
            pm = self._effect_cache.get(i) if use_effect else self._cache.get(i)
            if use_effect and (pm is None or not self._pm_matches_geom(pm, i)):
                # 效果未就绪或尺寸过期：先画原图（可平滑拉伸）
                alt = self._cache.get(i)
                if alt is not None:
                    pm = alt
            if pm is None:
                p.setPen(QColor("#d1d5db"))
                p.drawRect(x, y, g.width - 1, g.height - 1)
                p.setPen(QColor("#9ca3af"))
                p.drawText(QRect(x, y, g.width, g.height), Qt.AlignCenter, f"第 {i + 1} 页")
            else:
                # 统一画进逻辑矩形；DPR 正确时为 1:1 清晰，缩放过渡时平滑插值
                p.drawPixmap(QRect(x, y, g.width, g.height), pm)

            if i == self._current_page:
                p.setPen(QPen(QColor("#0ea5e9"), 2))
                p.drawRect(x, y, g.width - 1, g.height - 1)

        if self._mode == MODE_RECT and self._drag_start and self._drag_current:
            # 拖拽中的预览框：半透明填充 + 虚线边，能看见底下内容
            r = QRect(self._drag_start, self._drag_current).normalized()
            p.setPen(QPen(QColor(37, 99, 235, 220), 2, Qt.DashLine))
            p.setBrush(QColor(56, 132, 255, 48))
            p.drawRect(r)
            p.setBrush(Qt.NoBrush)


    # ----- interaction -----

    def _over_scrollbar(self, pos: QPoint) -> bool:
        """是否在滚动条几何区域内（含子控件边角）。"""
        if self._doc is None:
            return False
        if self._vbar.isVisible() and self._vbar.geometry().contains(pos):
            return True
        if self._hbar.isVisible() and self._hbar.geometry().contains(pos):
            return True
        # 右下角交叉块
        if pos.x() >= self._view_w() or pos.y() >= self._view_h():
            return True
        return False

    def _apply_cursor(self, pos: Optional[QPoint] = None) -> None:
        """
        光标策略：
        - 正在平移拖拽：始终手型
        - 滚动条 / 页外黑边：箭头
        - 仅当指针落在真实 PDF 页面矩形内：吸管 / 十字 / 手
        """
        if self._panning:
            key = "closed_hand"
            if key != self._last_cursor_key:
                self.setCursor(Qt.ClosedHandCursor)
                self._last_cursor_key = key
            return

        if pos is None:
            # 无坐标时：空格平移模式用手，否则默认箭头（等移动到页上再变）
            if self._space_pan or self._mode == MODE_PAN:
                key = "open_hand"
                cur = Qt.OpenHandCursor
            else:
                key = "arrow"
                cur = Qt.ArrowCursor
            if key != self._last_cursor_key:
                self.setCursor(cur)
                self._last_cursor_key = key
            return

        if self._over_scrollbar(pos):
            key = "arrow_sb"
            if key != self._last_cursor_key:
                self.setCursor(Qt.ArrowCursor)
                self._last_cursor_key = key
            return

        on_page = self._hit_page(pos) is not None
        if not on_page:
            # 页缝、左右黑边：箭头（空格预按着准备平移时仍显示张开手，提示可拖）
            if self._space_pan:
                key = "open_hand"
                cur = Qt.OpenHandCursor
            else:
                key = "arrow"
                cur = Qt.ArrowCursor
            if key != self._last_cursor_key:
                self.setCursor(cur)
                self._last_cursor_key = key
            return

        # 页面内：工具光标
        if self._space_pan or self._mode == MODE_PAN:
            key = "open_hand"
            cur = Qt.OpenHandCursor
        elif self._mode == MODE_RECT:
            key = "cross"
            cur = Qt.CrossCursor
        else:
            key = "eyedropper"
            cur = self._eyedropper
        if key != self._last_cursor_key:
            self.setCursor(cur)
            self._last_cursor_key = key

    def _hit_page(self, pos: QPoint) -> Optional[Tuple[int, int, int]]:
        """返回 (page, 逻辑坐标 lx, ly)。仅真实页面矩形内命中。"""
        if not self._geoms:
            return None
        # 滚动条区域不参与取色/绘制命中
        if self._over_scrollbar(pos):
            return None
        page_left = self._page_left()
        x = pos.x() - page_left
        y = pos.y() + self._scroll_y
        if x < 0 or x >= self._page_disp_w:
            return None
        for i, g in enumerate(self._geoms):
            if g.y <= y < g.y + g.height:
                return i, max(0, min(g.width - 1, x)), max(0, min(g.height - 1, y - g.y))
        return None

    def _logical_to_raster(self, page_index: int, lx: int, ly: int) -> Optional[Tuple[int, int, Image.Image]]:
        img = self._ensure_page_raster(page_index)
        if img is None or page_index >= len(self._geoms):
            return None
        g = self._geoms[page_index]
        w, h = img.size
        ix = int(round(lx * w / max(1, g.width)))
        iy = int(round(ly * h / max(1, g.height)))
        ix = max(0, min(w - 1, ix))
        iy = max(0, min(h - 1, iy))
        return ix, iy, img

    def _sample_color(self, page_index: int, lx: int, ly: int) -> Optional[RGB]:
        mapped = self._logical_to_raster(page_index, lx, ly)
        if mapped is None:
            return None
        ix, iy, img = mapped
        w, h = img.size
        px = img.getpixel((ix, iy))
        if isinstance(px, int):
            return (px, px, px)
        samples = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                xx, yy = ix + dx, iy + dy
                if 0 <= xx < w and 0 <= yy < h:
                    c = img.getpixel((xx, yy))
                    if isinstance(c, int):
                        samples.append((c, c, c))
                    else:
                        samples.append((int(c[0]), int(c[1]), int(c[2])))
        if not samples:
            return (int(px[0]), int(px[1]), int(px[2]))
        rs = sorted(s[0] for s in samples)
        gs = sorted(s[1] for s in samples)
        bs = sorted(s[2] for s in samples)
        m = len(samples) // 2
        return (rs[m], gs[m], bs[m])

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position().toPoint()
        # 点在滚动条上：交给滚动条，不进入取色/绘制
        if self._over_scrollbar(pos):
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MiddleButton or (
            event.button() == Qt.LeftButton
            and (self._space_pan or self._mode == MODE_PAN or event.modifiers() & Qt.ControlModifier)
        ):
            self._panning = True
            self._last_pos = pos
            self._apply_cursor(pos)
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._mode == MODE_RECT and not self._space_pan:
            # 仅在页面上开始绘制
            if self._hit_page(pos) is None:
                event.accept()
                return
            self._drag_start = pos
            self._drag_current = self._drag_start
            self.update()
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._mode == MODE_PICK and not self._space_pan:
            hit = self._hit_page(pos)
            if hit:
                pi, lx, ly = hit
                self._ensure_page_raster(pi)
                rgb = self._sample_color(pi, lx, ly)
                if rgb is not None:
                    self.color_picked.emit(pi, lx, ly)
                    self.color_sampled.emit(pi, rgb[0], rgb[1], rgb[2])
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position().toPoint()
        if self._panning:
            d = pos - self._last_pos
            self._last_pos = pos
            self._scroll_x -= d.x()
            self._scroll_y -= d.y()
            self._after_scroll(render=True)
            event.accept()
            return
        if self._mode == MODE_RECT and self._drag_start is not None:
            self._drag_current = pos
            self.update()
            event.accept()
            return
        # 随位置切换：页内工具光标 / 页外与滚动条箭头
        self._apply_cursor(pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position().toPoint()
        if self._panning and event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._panning = False
            self._apply_cursor(pos)
            event.accept()
            return
        if self._mode == MODE_RECT and self._drag_start and event.button() == Qt.LeftButton:
            end = pos
            a = self._hit_page(self._drag_start)
            b = self._hit_page(end)
            self._drag_start = None
            self._drag_current = None
            self.update()
            if a and b and a[0] == b[0]:
                pi = a[0]
                g = self._geoms[pi]
                self.rect_drawn.emit(
                    pi,
                    min(a[1], b[1]) / max(1, g.width),
                    min(a[2], b[2]) / max(1, g.height),
                    max(a[1], b[1]) / max(1, g.width),
                    max(a[2], b[2]) / max(1, g.height),
                )
            self._apply_cursor(pos)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                return
            pos = event.position().toPoint()
            self.zoom_by(1.1 if delta > 0 else 1 / 1.1, anchor_viewport=pos)
            event.accept()
            return
        delta = event.angleDelta()
        step = 96
        if event.modifiers() & Qt.ShiftModifier:
            self._scroll_x -= int(delta.y() * 0.5) if delta.y() else int(delta.x() * 0.5)
        else:
            dy = delta.y() if delta.y() else delta.x()
            self._scroll_y -= int(dy * step / 120) if abs(dy) < 400 else int(dy * 0.4)
        self._after_scroll(render=True)
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_pan = True
            self._last_cursor_key = None
            pos = self.mapFromGlobal(QCursor.pos()) if self.underMouse() else None
            self._apply_cursor(pos)
            event.accept()
            return
        if event.key() in (Qt.Key_PageDown, Qt.Key_Down):
            self._scroll_y += int(self._view_h() * 0.9) if event.key() == Qt.Key_PageDown else 48
            self._after_scroll(render=True)
            event.accept()
            return
        if event.key() in (Qt.Key_PageUp, Qt.Key_Up):
            self._scroll_y -= int(self._view_h() * 0.9) if event.key() == Qt.Key_PageUp else 48
            self._after_scroll(render=True)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_pan = False
            self._last_cursor_key = None
            pos = self.mapFromGlobal(QCursor.pos()) if self.underMouse() else None
            self._apply_cursor(pos)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._last_cursor_key = None
        self.setCursor(Qt.ArrowCursor)
        self._last_cursor_key = "arrow"
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_scrollbars()
        if self._doc and self._base_fit_w < 100:
            self.fit_width()
        else:
            self._clamp_scroll()
            self._sync_scrollbars()
            self._schedule_scroll_render()
