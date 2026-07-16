"""「应用本页遮盖区域」对话框。"""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import LineEdit

from ...core.page_ranges import (
    ApplyPageMode,
    format_pages_preview,
    resolve_apply_pages,
)
from ..theme import SPACE_SM, SPACE_XS, apply_control_font, apply_label


class ApplyRegionsDialog(QDialog):
    """
    选择本页矩形的应用范围。

    返回 (mode, custom_spec, replace) ；取消返回 None。
    """

    def __init__(
        self,
        parent: QWidget | None,
        *,
        page_count: int,
        current_index: int,
        template_count: int,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("应用本页遮盖区域")
        self.setMinimumWidth(420)
        self._page_count = page_count
        self._current_index = current_index
        self._template_count = template_count

        root = QVBoxLayout(self)
        root.setSpacing(SPACE_SM)

        src = QLabel(
            f"来源：第 {current_index + 1} 页 · {template_count} 个矩形\n"
            "将把这些矩形应用到下面选中的页面（坐标按页比例相同）。"
        )
        apply_label(src, "body")
        src.setWordWrap(True)
        root.addWidget(src)

        self._group = QButtonGroup(self)
        self._radios: dict[ApplyPageMode, QRadioButton] = {}

        def add_radio(mode: ApplyPageMode, text: str, checked: bool = False) -> QRadioButton:
            rb = QRadioButton(text)
            apply_control_font(rb)
            self._group.addButton(rb)
            self._radios[mode] = rb
            rb.setChecked(checked)
            rb.toggled.connect(self._refresh_preview)
            root.addWidget(rb)
            return rb

        add_radio(ApplyPageMode.ALL, "全部页面", checked=True)
        add_radio(ApplyPageMode.ODD, "奇数页（第 1、3、5… 页）")
        add_radio(ApplyPageMode.EVEN, "偶数页（第 2、4、6… 页）")
        add_radio(
            ApplyPageMode.EVERY_OTHER_FROM,
            f"从当前页起每隔一页（第 {current_index + 1}、{current_index + 3}… 页）",
        )
        add_radio(ApplyPageMode.CUSTOM, "自定义页码")

        custom_row = QHBoxLayout()
        custom_row.setContentsMargins(24, 0, 0, 0)
        self.custom_edit = LineEdit()
        self.custom_edit.setPlaceholderText("例如 1,5,9  或  2-20  或  1-3,8,12")
        apply_control_font(self.custom_edit)
        self.custom_edit.textChanged.connect(self._refresh_preview)
        custom_row.addWidget(self.custom_edit, 1)
        root.addLayout(custom_row)

        self.replace_cb = QCheckBox("替换目标页上已有区域（推荐，避免重复叠加）")
        self.replace_cb.setChecked(True)
        apply_control_font(self.replace_cb)
        root.addWidget(self.replace_cb)

        self.preview = QLabel("")
        apply_label(self.preview, "caption")
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet("color: #0ea5e9;")
        root.addWidget(self.preview)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("应用")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._ok_btn = buttons.button(QDialogButtonBox.Ok)
        self._radios[ApplyPageMode.CUSTOM].toggled.connect(self._sync_custom_enabled)
        self._sync_custom_enabled()
        self._refresh_preview()

    def _selected_mode(self) -> ApplyPageMode:
        for mode, rb in self._radios.items():
            if rb.isChecked():
                return mode
        return ApplyPageMode.ALL

    def _sync_custom_enabled(self) -> None:
        on = self._radios[ApplyPageMode.CUSTOM].isChecked()
        self.custom_edit.setEnabled(on)
        if on:
            self.custom_edit.setFocus(Qt.OtherFocusReason)

    def _target_indices(self) -> list[int]:
        mode = self._selected_mode()
        return resolve_apply_pages(
            mode,
            self._page_count,
            current_index=self._current_index,
            custom_spec=self.custom_edit.text(),
        )

    def _refresh_preview(self) -> None:
        indices = self._target_indices()
        if not indices:
            self.preview.setText("预览：没有匹配的页面，请检查选项或自定义页码。")
            self._ok_btn.setEnabled(False)
            return
        self._ok_btn.setEnabled(True)
        self.preview.setText(
            f"预览：将应用到 {format_pages_preview(indices)}"
        )

    def result_values(self) -> Tuple[ApplyPageMode, str, bool]:
        return (
            self._selected_mode(),
            self.custom_edit.text().strip(),
            self.replace_cb.isChecked(),
        )


def run_apply_regions_dialog(
    parent: QWidget | None,
    *,
    page_count: int,
    current_index: int,
    template_count: int,
) -> Optional[Tuple[ApplyPageMode, str, bool]]:
    dlg = ApplyRegionsDialog(
        parent,
        page_count=page_count,
        current_index=current_index,
        template_count=template_count,
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    mode, spec, replace = dlg.result_values()
    # 再校验一次自定义
    pages = resolve_apply_pages(
        mode, page_count, current_index=current_index, custom_spec=spec
    )
    if not pages:
        return None
    return mode, spec, replace
