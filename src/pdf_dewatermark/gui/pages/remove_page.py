"""选色替换：连续滚动阅读器 + 懒渲染效果预览。"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import fitz
from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import SegmentedWidget

from ...core.remove import remove_watermark_image
from ...paths import default_output_path
from .. import icons as I
from ..theme import (
    SPACE_SM,
    SPACE_XS,
    apply_control_font,
    apply_label,
    doc_toolbar_style,
    font_section,
)
from ..widgets.continuous_view import ContinuousPdfView
from ..widgets.empty_state import EmptyState
from ..widgets.params_panel import ParamsPanel
from ..widgets.toolbar_chrome import ElideLabel, make_tool_button


class RemovePage(QWidget):
    status = Signal(str)
    request_job = Signal(object)
    log = Signal(str)
    document_changed = Signal(object)
    # 请求主窗口全局打开（path 可为 "" 表示弹对话框）
    open_pdf_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._doc: Optional[fitz.Document] = None
        self._path: Optional[Path] = None
        self._picking_bg = False
        self._busy = False
        self._last_dir = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.empty = EmptyState(
            title="打开 PDF 开始选色替换",
            hint="将 PDF 拖到此处，或通过菜单 / 工具栏打开文件",
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

        # 纯图标平铺：居中 ToolButton，无下拉（小窗也够用）
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
        self.fit_btn.clicked.connect(self._fit_width)
        bar.addWidget(self.zoom_out)
        self.zoom_label = QLabel("100%")
        apply_label(self.zoom_label, "caption")
        self.zoom_label.setMinimumWidth(40)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        bar.addWidget(self.zoom_label)
        bar.addWidget(self.zoom_in)
        bar.addWidget(self.fit_btn)

        self.view_mode = SegmentedWidget()
        self.view_mode.addItem("original", "原图")
        self.view_mode.addItem("preview", "效果")
        self.view_mode.setCurrentItem("original")
        self.view_mode.currentItemChanged.connect(self._on_view_changed)
        bar.addWidget(self.view_mode)

        self.params_toggle = make_tool_button(I.NAV_SETTINGS, "显示/隐藏参数", self)
        self.params_toggle.setCheckable(True)
        self.params_toggle.clicked.connect(self._toggle_params)
        bar.addWidget(self.params_toggle)

        self.preview_btn = make_tool_button(I.ICO_REFRESH, "刷新效果", self)
        self.preview_btn.clicked.connect(self.refresh_preview)
        bar.addWidget(self.preview_btn)

        bar.addStretch(1)

        # 处理：三个独立图标按钮（无下拉、无文案裁切）
        self.page_btn = make_tool_button(I.ICO_DOCUMENT, "处理当前页", self)
        self.range_btn = make_tool_button(I.ICO_EDIT, "处理页范围…", self)
        self.all_btn = make_tool_button(I.ICO_EXPORT, "处理全部页面并导出", self)
        self.page_btn.clicked.connect(self.process_current_page)
        self.range_btn.clicked.connect(self.process_range)
        self.all_btn.clicked.connect(self.process_all)
        bar.addWidget(self.page_btn)
        bar.addWidget(self.range_btn)
        bar.addWidget(self.all_btn)
        work_l.addWidget(doc_bar)

        meta = QFrame()
        meta_l = QHBoxLayout(meta)
        meta_l.setContentsMargins(SPACE_SM, SPACE_XS, SPACE_SM, SPACE_XS)
        self.file_label = ElideLabel()
        self.file_label.setFont(font_section())
        self.file_label.setStyleSheet("color: #111827;")
        meta_l.addWidget(self.file_label, 1)
        work_l.addWidget(meta)

        body = QHBoxLayout()
        body.setSpacing(0)
        body.setContentsMargins(0, 0, 0, 0)

        self.viewer = ContinuousPdfView()
        self.viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.viewer.page_changed.connect(self._on_page_changed)
        self.viewer.scale_changed.connect(self._on_scale_changed)
        # 使用 color_sampled：直接给出显示缓冲上的精确 RGB（1:1 取样）
        self.viewer.color_sampled.connect(self._on_color_sampled)
        self.viewer.set_process_fn(self._process_page_image)
        body.addWidget(self.viewer, 1)

        self.params_drawer = QFrame()
        self.params_drawer.setObjectName("paramsDrawer")
        self.params_drawer.setStyleSheet(
            "#paramsDrawer { background: #fafafa; border-left: 1px solid #e5e7eb; }"
        )
        self.params_drawer.setFixedWidth(300)
        self.params_drawer.setVisible(False)
        drawer_l = QVBoxLayout(self.params_drawer)
        drawer_l.setContentsMargins(0, 0, 0, 0)
        self.params = ParamsPanel()
        self.params.setMinimumWidth(0)
        self.params.setMaximumWidth(16777215)
        self.params.setFixedWidth(300)
        drawer_l.addWidget(self.params)
        body.addWidget(self.params_drawer, 0)
        work_l.addLayout(body, 1)

        self.stack.addWidget(work)
        self.stack.setCurrentIndex(0)

        self.params.params_changed.connect(self._on_params_changed)
        self.params.pick_bg_requested.connect(self._start_pick_bg)
        self.params.clear_colors_requested.connect(self._on_clear_colors)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # 窄窗略收参数抽屉，给预览让宽（功能不变）
        if hasattr(self, "params_drawer") and hasattr(self, "params"):
            w = max(200, self.width())
            if w < 1000:
                dw = 260
            else:
                dw = 300
            self.params_drawer.setFixedWidth(dw)
            self.params.setFixedWidth(dw)

    def current_path(self) -> Optional[Path]:
        return self._path

    def has_document(self) -> bool:
        return self._doc is not None

    def open_pdf(self, path: Optional[str] = None) -> None:
        """请求全局打开（由 MainWindow 持有 Document，本页只绑定显示）。"""
        if path and isinstance(path, str):
            self.open_pdf_requested.emit(path)
        else:
            self.open_pdf_requested.emit("")

    def attach_document(self, doc: object, path: Path) -> None:
        """绑定全局文档，不负责 open/close fitz。"""
        import fitz as _fitz

        if not isinstance(doc, _fitz.Document):
            return
        self._doc = doc
        self._path = Path(path)
        self._last_dir = str(self._path.parent)
        self.file_label.set_full_text(self._path.name)
        self.stack.setCurrentIndex(1)
        self.viewer.set_document(self._doc)
        self.viewer.fit_width()
        self.viewer.set_show_effect(self.view_mode.currentRouteKey() == "preview")
        self.page_label.setText(f"1 / {len(self._doc)}")
        self.status.emit(f"已打开：{self._path.name}（{len(self._doc)} 页）")
        self.log.emit(f"打开 {self._path}")
        self.document_changed.emit(self._path)
        self.viewer.setFocus()

    def detach_document(self) -> None:
        """解除绑定，不关闭全局 Document。"""
        self._doc = None
        self._path = None
        self.viewer.set_document(None)
        self.stack.setCurrentIndex(0)
        self.file_label.set_full_text("")

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

    def _toggle_params(self) -> None:
        self.show_params(self.params_toggle.isChecked())

    def show_params(self, show: bool = True) -> None:
        self.params_drawer.setVisible(bool(show))
        self.params_toggle.blockSignals(True)
        self.params_toggle.setChecked(bool(show))
        self.params_toggle.blockSignals(False)

    def apply_prefs(self, prefs: dict) -> None:
        self.params.apply_prefs(prefs)
        self._last_dir = prefs.get("last_dir") or ""
        mode = prefs.get("view_mode", "original")
        if mode == "compare":
            mode = "preview"
        try:
            self.view_mode.setCurrentItem(mode if mode in ("original", "preview") else "original")
        except Exception:
            pass
        if prefs.get("params_open"):
            self.show_params(True)

    def collect_prefs(self) -> dict:
        d = self.params.to_prefs()
        d["view_mode"] = self.view_mode.currentRouteKey()
        d["params_open"] = self.params_drawer.isVisible()
        if self._path:
            d["last_dir"] = str(self._path.parent)
        elif self._last_dir:
            d["last_dir"] = self._last_dir
        return d

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        en = not busy and self._doc is not None
        for b in (self.preview_btn, self.page_btn, self.range_btn, self.all_btn):
            b.setEnabled(en)

    def prev_page(self) -> None:
        if not self._doc:
            return
        self.viewer.goto_page(max(0, self.viewer.current_page() - 1))

    def next_page(self) -> None:
        if not self._doc:
            return
        self.viewer.goto_page(min(len(self._doc) - 1, self.viewer.current_page() + 1))

    def _on_page_changed(self, index: int) -> None:
        if self._doc:
            self.page_label.setText(f"{index + 1}/{len(self._doc)}")

    def _on_scale_changed(self, scale: float) -> None:
        self.zoom_label.setText(f"{int(scale * 100)}%")

    def _fit_width(self) -> None:
        self.viewer.fit_width()

    def _on_view_changed(self, key: str) -> None:
        self.viewer.set_show_effect(key == "preview")
        if key == "preview" and not self.params.has_colors():
            self.status.emit("请先取样目标色后再看效果")

    def _process_page_image(self, image: Image.Image, page_index: int) -> Image.Image:
        """可见页懒处理：仅在有颜色组时执行。"""
        if not self.params.has_colors():
            return image
        try:
            params = self.params.build_params()
            out, _ = remove_watermark_image(image, params)
            return out
        except Exception:
            return image

    def _on_params_changed(self) -> None:
        # 防抖刷新效果，拖动容差时不每帧卡死
        self.viewer.invalidate_effects(immediate=False)
        if self.view_mode.currentRouteKey() == "preview" and self.params.has_colors():
            self.status.emit("参数已更新…")

    def _start_pick_bg(self) -> None:
        self._picking_bg = True
        if not self.params_drawer.isVisible():
            self.show_params(True)
        self.status.emit("请点击页面选择背景色（Esc 取消）")
        self.viewer.setFocus()

    def _on_clear_colors(self) -> None:
        self.viewer.invalidate_effects(immediate=True)
        self.status.emit("已清空目标色取样")

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape and self._picking_bg:
            self._picking_bg = False
            self.status.emit("已取消背景拾取")
            return
        super().keyPressEvent(event)

    def _on_color_sampled(self, page: int, r: int, g: int, b: int) -> None:
        """视图层已完成 1:1 缓冲取样，这里只写入参数。"""
        rgb = (int(r), int(g), int(b))

        if self._picking_bg:
            self.params.blockSignals(True)
            self.params.set_background(rgb)
            self.params.blockSignals(False)
            self._picking_bg = False
            self.status.emit(f"当前组背景 RGB{rgb}")
            self.viewer.invalidate_effects(immediate=False)
            return

        self.params.blockSignals(True)
        self.params.add_sample(rgb)
        self.params.blockSignals(False)
        n = self.params.pair_count_ready()
        self.status.emit(f"第{page + 1}页已取目标色 RGB{rgb} · 共 {n} 组")
        if n == 1 and not self.params_drawer.isVisible():
            self.show_params(True)
        # 取色后效果异步刷新，不阻塞点选
        self.viewer.invalidate_effects(immediate=False)
        if self.view_mode.currentRouteKey() != "preview":
            self.view_mode.setCurrentItem("preview")

    def refresh_preview(self) -> None:
        if not self.params.has_colors():
            self.status.emit("请先取样至少一组目标色")
            return
        self.viewer.invalidate_effects(immediate=True)
        self.viewer.set_show_effect(True)
        if self.view_mode.currentRouteKey() != "preview":
            self.view_mode.setCurrentItem("preview")
        self.status.emit("已刷新可见页效果")

    def _ask_output(self, suffix: str) -> Optional[Path]:
        if not self._path:
            return None
        initial = str(default_output_path(self._path, suffix=suffix))
        path, _ = QFileDialog.getSaveFileName(self, "导出 PDF", initial, "PDF (*.pdf)")
        return Path(path) if path else None

    def process_current_page(self) -> None:
        self._emit_remove_job([self.viewer.current_page()], "单页")

    def process_all(self) -> None:
        self._emit_remove_job(None, "全部")

    def process_range(self) -> None:
        if not self._doc:
            return
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout
        from qfluentwidgets import LineEdit

        dlg = QDialog(self)
        dlg.setWindowTitle("处理页范围")
        form = QFormLayout(dlg)
        start = LineEdit()
        end = LineEdit()
        cur = self.viewer.current_page() + 1
        start.setText(str(cur))
        end.setText(str(len(self._doc)))
        apply_control_font(start)
        apply_control_font(end)
        form.addRow("起始页（从 1）", start)
        form.addRow("结束页", end)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            s = max(1, int(start.text()))
            e = min(len(self._doc), int(end.text()))
        except ValueError:
            QMessageBox.warning(self, "无效", "请输入数字页码")
            return
        if s > e:
            QMessageBox.warning(self, "无效", "起始页不能大于结束页")
            return
        self._emit_remove_job(list(range(s - 1, e)), f"{s}-{e}页")

    def _emit_remove_job(self, indices: Optional[List[int]], label: str) -> None:
        from ..workers import JobRequest

        if not self._path or not self._doc:
            QMessageBox.information(self, "提示", "请先打开 PDF")
            return
        if not self.params.has_colors():
            QMessageBox.information(self, "提示", "请先添加至少一组目标色")
            return
        out = self._ask_output(f"选色替换_{label}")
        if not out:
            return
        try:
            params = self.params.build_params()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "参数错误", str(exc))
            return
        req = JobRequest(
            kind="remove",
            input_path=str(self._path),
            output_path=str(out),
            params=params,
            page_indices=indices,
        )
        self.log.emit(f"开始选色替换（{label}）→ {out}")
        self.request_job.emit(req)

    def close_doc(self) -> None:
        """兼容旧调用：仅解绑，文档由主窗口关闭。"""
        self.detach_document()
        self.document_changed.emit(None)
