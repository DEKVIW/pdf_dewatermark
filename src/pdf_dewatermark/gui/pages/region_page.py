"""区域遮盖：连续滚动 + 矩形叠层（懒渲染）+ 应用到指定页。"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import List, Optional

import fitz
from PIL import Image, ImageDraw
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import CardWidget, StrongBodyLabel

from ...core.page_ranges import (
    apply_region_templates,
    format_pages_preview,
    resolve_apply_pages,
)
from ...models import RegionRect
from ...paths import default_output_path
from .. import icons as I
from ..theme import SPACE_SM, SPACE_XS, apply_label, doc_toolbar_style
from ..widgets.apply_regions_dialog import run_apply_regions_dialog
from ..widgets.continuous_view import ContinuousPdfView
from ..widgets.empty_state import EmptyState
from ..widgets.toolbar_chrome import make_tool_button


class RegionPage(QWidget):
    status = Signal(str)
    request_job = Signal(object)
    log = Signal(str)
    document_changed = Signal(object)
    open_pdf_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._doc: Optional[fitz.Document] = None
        self._path: Optional[Path] = None
        self._regions: List[RegionRect] = []
        self._last_dir = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.empty = EmptyState(
            title="打开 PDF 开始区域遮盖",
            hint="拖入 PDF，在有水印的页上拖出矩形，再用「应用到…」覆盖奇数/偶数/隔页等",
            button_text="打开 PDF…",
        )
        self.empty.open_clicked.connect(lambda: self.open_pdf())
        self.empty.file_dropped.connect(self.open_pdf)
        self.stack.addWidget(self.empty)

        work = QWidget()
        work_l = QVBoxLayout(work)
        work_l.setContentsMargins(0, 0, 0, 0)
        work_l.setSpacing(0)

        doc_bar = QFrame()
        doc_bar.setObjectName("docToolbar")
        doc_bar.setStyleSheet(doc_toolbar_style())
        bar = QHBoxLayout(doc_bar)
        bar.setContentsMargins(SPACE_SM, SPACE_XS, SPACE_SM, SPACE_XS)
        bar.setSpacing(4)
        bar.setAlignment(Qt.AlignVCenter)

        self.prev_btn = make_tool_button(I.ICO_PAGE_PREV, "上一页", self)
        self.next_btn = make_tool_button(I.ICO_PAGE_NEXT, "下一页", self)
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn.clicked.connect(self.next_page)
        bar.addWidget(self.prev_btn)
        bar.addWidget(self.next_btn)

        self.page_label = QLabel("1/1")
        apply_label(self.page_label, "caption")
        self.page_label.setMinimumWidth(40)
        self.page_label.setAlignment(Qt.AlignCenter)
        bar.addWidget(self.page_label)

        self.zoom_out = make_tool_button(I.ICO_ZOOM_OUT, "缩小（Ctrl+滚轮）", self)
        self.zoom_in = make_tool_button(I.ICO_ZOOM_IN, "放大（Ctrl+滚轮）", self)
        self.fit_btn = make_tool_button(I.ICO_FIT, "适合宽度", self)
        self.zoom_out.clicked.connect(lambda: self.viewer.zoom_by(1 / 1.15))
        self.zoom_in.clicked.connect(lambda: self.viewer.zoom_by(1.15))
        self.fit_btn.clicked.connect(lambda: self.viewer.fit_width())
        bar.addWidget(self.zoom_out)
        bar.addWidget(self.zoom_in)
        bar.addWidget(self.fit_btn)

        bar.addStretch(1)

        self.apply_btn = make_tool_button(
            I.ICO_COPY, "应用到…（全部/奇偶/隔页/自定义）", self
        )
        self.apply_btn.clicked.connect(self.apply_current_page_regions)
        bar.addWidget(self.apply_btn)

        self.clear_btn = make_tool_button(I.ICO_CLEAR, "清除本页区域", self)
        self.clear_all_btn = make_tool_button(I.ICO_DELETE, "清除所有区域", self)
        self.clear_btn.clicked.connect(self.clear_page_rects)
        self.clear_all_btn.clicked.connect(self.clear_all_rects)
        bar.addWidget(self.clear_btn)
        bar.addWidget(self.clear_all_btn)

        self.export_btn = make_tool_button(I.ICO_EXPORT, "导出区域遮盖结果 PDF", self)
        self.export_btn.clicked.connect(self.export)
        bar.addWidget(self.export_btn)
        work_l.addWidget(doc_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.viewer = ContinuousPdfView()
        self.viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.viewer.set_draw_rect_mode(True)
        self.viewer.page_changed.connect(self._on_page_changed)
        self.viewer.rect_drawn.connect(self._on_rect)
        self.viewer.set_process_fn(self._overlay_regions)
        self.viewer.set_show_effect(True)
        body.addWidget(self.viewer, 1)

        # 侧栏：可伸缩，小窗时不强制占死 260px 导致主区过窄
        self.side = CardWidget()
        self.side.setMinimumWidth(160)
        self.side.setMaximumWidth(280)
        self.side.setFixedWidth(220)
        side_l = QVBoxLayout(self.side)
        side_l.addWidget(StrongBodyLabel("已绘制区域"))
        self.side_hint = QLabel("拖拽绘制；隔页/偶数页用「应用到…」。")
        apply_label(self.side_hint, "caption")
        self.side_hint.setWordWrap(True)
        side_l.addWidget(self.side_hint)
        self.list = QListWidget()
        side_l.addWidget(self.list, 1)
        self.summary_label = QLabel("共 0 个区域")
        apply_label(self.summary_label, "caption")
        side_l.addWidget(self.summary_label)
        body.addWidget(self.side, 0)
        work_l.addLayout(body, 1)

        self.stack.addWidget(work)
        self.stack.setCurrentIndex(0)
        self.setAcceptDrops(True)

    def open_pdf(self, path: Optional[str] = None) -> None:
        """请求全局打开。"""
        if path and isinstance(path, str):
            self.open_pdf_requested.emit(path)
        else:
            self.open_pdf_requested.emit("")

    def attach_document(self, doc: object, path: Path, *, clear_regions: bool = True) -> None:
        """绑定全局文档；换文档时默认清空矩形（版式可能不同）。"""
        if not isinstance(doc, fitz.Document):
            return
        self._doc = doc
        self._path = Path(path)
        self._last_dir = str(self._path.parent)
        if clear_regions:
            self._regions.clear()
            self._rebuild_list()
        self.stack.setCurrentIndex(1)
        self.viewer.set_document(self._doc)
        self.viewer.fit_width()
        self.viewer.set_show_effect(True)
        self.page_label.setText(f"1/{len(self._doc)}")
        self.status.emit(f"区域遮盖：{self._path.name}")
        self.document_changed.emit(self._path)

    def detach_document(self) -> None:
        self._doc = None
        self._path = None
        self.viewer.set_document(None)
        self.stack.setCurrentIndex(0)

    def get_regions(self) -> List:
        return list(self._regions)

    def region_count(self) -> int:
        return len(self._regions)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p.lower().endswith(".pdf"):
                self.open_pdf(p)
                event.acceptProposedAction()
                return
        event.ignore()

    def prev_page(self) -> None:
        if self._doc:
            self.viewer.goto_page(max(0, self.viewer.current_page() - 1))

    def next_page(self) -> None:
        if self._doc:
            self.viewer.goto_page(min(len(self._doc) - 1, self.viewer.current_page() + 1))

    def _on_page_changed(self, index: int) -> None:
        if self._doc:
            self.page_label.setText(f"{index + 1}/{len(self._doc)}")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # 窄窗收窄侧栏，避免与预览抢宽度
        w = self.width()
        if hasattr(self, "side"):
            if w < 900:
                self.side.setFixedWidth(max(160, min(200, w // 5)))
            else:
                self.side.setFixedWidth(220)

    def _overlay_regions(self, image: Image.Image, page_index: int) -> Image.Image:
        rects = [r for r in self._regions if r.page_index == page_index]
        if not rects or not self._doc:
            return image
        page = self._doc[page_index]
        pw, ph = page.rect.width, page.rect.height
        out = image.convert("RGBA")
        draw = ImageDraw.Draw(out, "RGBA")
        for r in rects:
            x0, y0, x1, y1 = r.normalized()
            sx = out.width / pw if pw else 1
            sy = out.height / ph if ph else 1
            box = (x0 * sx, y0 * sy, x1 * sx, y1 * sy)
            draw.rectangle(box, fill=(74, 134, 232, 90), outline=(37, 99, 235, 220), width=2)
        return out.convert("RGB")

    def _on_rect(self, page: int, x0: float, y0: float, x1: float, y1: float) -> None:
        if not self._doc:
            return
        if abs(x1 - x0) < 0.005 or abs(y1 - y0) < 0.005:
            return
        p = self._doc[page]
        w, h = p.rect.width, p.rect.height
        r = RegionRect(
            page_index=page,
            x0=min(x0, x1) * w,
            y0=min(y0, y1) * h,
            x1=max(x0, x1) * w,
            y1=max(y0, y1) * h,
        )
        self._regions.append(r)
        self._rebuild_list()
        self.viewer.invalidate_effects(immediate=True)
        self.status.emit(f"已添加矩形（第 {page + 1} 页），共 {len(self._regions)} 个 · 可用「应用到…」铺到奇偶/隔页")

    def _rebuild_list(self) -> None:
        self.list.clear()
        by_page: dict[int, List[RegionRect]] = defaultdict(list)
        for r in self._regions:
            by_page[r.page_index].append(r)
        for pi in sorted(by_page.keys()):
            rects = by_page[pi]
            self.list.addItem(f"—— 第 {pi + 1} 页（{len(rects)} 个）——")
            for i, r in enumerate(rects, 1):
                x0, y0, x1, y1 = r.normalized()
                self.list.addItem(
                    f"  {i}. ({x0:.0f},{y0:.0f})–({x1:.0f},{y1:.0f})"
                )
        n_pages = len(by_page)
        self.summary_label.setText(
            f"共 {len(self._regions)} 个区域"
            + (f" · 分布在 {n_pages} 页" if n_pages else "")
        )

    def clear_page_rects(self) -> None:
        pi = self.viewer.current_page()
        before = len(self._regions)
        self._regions = [r for r in self._regions if r.page_index != pi]
        removed = before - len(self._regions)
        self._rebuild_list()
        self.viewer.invalidate_effects(immediate=True)
        self.status.emit(f"已清除第 {pi + 1} 页区域（{removed} 个）")

    def clear_all_rects(self) -> None:
        if self._regions and QMessageBox.question(
            self,
            "确认",
            f"清除全部 {len(self._regions)} 个区域？",
        ) != QMessageBox.Yes:
            return
        self._regions.clear()
        self._rebuild_list()
        self.viewer.invalidate_effects(immediate=True)
        self.status.emit("已清除所有区域")

    def apply_current_page_regions(self) -> None:
        """将当前页矩形应用到选定页集合（全部/奇偶/隔页/自定义）。"""
        if not self._doc:
            return
        pi = self.viewer.current_page()
        templates = [r for r in self._regions if r.page_index == pi]
        if not templates:
            QMessageBox.information(
                self,
                "提示",
                f"第 {pi + 1} 页还没有矩形。\n请先在该页拖拽绘制遮盖区域，再点「应用到…」。",
            )
            return

        result = run_apply_regions_dialog(
            self,
            page_count=len(self._doc),
            current_index=pi,
            template_count=len(templates),
        )
        if result is None:
            return
        mode, custom_spec, replace = result
        targets = resolve_apply_pages(
            mode,
            len(self._doc),
            current_index=pi,
            custom_spec=custom_spec,
        )
        if not targets:
            QMessageBox.warning(self, "无效", "没有匹配的页面，请检查自定义页码。")
            return

        self._regions = apply_region_templates(
            self._regions,
            pi,
            targets,
            replace=replace,
        )
        self._rebuild_list()
        self.viewer.invalidate_effects(immediate=True)
        preview = format_pages_preview(targets)
        msg = (
            f"已将第 {pi + 1} 页的 {len(templates)} 个矩形"
            f"{'替换并' if replace else ''}应用到 {preview}"
        )
        self.status.emit(msg)
        self.log.emit(msg)

    def export(self) -> None:
        from ..workers import JobRequest

        if not self._path or not self._regions:
            QMessageBox.information(self, "提示", "请打开 PDF 并至少绘制一个矩形")
            return
        initial = str(default_output_path(self._path, suffix="区域遮盖"))
        path, _ = QFileDialog.getSaveFileName(self, "导出 PDF", initial, "PDF (*.pdf)")
        if not path:
            return
        req = JobRequest(
            kind="region",
            input_path=str(self._path),
            output_path=path,
            regions=list(self._regions),
            region_dpi=200,
        )
        self.log.emit(f"区域遮盖导出 → {path}（{len(self._regions)} 个区域）")
        self.request_job.emit(req)

    def close_doc(self) -> None:
        self.detach_document()
        self.document_changed.emit(None)
