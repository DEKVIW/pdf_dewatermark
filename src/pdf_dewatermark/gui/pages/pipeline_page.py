"""组合处理：编排灰度 / 选色 / 区域，一次导出。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
)

from ...paths import default_output_path
from .. import icons as I
from ..theme import CTRL_HEIGHT, SPACE_MD, SPACE_SM, apply_control_font, apply_label

# (step_id, 显示名, 说明)
_DEFAULT_STEPS: Sequence[Tuple[str, str, str]] = (
    ("grayscale", "灰度转换", "整页转灰度（预处理，可选）"),
    ("remove", "选色替换", "使用选色页已配置的颜色组"),
    ("region", "区域遮盖", "使用区域页已绘制的矩形"),
)


class PipelinePage(QWidget):
    status = Signal(str)
    request_job = Signal(object)
    log = Signal(str)
    # 请求切换到配置页
    navigate_to = Signal(str)  # remove | region | grayscale

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path: Optional[Path] = None
        self._page_count = 0
        # 回调：由 MainWindow 注入，拉取最新配置状态
        self._get_remove_ready: Optional[Callable[[], Tuple[bool, str]]] = None
        self._get_region_ready: Optional[Callable[[], Tuple[bool, str]]] = None
        self._get_remove_params = None
        self._get_regions = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SPACE_SM)

        card = CardWidget()
        lay = QVBoxLayout(card)
        lay.setSpacing(SPACE_SM)
        lay.addWidget(StrongBodyLabel("组合处理"))
        lay.addWidget(
            BodyLabel(
                "同一本 PDF 只打开一次：在「选色替换 / 区域遮盖」配好参数后，"
                "在此勾选步骤、调整顺序，一次导出。"
                "各模块仍可单独导出，互不影响。"
            )
        )

        self.doc_label = QLabel("当前文档：未打开（请用顶栏或菜单打开 PDF）")
        apply_label(self.doc_label, "body")
        self.doc_label.setWordWrap(True)
        lay.addWidget(self.doc_label)

        lay.addWidget(StrongBodyLabel("处理步骤（可勾选 · 可调序）"))
        self.step_list = QListWidget()
        self.step_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.step_list.setMinimumHeight(160)
        for sid, title, hint in _DEFAULT_STEPS:
            item = QListWidgetItem(f"{title}  —  {hint}")
            item.setData(Qt.UserRole, sid)
            item.setFlags(
                item.flags()
                | Qt.ItemIsUserCheckable
                | Qt.ItemIsEnabled
                | Qt.ItemIsSelectable
            )
            # 默认：选色 + 区域开，灰度关
            item.setCheckState(
                Qt.Checked if sid in ("remove", "region") else Qt.Unchecked
            )
            self.step_list.addItem(item)
        lay.addWidget(self.step_list)

        ord_row = QHBoxLayout()
        self.btn_up = PushButton("上移")
        self.btn_down = PushButton("下移")
        self.btn_refresh = PushButton("刷新配置状态")
        for b in (self.btn_up, self.btn_down, self.btn_refresh):
            apply_control_font(b)
            b.setFixedHeight(CTRL_HEIGHT)
        self.btn_up.clicked.connect(self._move_up)
        self.btn_down.clicked.connect(self._move_down)
        self.btn_refresh.clicked.connect(self.refresh_status)
        ord_row.addWidget(self.btn_up)
        ord_row.addWidget(self.btn_down)
        ord_row.addWidget(self.btn_refresh)
        ord_row.addStretch(1)
        lay.addLayout(ord_row)

        self.status_box = BodyLabel("")
        self.status_box.setWordWrap(True)
        lay.addWidget(self.status_box)

        link_row = QHBoxLayout()
        self.btn_goto_remove = PushButton("去配置选色…")
        self.btn_goto_region = PushButton("去配置区域…")
        self.btn_goto_gray = PushButton("灰度单独页…")
        for b in (self.btn_goto_remove, self.btn_goto_region, self.btn_goto_gray):
            apply_control_font(b)
            b.setFixedHeight(CTRL_HEIGHT)
        self.btn_goto_remove.clicked.connect(lambda: self.navigate_to.emit("remove"))
        self.btn_goto_region.clicked.connect(lambda: self.navigate_to.emit("region"))
        self.btn_goto_gray.clicked.connect(lambda: self.navigate_to.emit("grayscale"))
        link_row.addWidget(self.btn_goto_remove)
        link_row.addWidget(self.btn_goto_region)
        link_row.addWidget(self.btn_goto_gray)
        link_row.addStretch(1)
        lay.addLayout(link_row)

        self.hint = BodyLabel(
            "推荐顺序：灰度（可选）→ 选色 → 区域。导出编码跟随选色页的「导出预设」。"
        )
        apply_label(self.hint, "caption")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)

        self.run_btn = PrimaryPushButton("组合导出…")
        self.run_btn.setIcon(I.ICO_EXPORT.icon())
        apply_control_font(self.run_btn)
        self.run_btn.setFixedHeight(CTRL_HEIGHT)
        self.run_btn.clicked.connect(self.run_export)
        lay.addWidget(self.run_btn)

        root.addWidget(card)
        root.addStretch(1)

    def bind_providers(
        self,
        *,
        get_remove_ready: Callable[[], Tuple[bool, str]],
        get_region_ready: Callable[[], Tuple[bool, str]],
        get_remove_params: Callable,
        get_regions: Callable,
    ) -> None:
        self._get_remove_ready = get_remove_ready
        self._get_region_ready = get_region_ready
        self._get_remove_params = get_remove_params
        self._get_regions = get_regions
        self.refresh_status()

    def set_document_path(self, path: Optional[Path], page_count: int = 0) -> None:
        self._path = Path(path) if path else None
        self._page_count = int(page_count or 0)
        if self._path:
            self.doc_label.setText(
                f"当前文档：{self._path.name}（{self._page_count} 页）· 与其它模块共用"
            )
        else:
            self.doc_label.setText("当前文档：未打开（请用顶栏或菜单打开 PDF）")
        self.refresh_status()

    def refresh_status(self) -> None:
        lines: List[str] = []
        if self._get_remove_ready:
            ok, msg = self._get_remove_ready()
            lines.append(f"选色：{'✓ ' if ok else '○ '}{msg}")
        if self._get_region_ready:
            ok, msg = self._get_region_ready()
            lines.append(f"区域：{'✓ ' if ok else '○ '}{msg}")
        lines.append("灰度：组合内勾选即可（无需先去灰度页导出）")
        self.status_box.setText("\n".join(lines))

    def _ordered_checked_steps(self) -> List[str]:
        steps: List[str] = []
        for i in range(self.step_list.count()):
            item = self.step_list.item(i)
            if item.checkState() == Qt.Checked:
                sid = item.data(Qt.UserRole)
                if sid:
                    steps.append(str(sid))
        return steps

    def _move_up(self) -> None:
        row = self.step_list.currentRow()
        if row <= 0:
            return
        item = self.step_list.takeItem(row)
        self.step_list.insertItem(row - 1, item)
        self.step_list.setCurrentRow(row - 1)

    def _move_down(self) -> None:
        row = self.step_list.currentRow()
        if row < 0 or row >= self.step_list.count() - 1:
            return
        item = self.step_list.takeItem(row)
        self.step_list.insertItem(row + 1, item)
        self.step_list.setCurrentRow(row + 1)

    def run_export(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        from ..workers import JobRequest

        if not self._path or not self._path.is_file():
            self.status.emit("请先打开 PDF（顶栏「打开」）")
            return
        steps = self._ordered_checked_steps()
        if not steps:
            self.status.emit("请至少勾选一个处理步骤")
            return

        remove_params = None
        regions = []
        if "remove" in steps:
            if not self._get_remove_params:
                self.status.emit("内部错误：未绑定选色参数")
                return
            try:
                remove_params = self._get_remove_params()
            except Exception as exc:  # noqa: BLE001
                self.status.emit(f"读取选色参数失败：{exc}")
                return
            if not remove_params.resolved_pairs():
                self.status.emit("已勾选选色，请先到选色页取样目标色")
                return
        if "region" in steps:
            if not self._get_regions:
                self.status.emit("内部错误：未绑定区域数据")
                return
            regions = list(self._get_regions())
            if not regions:
                self.status.emit("已勾选区域，请先到区域页绘制矩形")
                return

        initial = str(default_output_path(self._path, suffix="组合处理"))
        path, _ = QFileDialog.getSaveFileName(self, "组合导出 PDF", initial, "PDF (*.pdf)")
        if not path:
            return

        req = JobRequest(
            kind="pipeline",
            input_path=str(self._path),
            output_path=path,
            params=remove_params,
            regions=regions,
            pipeline_steps=steps,
            gray_dpi=200,
        )
        self.log.emit(f"组合导出 steps={steps} → {path}")
        self.status.emit("开始组合处理…")
        self.request_job.emit(req)
