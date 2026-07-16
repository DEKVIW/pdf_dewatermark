# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onedir for 净页 JingYe GUI.

import sys
from pathlib import Path

block_cipher = None

SPECDIR = Path(SPEC).resolve().parent if "SPEC" in dir() else Path(".").resolve()
ROOT = SPECDIR.parent if SPECDIR.name == "packaging" else SPECDIR
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

datas = [
    (str(ROOT / "packaging" / "user_README.txt"), "."),
]
res = ROOT / "src" / "pdf_dewatermark" / "gui" / "resources"
if res.is_dir():
    datas.append((str(res), "pdf_dewatermark/gui/resources"))

icon_file = ROOT / "packaging" / "app.ico"
if not icon_file.is_file():
    icon_file = res / "app.ico"
icon_arg = str(icon_file) if icon_file.is_file() else None

hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "qfluentwidgets",
    "fitz",
    "PIL",
    "numpy",
    "pdf_dewatermark",
    "pdf_dewatermark.gui",
    "pdf_dewatermark.gui.app",
    "pdf_dewatermark.gui.main_window",
    "pdf_dewatermark.gui.branding",
    "pdf_dewatermark.gui.icons",
    "pdf_dewatermark.processor",
]

a = Analysis(
    [str(ROOT / "packaging" / "gui_entry.py")],
    pathex=[str(SRC), str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "notebook"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JingYe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_arg,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="JingYe",
)
