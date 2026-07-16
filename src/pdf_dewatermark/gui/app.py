"""GUI 应用入口。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap_paths() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
    else:
        here = Path(__file__).resolve()
        # .../src/pdf_dewatermark/gui/app.py → parents[3] = project root
        root = here.parents[3] if len(here.parents) >= 4 else Path.cwd()
        src_dir = root / "src"
        if src_dir.is_dir() and str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
    try:
        os.chdir(root)
    except OSError:
        pass
    return root


def main() -> None:
    _bootstrap_paths()

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from qfluentwidgets import Theme, setTheme

    from pdf_dewatermark.gui.branding import APP_NAME_EN, APP_ORG, APP_WINDOW_TITLE, icon_path
    from pdf_dewatermark.gui.main_window import MainWindow
    from pdf_dewatermark.paths import ensure_runtime_dirs

    ensure_runtime_dirs()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME_EN)
    app.setOrganizationName(APP_ORG)
    setTheme(Theme.AUTO)

    icon = icon_path()
    if icon is not None:
        app.setWindowIcon(QIcon(str(icon)))

    window = MainWindow()
    window.setWindowTitle(APP_WINDOW_TITLE)
    if icon is not None:
        window.setWindowIcon(QIcon(str(icon)))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
