"""
Screenshot script — captures the redesigned launcher dialog.

Saves: final_v2_launcher.png at the project root.

Run via:
    python _screenshot_launcher.py
"""
import os
import sys
import time
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Use offscreen platform so screenshots work in headless / sandboxed envs.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from theme import get_stylesheet
from ui.launcher import LauncherDialog

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(OUT_DIR, "final_v2_launcher.png")


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(get_stylesheet())

    launcher = LauncherDialog()
    # Center on the primary screen so the screenshot looks intentional.
    scr = app.primaryScreen().availableGeometry()
    launcher.move(
        scr.x() + (scr.width() - launcher.width()) // 2,
        scr.y() + (scr.height() - launcher.height()) // 2,
    )
    launcher.show()
    # Let layout settle, the rounded-mask timer fire, and the float animation
    # start. 600ms is enough — we only need a stable frame, not a full anim.
    for _ in range(60):
        QApplication.processEvents()
        time.sleep(0.025)

    pix = launcher.grab()
    if pix.isNull():
        screen = app.primaryScreen()
        pix = screen.grabWindow(0)
    pix.save(OUT_PATH, "PNG")
    print(f"  saved: {OUT_PATH}  ({pix.width()}x{pix.height()})")

    # Exit cleanly so the script doesn't hang in the offscreen platform.
    QTimer.singleShot(0, app.quit)
    app.exec()


if __name__ == "__main__":
    main()
