# -*- coding: utf-8 -*-
"""写入绿色包元数据（UTF-8 BOM），避免 PowerShell 中文乱码。

用法:
  python packaging/write_dist_meta.py <dist_dir> <version>
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: write_dist_meta.py <dist_dir> <version>", file=sys.stderr)
        return 2

    dist = Path(sys.argv[1])
    ver = sys.argv[2].strip()
    root = Path(__file__).resolve().parent.parent
    dist.mkdir(parents=True, exist_ok=True)

    # 内容用 utf-8-sig（带 BOM），Windows 记事本可正确打开
    version_text = f"净页 JingYe {ver}\n"
    (dist / "VERSION.txt").write_text(version_text, encoding="utf-8-sig")

    readme_src = root / "packaging" / "user_README.txt"
    if readme_src.is_file():
        body = readme_src.read_text(encoding="utf-8")
    else:
        body = (
            f"净页 JingYe {ver}\n"
            "================\n\n"
            "双击 JingYe.exe 启动。\n"
        )
    # 中文文件名由 Python（Unicode）创建，不经过 PowerShell 字面量
    readme_cn = dist / "使用说明.txt"
    readme_cn.write_text(body, encoding="utf-8-sig")

    # 同时保留 ASCII 文件名，资源管理器/终端都稳
    (dist / "README.txt").write_text(body, encoding="utf-8-sig")

    # 清理历史乱码文件名（UTF-8 被 PowerShell 误写的残留）
    keep = {
        "VERSION.txt",
        "README.txt",
        "使用说明.txt",
        "user_README.txt",
    }
    for p in dist.glob("*.txt"):
        if p.name not in keep:
            try:
                p.unlink()
                print(f"removed leftover: {p.name!r}")
            except OSError as e:
                print(f"skip remove {p.name!r}: {e}")

    (dist / "data").mkdir(exist_ok=True)
    (dist / "output").mkdir(exist_ok=True)
    (dist / "logs").mkdir(exist_ok=True)

    ico = root / "packaging" / "app.ico"
    if ico.is_file():
        (dist / "app.ico").write_bytes(ico.read_bytes())

    # 自检：文件名必须是正确 Unicode
    assert readme_cn.name == "使用说明.txt", readme_cn.name
    assert (dist / "VERSION.txt").read_text(encoding="utf-8-sig").startswith("净页")
    print(f"meta written: {dist} (v{ver})")
    print(f"  VERSION.txt OK, 使用说明.txt OK, README.txt OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
