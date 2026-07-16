"""后台任务：只调用 core/processor，不拼 shell。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from PySide6.QtCore import QObject, QThread, Signal

from ..models import GrayscaleParams, RegionRect, RemoveParams
from ..processor import (
    process_batch_remove,
    process_pdf_grayscale,
    process_pdf_pipeline,
    process_pdf_regions,
    process_pdf_remove,
)


@dataclass
class JobRequest:
    kind: str  # remove | grayscale | region | batch_remove | pipeline
    input_path: str = ""
    output_path: str = ""
    params: Optional[RemoveParams] = None
    gray_params: Optional[GrayscaleParams] = None
    regions: List[RegionRect] = field(default_factory=list)
    page_indices: Optional[List[int]] = None
    batch_files: List[str] = field(default_factory=list)
    batch_output_dir: str = ""
    region_dpi: int = 200
    # 组合处理：有序步骤 grayscale | remove | region
    pipeline_steps: List[str] = field(default_factory=list)
    gray_dpi: int = 200


class JobWorker(QObject):
    log_line = Signal(str)
    progress = Signal(int, int, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, request: JobRequest) -> None:
        super().__init__()
        self.request = request
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def _cancelled(self) -> bool:
        return self._cancel

    def _on_progress(self, cur: int, total: int, msg: str) -> None:
        self.progress.emit(cur, total, msg)
        self.log_line.emit(msg)

    def run(self) -> None:
        try:
            req = self.request
            if req.kind == "remove":
                assert req.params is not None
                result = process_pdf_remove(
                    req.input_path,
                    req.output_path,
                    req.params,
                    page_indices=req.page_indices,
                    progress=self._on_progress,
                    should_cancel=self._cancelled,
                )
            elif req.kind == "grayscale":
                result = process_pdf_grayscale(
                    req.input_path,
                    req.output_path,
                    req.gray_params or GrayscaleParams(),
                    progress=self._on_progress,
                    should_cancel=self._cancelled,
                )
            elif req.kind == "region":
                result = process_pdf_regions(
                    req.input_path,
                    req.output_path,
                    req.regions,
                    dpi=int(req.region_dpi or 200),
                    page_indices=req.page_indices,
                    progress=self._on_progress,
                    should_cancel=self._cancelled,
                )
            elif req.kind == "batch_remove":
                assert req.params is not None
                result = process_batch_remove(
                    req.batch_files,
                    req.batch_output_dir or str(Path(req.output_path).parent),
                    req.params,
                    progress=self._on_progress,
                    should_cancel=self._cancelled,
                )
            elif req.kind == "pipeline":
                result = process_pdf_pipeline(
                    req.input_path,
                    req.output_path,
                    req.pipeline_steps,
                    remove_params=req.params,
                    regions=req.regions,
                    gray_dpi=int(req.gray_dpi or 200),
                    progress=self._on_progress,
                    should_cancel=self._cancelled,
                )
            else:
                raise ValueError(f"未知任务: {req.kind}")

            if self._cancel:
                self.failed.emit("已取消")
                return
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001 — 传到 UI
            self.failed.emit(str(exc))


def start_job(request: JobRequest, parent: QObject | None = None) -> tuple[QThread, JobWorker]:
    thread = QThread(parent)
    worker = JobWorker(request)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished_ok.connect(thread.quit)
    worker.failed.connect(thread.quit)
    worker.finished_ok.connect(worker.deleteLater)
    worker.failed.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread, worker
