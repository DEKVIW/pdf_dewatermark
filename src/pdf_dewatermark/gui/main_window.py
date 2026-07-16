"""主窗口：规范文档工作台壳层（菜单 · 应用工具栏 · 状态栏）。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import NavigationInterface, NavigationItemPosition, PushButton

from .widgets.toolbar_chrome import ElideLabel, make_tool_button

from ..paths import OUTPUT_DIR, ensure_runtime_dirs
from . import icons as I
from .branding import (
    APP_ABOUT,
    APP_NAME_FULL,
    APP_NAME_ZH,
    APP_TAGLINE,
    APP_VERSION,
    APP_WINDOW_TITLE,
    DOCS_URL,
    icon_path,
)
from .pages.batch_page import BatchPage
from .pages.grayscale_page import GrayscalePage
from .pages.pipeline_page import PipelinePage
from .pages.region_page import RegionPage
from .pages.remove_page import RemovePage
from .state.prefs import load_prefs, push_recent, save_prefs
from .theme import (
    CTRL_HEIGHT,
    SPACE_SM,
    SPACE_XS,
    apply_control_font,
    apply_label,
    font_title,
    statusbar_style,
    toolbar_frame_style,
)
from .widgets.log_panel import LogPanel
from .workers import JobRequest, JobWorker, start_job

MODE_REMOVE = "remove"
MODE_REGION = "region"
MODE_GRAY = "grayscale"
MODE_PIPELINE = "pipeline"
MODE_BATCH = "batch"

MODE_LABELS = [
    (MODE_REMOVE, "选色替换"),
    (MODE_REGION, "区域遮盖"),
    (MODE_GRAY, "灰度转换"),
    (MODE_PIPELINE, "组合处理"),
    (MODE_BATCH, "批量处理"),
]

_SUBTITLES = {
    MODE_REMOVE: "点选目标色替换为背景色，支持多组一次处理",
    MODE_REGION: "拖拽矩形遮盖固定区域，可应用到奇偶/隔页",
    MODE_GRAY: "整页渲染为灰度后重新生成 PDF",
    MODE_PIPELINE: "灰度 · 选色 · 区域按序一次导出（共用当前文档）",
    MODE_BATCH: "多文件使用同一套颜色组参数批量导出",
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_WINDOW_TITLE)
        self.resize(1400, 900)
        self.setMinimumSize(960, 640)
        self.setAcceptDrops(True)
        ensure_runtime_dirs()
        icon = icon_path()
        if icon is not None:
            self.setWindowIcon(QIcon(str(icon)))

        self._prefs = load_prefs()
        self._thread = None
        self._worker: Optional[JobWorker] = None
        self._log_expanded = False
        self._recent_actions: List[QAction] = []
        # 全局当前文档（选色/区域/组合共享；批量仍用自己的队列）
        self._doc = None  # Optional[fitz.Document]
        self._doc_path: Optional[Path] = None

        self._build_menu()
        self._build_ui()
        self._build_statusbar()
        self._apply_prefs()
        self._rebuild_recent_menu()

    # ----- menu -----

    def _build_menu(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("文件")
        act_open = QAction("打开 PDF…", self)
        act_open.setShortcut(QKeySequence.Open)
        act_open.setIcon(I.ICO_OPEN.icon())
        act_open.triggered.connect(self.open_pdf_dialog)
        file_menu.addAction(act_open)

        self.recent_menu = file_menu.addMenu("最近打开")
        file_menu.addSeparator()

        act_out = QAction("打开输出目录", self)
        act_out.setIcon(I.NAV_OUTPUT.icon())
        act_out.triggered.connect(lambda: self._open_path(OUTPUT_DIR))
        file_menu.addAction(act_out)
        file_menu.addSeparator()

        act_quit = QAction("退出", self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        view_menu = menu.addMenu("视图")
        act_log = QAction("显示/隐藏日志", self)
        act_log.setShortcut(QKeySequence("Ctrl+L"))
        act_log.triggered.connect(self._toggle_log)
        view_menu.addAction(act_log)

        help_menu = menu.addMenu("帮助")
        act_docs = QAction("使用说明", self)
        act_docs.triggered.connect(self._open_user_guide)
        help_menu.addAction(act_docs)
        help_menu.addSeparator()
        act_about = QAction("关于净页", self)
        act_about.triggered.connect(self._about)
        help_menu.addAction(act_about)

    def _rebuild_recent_menu(self) -> None:
        self.recent_menu.clear()
        self._recent_actions.clear()
        recent = [p for p in (self._prefs.get("recent_files") or []) if Path(p).is_file()]
        if not recent:
            empty = QAction("（无）", self)
            empty.setEnabled(False)
            self.recent_menu.addAction(empty)
            return
        for path in recent[:12]:
            act = QAction(Path(path).name, self)
            act.setToolTip(path)
            act.triggered.connect(lambda checked=False, p=path: self.open_pdf_path(p))
            self.recent_menu.addAction(act)
            self._recent_actions.append(act)
        self.recent_menu.addSeparator()
        clear_act = QAction("清除最近记录", self)
        clear_act.triggered.connect(self._clear_recent)
        self.recent_menu.addAction(clear_act)

    def _clear_recent(self) -> None:
        self._prefs["recent_files"] = []
        self._rebuild_recent_menu()

    # ----- chrome UI -----

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 左侧导航
        self.navigation = NavigationInterface(self, showMenuButton=True, showReturnButton=False)
        self.navigation.setExpandWidth(168)
        for key, label in MODE_LABELS:
            self.navigation.addItem(
                routeKey=key,
                icon=I.MODE_ICONS.get(key, I.ICO_DOCUMENT),
                text=label,
                onClick=lambda checked=False, k=key: self._switch_mode(k),
                position=NavigationItemPosition.TOP,
            )
        self.navigation.addItem(
            routeKey="open_output",
            icon=I.NAV_OUTPUT,
            text="输出目录",
            onClick=lambda: self._open_path(OUTPUT_DIR),
            position=NavigationItemPosition.BOTTOM,
        )
        self.navigation.addItem(
            routeKey="about",
            icon=I.NAV_ABOUT,
            text="关于",
            onClick=lambda: self._about(),
            position=NavigationItemPosition.BOTTOM,
        )
        outer.addWidget(self.navigation)

        # 右侧：应用工具栏 + 标题 + 页面
        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(0)

        # —— 应用级工具栏（壳层：打开 / 当前文件 / 输出）——
        app_tb = QFrame()
        app_tb.setObjectName("appToolbar")
        app_tb.setStyleSheet(toolbar_frame_style())
        app_tb.setFixedHeight(CTRL_HEIGHT + 14)
        tb = QHBoxLayout(app_tb)
        tb.setContentsMargins(SPACE_SM, SPACE_XS, SPACE_SM, SPACE_XS)
        tb.setSpacing(SPACE_SM)

        self.btn_open = PushButton("打开")
        self.btn_open.setIcon(I.ICO_OPEN.icon())
        self.btn_open.setToolTip("打开 PDF（Ctrl+O）")
        self.btn_open.clicked.connect(self.open_pdf_dialog)
        apply_control_font(self.btn_open)
        self.btn_open.setFixedHeight(CTRL_HEIGHT)
        tb.addWidget(self.btn_open)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #e5e7eb;")
        tb.addWidget(sep)

        self.lbl_doc = ElideLabel()
        apply_label(self.lbl_doc, "caption")
        self.lbl_doc.set_full_text("未打开文档")
        tb.addWidget(self.lbl_doc, 1)

        self.btn_output = make_tool_button(I.NAV_OUTPUT, "打开输出目录", self)
        self.btn_output.clicked.connect(lambda: self._open_path(OUTPUT_DIR))
        tb.addWidget(self.btn_output)

        self.btn_stop = make_tool_button(I.ICO_STOP, "停止当前任务", self)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_job)
        tb.addWidget(self.btn_stop)

        right_l.addWidget(app_tb)

        # 页面标题
        title_wrap = QWidget()
        title_l = QHBoxLayout(title_wrap)
        title_l.setContentsMargins(SPACE_SM, SPACE_SM, SPACE_SM, SPACE_XS)
        title_l.setSpacing(SPACE_SM)
        self.page_title = QLabel(MODE_LABELS[0][1])
        self.page_title.setFont(font_title())
        self.page_title.setStyleSheet("color: #111827;")
        self.page_title.setMinimumWidth(72)
        title_l.addWidget(self.page_title)
        self.page_subtitle = ElideLabel()
        apply_label(self.page_subtitle, "caption")
        self.page_subtitle.set_full_text(_SUBTITLES[MODE_REMOVE])
        title_l.addWidget(self.page_subtitle, 1)
        right_l.addWidget(title_wrap)

        # 页面栈
        content = QWidget()
        content_l = QVBoxLayout(content)
        content_l.setContentsMargins(SPACE_SM, 0, SPACE_SM, SPACE_SM)
        content_l.setSpacing(0)
        self.stack = QStackedWidget()
        self.remove_page = RemovePage()
        self.region_page = RegionPage()
        self.gray_page = GrayscalePage()
        self.pipeline_page = PipelinePage()
        self.batch_page = BatchPage()
        self.batch_page.sync_requested.connect(self._sync_batch_from_remove)
        self.remove_page.open_pdf_requested.connect(self._on_page_open_requested)
        self.region_page.open_pdf_requested.connect(self._on_page_open_requested)
        self.pipeline_page.navigate_to.connect(self._navigate_to_mode)
        self.pipeline_page.bind_providers(
            get_remove_ready=self._pipeline_remove_ready,
            get_region_ready=self._pipeline_region_ready,
            get_remove_params=lambda: self.remove_page.params.build_params(),
            get_regions=lambda: self.region_page.get_regions(),
        )
        for page in (
            self.remove_page,
            self.region_page,
            self.gray_page,
            self.pipeline_page,
            self.batch_page,
        ):
            self.stack.addWidget(page)
            page.status.connect(self._set_status)
            page.request_job.connect(self.start_job)
            page.log.connect(self._log)
        content_l.addWidget(self.stack, 1)

        # 可折叠日志（不抢主区域）
        self.log_panel = LogPanel()
        self.log_panel.setVisible(False)
        self.log_panel.setMaximumHeight(100)
        content_l.addWidget(self.log_panel)
        right_l.addWidget(content, 1)
        outer.addWidget(right, 1)

        self._mode_order = [k for k, _ in MODE_LABELS]

    def _build_statusbar(self) -> None:
        sb = QStatusBar(self)
        sb.setStyleSheet(statusbar_style())
        self.setStatusBar(sb)
        self.status_label = ElideLabel()
        apply_label(self.status_label, "caption")
        self.status_label.set_full_text("就绪")
        sb.addWidget(self.status_label, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMaximumWidth(140)
        self.progress.setFixedWidth(120)
        self.progress.setFixedHeight(14)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        sb.addPermanentWidget(self.progress)

        # 固定短文案，避免「展开/收起日志」被裁切
        self.btn_log = PushButton("日志")
        apply_control_font(self.btn_log)
        self.btn_log.setFixedHeight(24)
        self.btn_log.setMinimumWidth(48)
        self.btn_log.setToolTip("显示或隐藏日志面板（Ctrl+L）")
        self.btn_log.clicked.connect(self._toggle_log)
        sb.addPermanentWidget(self.btn_log)

    # ----- open / recent -----

    def open_pdf_dialog(self) -> None:
        start = self._prefs.get("last_dir") or ""
        path, _ = QFileDialog.getOpenFileName(self, "打开 PDF", start, "PDF (*.pdf)")
        if path:
            self.open_pdf_path(path)

    def _on_page_open_requested(self, path: str) -> None:
        """子页空状态/拖入：走全局打开。"""
        if path and str(path).strip():
            self.open_pdf_path(str(path).strip())
        else:
            self.open_pdf_dialog()

    def open_pdf_path(self, path: str) -> None:
        """全局打开 PDF：选色 / 区域 / 组合共用同一 Document。"""
        import fitz

        p = Path(path)
        if not p.is_file():
            QMessageBox.warning(self, "无法打开", f"文件不存在：\n{path}")
            self._rebuild_recent_menu()
            return
        try:
            new_doc = fitz.open(str(p))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "打开失败", str(exc))
            return

        # 先解绑再关旧文档，避免 double-close
        self.remove_page.detach_document()
        self.region_page.detach_document()
        old = self._doc
        self._doc = new_doc
        self._doc_path = p
        if old is not None:
            try:
                if not getattr(old, "is_closed", False):
                    old.close()
            except Exception:
                pass

        # 绑定到文档页：换文档清空区域矩形，保留选色参数
        self.remove_page.attach_document(self._doc, p)
        self.region_page.attach_document(self._doc, p, clear_regions=True)
        self.pipeline_page.set_document_path(p, page_count=len(self._doc))
        # 灰度页填入路径，仍可单独另选文件
        try:
            self.gray_page.input_edit.setText(str(p))
            if not self.gray_page.output_edit.text().strip():
                from ..paths import default_output_path

                self.gray_page.output_edit.setText(
                    str(default_output_path(p, suffix="灰度"))
                )
        except Exception:
            pass

        self.lbl_doc.set_full_text(p.name)
        self.lbl_doc.setToolTip(str(p))
        self.setWindowTitle(f"{p.name} — {APP_NAME_ZH}")
        self._prefs = push_recent(self._prefs, p)
        self._prefs["last_dir"] = str(p.parent)
        self._rebuild_recent_menu()
        self.pipeline_page.refresh_status()
        self._set_status(f"已打开：{p.name}（{len(self._doc)} 页）· 全局共用")
        self._log(f"全局打开 {p}")

    def _close_global_document(self) -> None:
        self.remove_page.detach_document()
        self.region_page.detach_document()
        self.pipeline_page.set_document_path(None, 0)
        doc = self._doc
        self._doc = None
        self._doc_path = None
        if doc is not None:
            try:
                if not getattr(doc, "is_closed", False):
                    doc.close()
            except Exception:
                pass
        self.lbl_doc.set_full_text("未打开文档")
        self.setWindowTitle(APP_WINDOW_TITLE)

    def _pipeline_remove_ready(self):
        try:
            n = self.remove_page.params.pair_count_ready()
            if n > 0:
                return True, f"已配置 {n} 组颜色"
            return False, "尚未取样（请到选色页取目标色）"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def _pipeline_region_ready(self):
        try:
            n = self.region_page.region_count()
            if n > 0:
                return True, f"已有 {n} 个矩形"
            return False, "尚未绘制（请到区域页画框）"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def _navigate_to_mode(self, key: str) -> None:
        if key not in self._mode_order:
            return
        self._switch_mode(key)
        try:
            self.navigation.setCurrentItem(key)
        except Exception:
            pass
        if key == MODE_PIPELINE:
            self.pipeline_page.refresh_status()

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
            if path.lower().endswith(".pdf"):
                self.open_pdf_path(path)
                event.acceptProposedAction()
                return
        event.ignore()

    # ----- mode / prefs -----

    def _apply_prefs(self) -> None:
        self.remove_page.apply_prefs(self._prefs)
        mode = self._prefs.get("last_mode", MODE_REMOVE)
        if mode in self._mode_order:
            self._switch_mode(mode)
            try:
                self.navigation.setCurrentItem(mode)
            except Exception:
                pass
        geo = self._prefs.get("window_geometry") or ""
        if geo:
            try:
                self.restoreGeometry(bytes.fromhex(geo))
            except Exception:
                pass

    def _switch_mode(self, key: str) -> None:
        if key not in self._mode_order:
            return
        self.stack.setCurrentIndex(self._mode_order.index(key))
        self.page_title.setText(dict(MODE_LABELS).get(key, key))
        self.page_subtitle.set_full_text(_SUBTITLES.get(key, ""))
        self._prefs["last_mode"] = key
        if key == MODE_BATCH:
            self._sync_batch_from_remove(silent=True)
        if key == MODE_PIPELINE:
            self.pipeline_page.refresh_status()

    def _sync_batch_from_remove(self, silent: bool = False) -> None:
        try:
            params = self.remove_page.params.build_params()
            self.batch_page.apply_remove_params(params)
            if not silent:
                n = len(params.resolved_pairs())
                self._set_status(f"已从选色替换同步 {n} 组颜色参数")
                self._log(f"批量页已同步 {n} 组颜色")
        except Exception as exc:  # noqa: BLE001
            if not silent:
                self._set_status(f"同步失败: {exc}")

    def _toggle_log(self) -> None:
        self._log_expanded = not self._log_expanded
        self.log_panel.setVisible(self._log_expanded)
        # 文案固定「日志」，完整状态放 ToolTip，避免小窗裁字
        self.btn_log.setText("日志")
        self.btn_log.setToolTip(
            "隐藏日志面板（Ctrl+L）" if self._log_expanded else "显示日志面板（Ctrl+L）"
        )

    def _set_status(self, text: str) -> None:
        self.status_label.set_full_text(text or "")

    def _log(self, text: str) -> None:
        self.log_panel.append(text)
        if not self._log_expanded and any(k in text for k in ("错误", "失败", "完成")):
            self._log_expanded = True
            self.log_panel.setVisible(True)
            self.btn_log.setText("日志")
            self.btn_log.setToolTip("隐藏日志面板（Ctrl+L）")

    # ----- jobs -----

    def start_job(self, request: JobRequest) -> None:
        if self._worker is not None:
            QMessageBox.information(self, "忙碌", "已有任务在运行，请等待或先停止。")
            return
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.btn_stop.setEnabled(True)
        self.remove_page.set_busy(True)
        self._set_status("处理中…")
        self._log(f"任务开始: {request.kind}")

        thread, worker = start_job(request, self)
        self._thread = thread
        self._worker = worker
        worker.progress.connect(self._on_progress)
        worker.log_line.connect(self._log)
        worker.finished_ok.connect(self._on_ok)
        worker.failed.connect(self._on_fail)

    def stop_job(self) -> None:
        if self._worker:
            self._worker.request_cancel()
            self._set_status("正在取消…")
            self._log("用户请求取消")

    def _on_progress(self, cur: int, total: int, msg: str) -> None:
        if total > 0:
            self.progress.setValue(int(cur / total * 100))
        self._set_status(msg)

    def _on_ok(self, result: object) -> None:
        self._cleanup_job()
        self.progress.setValue(100)
        self._set_status("完成")
        self._log(f"完成: {result}")
        path = None
        if isinstance(result, Path):
            path = result
        elif isinstance(result, list) and result:
            path = Path(result[0])
        elif isinstance(result, str):
            path = Path(result)
        msg = f"处理完成。\n{result}"
        if path and path.exists():
            ret = QMessageBox.question(self, "完成", msg + "\n\n是否打开所在文件夹？")
            if ret == QMessageBox.Yes:
                self._open_path(path.parent if path.is_file() else path)
        else:
            QMessageBox.information(self, "完成", msg)

    def _on_fail(self, err: str) -> None:
        self._cleanup_job()
        self._set_status("失败")
        self._log(f"错误: {err}")
        QMessageBox.critical(self, "处理失败", err)

    def _cleanup_job(self) -> None:
        self._worker = None
        self._thread = None
        self.btn_stop.setEnabled(False)
        self.remove_page.set_busy(False)
        self.progress.setVisible(False)

    def _open_path(self, path: Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            QMessageBox.warning(self, "无法打开", str(exc))

    def _open_user_guide(self) -> None:
        """在系统浏览器中打开在线使用说明。"""
        if not QDesktopServices.openUrl(QUrl(DOCS_URL)):
            QMessageBox.warning(
                self,
                "无法打开",
                f"无法打开浏览器，请手动访问：\n{DOCS_URL}",
            )

    def _about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(f"关于 {APP_NAME_ZH}")
        box.setIcon(QMessageBox.Information)
        box.setText(f"{APP_NAME_FULL} v{APP_VERSION}")
        box.setInformativeText(
            f"{APP_TAGLINE}\n{APP_ABOUT}\n\n"
            "选色替换 · 区域遮盖 · 灰度 · 组合处理（多步一次导出）。\n"
            "文档全局打开一次，各模块共用；结果多为光栅化 PDF。\n"
            "请仅处理你有权处理的文档。\n\n"
            f"使用说明：{DOCS_URL}"
        )
        docs_btn = box.addButton("使用说明", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is docs_btn:
            self._open_user_guide()


    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        prefs = dict(self._prefs)
        prefs.update(self.remove_page.collect_prefs())
        prefs["last_mode"] = self._prefs.get("last_mode", MODE_REMOVE)
        try:
            prefs["window_geometry"] = self.saveGeometry().data().hex()
        except Exception:
            pass
        save_prefs(prefs)
        self._close_global_document()
        if self._worker:
            self._worker.request_cancel()
        super().closeEvent(event)
