"""界面偏好（非密钥）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

from ...paths import DATA_DIR

PREFS_FILE = DATA_DIR / "gui_prefs.json"
MAX_RECENT = 12

DEFAULT_PREFS: dict[str, Any] = {
    "last_mode": "remove",
    "last_dir": "",
    "recent_files": [],
    "tolerance": 30,
    "dpi": 200,
    "method": "color_pick",
    "fill_mode": "solid",
    "contrast": 1.2,
    "morph_open": 0,
    "morph_close": 0,
    "resolution_factor": "3.0",
    "sharpen": False,
    "image_format": "jpeg",
    "jpeg_quality": 92,
    "avoid_upsample": True,
    "export_preset": "balanced",
    "window_geometry": "",
    "view_mode": "preview",
    "params_open": False,
    "export_profile": "v2",
}


def load_prefs() -> dict[str, Any]:
    prefs = dict(DEFAULT_PREFS)
    if not PREFS_FILE.exists():
        return prefs
    try:
        raw = json.loads(PREFS_FILE.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            prefs.update(raw)
    except (OSError, json.JSONDecodeError):
        pass

    if prefs.get("method") in ("distance", "distance_lab"):
        prefs["method"] = "color_pick"

    # 算法默认（硬替换等）
    if prefs.get("algo_profile") != "legacy_v1":
        prefs["method"] = (
            prefs["method"]
            if prefs.get("method") in ("color_pick", "threshold")
            else "color_pick"
        )
        prefs["fill_mode"] = "solid"
        prefs["morph_open"] = 0
        prefs["morph_close"] = 0
        prefs["contrast"] = 1.2
        if int(prefs.get("tolerance") or 0) < 5:
            prefs["tolerance"] = 30
        prefs["algo_profile"] = "legacy_v1"

    # 导出体积/清晰度默认：一次性迁移到 v2（均衡 JPEG，不再强制 300+PNG）
    if prefs.get("export_profile") != "v2":
        prefs["dpi"] = 200
        prefs["image_format"] = "jpeg"
        prefs["jpeg_quality"] = 92
        prefs["avoid_upsample"] = True
        prefs["export_preset"] = "balanced"
        prefs["resolution_factor"] = "3.0"
        prefs["export_profile"] = "v2"

    # 合法化
    if prefs.get("image_format") not in ("png", "jpeg", "jpg"):
        prefs["image_format"] = "jpeg"
    if prefs.get("image_format") == "jpg":
        prefs["image_format"] = "jpeg"
    try:
        q = int(prefs.get("jpeg_quality", 92))
        prefs["jpeg_quality"] = max(70, min(100, q))
    except (TypeError, ValueError):
        prefs["jpeg_quality"] = 92
    if prefs.get("export_preset") not in ("balanced", "quality", "small", "custom"):
        prefs["export_preset"] = "balanced"

    if not isinstance(prefs.get("recent_files"), list):
        prefs["recent_files"] = []

    return prefs


def save_prefs(prefs: dict[str, Any]) -> None:
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    merged = dict(DEFAULT_PREFS)
    merged.update(prefs)
    merged["algo_profile"] = "legacy_v1"
    merged["export_profile"] = "v2"
    PREFS_FILE.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def push_recent(prefs: dict[str, Any], path: str | Path) -> dict[str, Any]:
    """把路径插到最近文件列表头部。"""
    p = str(Path(path).resolve())
    recent: List[str] = [x for x in prefs.get("recent_files") or [] if x != p]
    recent.insert(0, p)
    prefs["recent_files"] = recent[:MAX_RECENT]
    prefs["last_dir"] = str(Path(p).parent)
    return prefs
