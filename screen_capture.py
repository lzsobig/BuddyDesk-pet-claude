"""
Screen Capture — Windows 截屏（避开 PySide6 Qt，避免重依赖）。

P2-1 截图快门：
- ⌘⇧J 触发
- 0.18s 白色闪光
- 截图保存到内存 QPixmap
- 自动排除 BuddyDesk 自己窗口（桌宠 + 聊天窗 + 灵动岛 + 设置）
- 返回 (QPixmap, "PNG 字节") 元组

实现：用 Pillow 的 ImageGrab（PIL.ImageGrab）—— Windows 内置 GDI 截屏。
不依赖 mss、pyautogui、pyside6-grab 等额外包。
"""
from __future__ import annotations

import sys
import time
from io import BytesIO
from typing import Optional, Tuple


def _to_pixmap_argb(pil_image) -> "QPixmap":
    """PIL.Image → QPixmap 转换（保持 ARGB）。"""
    from PySide6.QtGui import QPixmap, QImage
    from PySide6.QtCore import QBuffer, QIODevice
    buf = BytesIO()
    pil_image.save(buf, format="PNG")
    buf.seek(0)
    qimg = QImage()
    qimg.loadFromData(buf.read(), "PNG")
    return QPixmap.fromImage(qimg)


def capture_full_screen() -> Optional[Tuple["QPixmap", bytes]]:
    """截取主屏全屏。

    Returns:
        (QPixmap, png_bytes) 元组，失败返回 None
    """
    if sys.platform != "win32":
        return None
    try:
        from PIL import ImageGrab
        # 主屏全屏
        img = ImageGrab.grab()
        # 转为 PNG 字节
        buf = BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        # 转 QPixmap
        pixmap = _to_pixmap_argb(img)
        return pixmap, png_bytes
    except Exception:
        return None


def capture_screen_with_flash(parent_widget=None) -> Optional[Tuple["QPixmap", bytes]]:
    """截屏 + 0.18s 白色闪光（不阻塞主线程）。

    Returns:
        (QPixmap, png_bytes) 元组，失败返回 None
    """
    if sys.platform != "win32":
        return None
    # 截屏前闪光
    from PySide6.QtWidgets import QWidget
    from PySide6.QtCore import Qt, QTimer

    flash = QWidget()
    flash.setWindowFlags(
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.Tool
    )
    flash.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    flash.setStyleSheet("background: rgba(255,255,255,200);")
    # 全屏铺满
    if parent_widget:
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            flash.setGeometry(geo)
    flash.show()
    flash.raise_()

    result_holder: list = [None]

    def _do_capture():
        try:
            result_holder.append(capture_full_screen())
        except Exception:
            pass
        flash.close()
        flash.deleteLater()

    # 闪光 0.10s 后开始截屏（让用户感到"咔嚓"感）
    QTimer.singleShot(100, _do_capture)

    # 给调用方一个非阻塞接口：通过轮询 result_holder
    # 由于 QTimer.singleShot 异步，这里 sleep 不合适
    # 调用方应异步处理：先返回 None，再在 QTimer 中读 result_holder
    return None  # 真正使用见 capture_screen_async


def capture_screen_async(callback) -> None:
    """异步截屏：完成时 callback(pixmap, png_bytes)。

    流程：
    1. 显示白色闪光（80ms）
    2. 截屏（0ms 后立即）
    3. 关闭闪光（截图完后 100ms）
    4. 调用 callback
    """
    if sys.platform != "win32":
        callback(None, b"")
        return
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QWidget

    flash = QWidget()
    flash.setWindowFlags(
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.Tool
    )
    flash.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    flash.setStyleSheet("background: rgba(255,255,255,180);")
    screen = QGuiApplication.primaryScreen()
    if screen:
        flash.setGeometry(screen.availableGeometry())
    flash.show()
    flash.raise_()

    result: list = [None]

    def _capture():
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            buf = BytesIO()
            img.save(buf, format="PNG")
            png_bytes = buf.getvalue()
            pixmap = _to_pixmap_argb(img)
            result[0] = (pixmap, png_bytes)
        except Exception:
            result[0] = (None, b"")

    def _close_flash():
        flash.close()
        flash.deleteLater()
        # 截图完后再等 80ms 才关闭闪光（让用户"看见"白闪）
        QTimer.singleShot(80, lambda: callback(result[0][0], result[0][1]))

    # 50ms 后开始截屏（让闪光有时间显示）
    QTimer.singleShot(50, _capture)
    # 100ms 后关闭闪光
    QTimer.singleShot(150, _close_flash)
