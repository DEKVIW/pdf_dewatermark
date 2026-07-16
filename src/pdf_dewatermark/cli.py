"""命令行入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .models import ColorMethod, FillMode, ImageFormat, RemoveParams
from .paths import default_output_path, ensure_runtime_dirs
from .processor import process_pdf_grayscale, process_pdf_remove


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pdf-dewatermark-cli",
        description="PDF 去水印命令行工具",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    rm = sub.add_parser("remove", help="按颜色去水印")
    rm.add_argument("input", type=Path)
    rm.add_argument("-o", "--output", type=Path, default=None)
    rm.add_argument("--r", type=int, required=True, help="水印 R")
    rm.add_argument("--g", type=int, required=True, help="水印 G")
    rm.add_argument("--b", type=int, required=True, help="水印 B")
    rm.add_argument("--tolerance", type=float, default=30.0)
    rm.add_argument("--dpi", type=int, default=200)
    rm.add_argument(
        "--method",
        choices=[m.value for m in ColorMethod],
        default=ColorMethod.COLOR_PICK.value,
    )
    rm.add_argument(
        "--fill",
        choices=[m.value for m in FillMode],
        default=FillMode.SOLID.value,
    )
    rm.add_argument("--contrast", type=float, default=1.2)
    rm.add_argument("--resolution-factor", type=float, default=3.0)
    rm.add_argument(
        "--format",
        choices=[ImageFormat.JPEG.value, ImageFormat.PNG.value, "jpg"],
        default=ImageFormat.JPEG.value,
        help="导出图像格式（默认 jpeg）",
    )
    rm.add_argument("--jpeg-quality", type=int, default=92)
    rm.add_argument(
        "--allow-upsample",
        action="store_true",
        help="允许渲染超过扫描原图分辨率（默认会限制不放大）",
    )
    rm.add_argument("--bg", type=int, nargs=3, default=[255, 255, 255], metavar=("R", "G", "B"))

    gs = sub.add_parser("grayscale", help="转灰度 PDF")
    gs.add_argument("input", type=Path)
    gs.add_argument("-o", "--output", type=Path, default=None)
    gs.add_argument("--dpi", type=int, default=200)

    return p


def main(argv: list[str] | None = None) -> int:
    ensure_runtime_dirs()
    args = build_parser().parse_args(argv)

    def _progress(cur: int, total: int, msg: str) -> None:
        print(f"[{cur}/{total}] {msg}")

    if args.cmd == "remove":
        out = args.output or default_output_path(args.input)
        fmt = args.format
        if fmt == "jpg":
            fmt = ImageFormat.JPEG.value
        params = RemoveParams(
            method=ColorMethod(args.method),
            watermark_colors=[(args.r, args.g, args.b)],
            background=tuple(args.bg),  # type: ignore[arg-type]
            tolerance=args.tolerance,
            fill_mode=FillMode(args.fill),
            contrast=args.contrast,
            dpi=args.dpi,
            resolution_factor=args.resolution_factor,
            image_format=ImageFormat(fmt),
            jpeg_quality=int(args.jpeg_quality),
            avoid_upsample=not bool(args.allow_upsample),
            export_preset="custom",
        )
        path = process_pdf_remove(args.input, out, params, progress=_progress)
        print(f"已保存: {path}")
        return 0

    if args.cmd == "grayscale":
        out = args.output or default_output_path(args.input, suffix="灰度")
        from .models import GrayscaleParams

        path = process_pdf_grayscale(
            args.input,
            out,
            GrayscaleParams(dpi=args.dpi),
            progress=_progress,
        )
        print(f"已保存: {path}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
