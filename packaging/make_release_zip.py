# -*- coding: utf-8 -*-
"""用 Python 打 zip，避免 Compress-Archive 对中文文件名处理异常。

用法:
  python packaging/make_release_zip.py <source_dir> <zip_path>
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: make_release_zip.py <source_dir> <zip_path>", file=sys.stderr)
        return 2
    src = Path(sys.argv[1])
    zip_path = Path(sys.argv[2])
    if not src.is_dir():
        print(f"not a directory: {src}", file=sys.stderr)
        return 1

    if zip_path.exists():
        zip_path.unlink()
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    # ZIP_DEFLATED；文件名用 UTF-8 标志（Python 3.11+ zipfile 支持）
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in src.rglob("*"):
            if path.is_file():
                arc = path.relative_to(src).as_posix()
                # ZipInfo with utf-8 flag
                zf.write(path, arcname=arc)

    print(f"zip written: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
