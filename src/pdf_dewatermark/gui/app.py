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


def _silence_qfluent_tips() -> None:
    """
    QFluentWidgets 在 import 时会 print 带 ANSI/emoji 的 Pro 广告。
    Windows 控制台常乱码；pythonw 下 sys.stdout 为 None，print 必须有可写对象。
    """
    class _NullStream:
        def write(self, s):  # noqa: ANN001
            return 0 if s is None else len(s)

        def flush(self):
            return None

        def isatty(self):
            return False

    class _Filter:
        def __init__(self, stream):
            self._stream = stream if stream is not None else _NullStream()

        def write(self, s):  # noqa: ANN001
            if not s:
                return 0
            if "QFluentWidgets Pro" in s or ("Tips:" in s and "qfluentwidgets" in s.lower()):
                return len(s)
            if "\033[" in s and "Tips" in s:
                return len(s)
            try:
                return self._stream.write(s)
            except Exception:
                return len(s)

        def flush(self):
            try:
                return self._stream.flush()
            except Exception:
                return None

        def isatty(self):
            try:
                return bool(self._stream.isatty())
            except Exception:
                return False

        def __getattr__(self, name: str):
            return getattr(self._stream, name)

    try:
        sys.stdout = _Filter(sys.stdout)  # type: ignore[assignment]
        sys.stderr = _Filter(sys.stderr)  # type: ignore[assignment]
    except Exception:
        pass


def main() -> None:
    _bootstrap_paths()
    # 尽量用 UTF-8 输出，减轻 python.exe 控制台乱码
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    _silence_qfluent_tips()

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
