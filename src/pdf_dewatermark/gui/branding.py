"""产品品牌常量 — 净页 JingYe。"""

from __future__ import annotations

from pathlib import Path

# —— 产品命名 ——
# 中文名：净页 —— 「净」清理杂质色，「页」面向 PDF 页面
APP_NAME_ZH = "净页"
APP_NAME_EN = "JingYe"
APP_NAME_FULL = "净页 JingYe"
APP_WINDOW_TITLE = "净页 — PDF 清理工作台"
APP_ABOUT = "选色替换 · 区域遮盖 · 灰度转换 · 批量处理"
APP_TAGLINE = "把页面上的杂质色清理干净"
APP_ORG = "JingYe"
APP_VERSION = "0.2.6"
APP_EXE_NAME = "JingYe"
# 在线使用说明（帮助菜单 / 关于 中打开）
DOCS_URL = "https://blog.yilanapp.com/posts/adbbe073/"

_PKG_DIR = Path(__file__).resolve().parent
_RESOURCES = _PKG_DIR / "resources"


def resources_dir() -> Path:
    return _RESOURCES


def icon_path() -> Path | None:
    """应用主图标（.ico 优先，便于 Windows 任务栏）。"""
    candidates = [
        _RESOURCES / "app.ico",
        _RESOURCES / "app.png",
        Path.cwd() / "resources" / "app.ico",
        Path.cwd() / "resources" / "app.png",
        Path.cwd() / "packaging" / "app.ico",
        Path.cwd() / "packaging" / "app.png",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def icon_png_path() -> Path | None:
    for path in (
        _RESOURCES / "app.png",
        Path.cwd() / "packaging" / "app.png",
        icon_path(),
    ):
        if path is not None and path.is_file():
            return path
    return None
