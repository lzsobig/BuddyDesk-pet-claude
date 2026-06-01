"""
Screenshot script — captures 3 Dynamic Island states for visual verification.

States captured:
  1. final_v2_island_ready.png    — idle (default on show)
  2. final_v2_island_thinking.png — thinking (after set_state("thinking"))
  3. final_v2_island_error.png    — error    (after set_state("error", "网络连接超时"))

Run via:
  python _screenshot_island.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Use offscreen platform so screenshots work in headless environments
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from ui.dynamic_island import DynamicIsland

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def grab(widget, path: str):
    """Grab the widget region (with a little padding for the drop shadow)."""
    # Wait one event loop tick so the most recent paint is applied
    QApplication.processEvents()
    time.sleep(0.05)
    QApplication.processEvents()

    pix = widget.grab()
    if pix.isNull():
        # Fallback: render the whole primary screen
        screen = QApplication.primaryScreen()
        pix = screen.grabWindow(0)
    pix.save(path, "PNG")
    print(f"  saved: {path}  ({pix.width()}x{pix.height()})")


def main():
    app = QApplication(sys.argv)

    island = DynamicIsland()
    # No on_click callback for the screenshot
    island._on_click = None
    # Place at fixed coords for deterministic capture
    island.move(400, 200)
    island.resize(island.width(), island.height())
    island.show()
    QApplication.processEvents()
    time.sleep(0.4)  # let show-fade finish

    # 1. Ready (idle)
    print("Capturing: ready")
    grab(island, os.path.join(OUT_DIR, "final_v2_island_ready.png"))

    # 2. Thinking
    print("Capturing: thinking")
    island.set_state("thinking")
    # Wait for the 200ms size animation + 100ms cross-fade to finish
    for _ in range(40):
        QApplication.processEvents()
        time.sleep(0.025)
    grab(island, os.path.join(OUT_DIR, "final_v2_island_thinking.png"))

    # 3. Error
    print("Capturing: error")
    island.set_state("error", "网络连接超时，请重试")
    for _ in range(40):
        QApplication.processEvents()
        time.sleep(0.025)
    grab(island, os.path.join(OUT_DIR, "final_v2_island_error.png"))

    # 4. Result (bonus, not required by task)
    print("Capturing: result (bonus)")
    island.set_state("result", "打开了 VS Code")
    for _ in range(40):
        QApplication.processEvents()
        time.sleep(0.025)
    grab(island, os.path.join(OUT_DIR, "final_v2_island_result.png"))

    # 5. Notify (bonus)
    print("Capturing: notify (bonus)")
    island.set_state("notify", "该喝水了")
    for _ in range(40):
        QApplication.processEvents()
        time.sleep(0.025)
    grab(island, os.path.join(OUT_DIR, "final_v2_island_notify.png"))

    print("done.")


if __name__ == "__main__":
    main()
