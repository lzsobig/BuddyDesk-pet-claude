"""BuddyDesk — PyInstaller entry point.

When frozen (packaged as .exe), this script IS the application.
The icon is embedded in the .exe via build.spec.
"""
import sys
import os


def _bootstrap_qt():
    """Pin the Qt platform plugin path before any PySide6 import.

    Prevents "no Qt platform plugin could be initialized" when stray Qt DLLs
    on PATH (WeChat/QQ installers etc.) shadow the correct plugin.
    """
    try:
        import importlib.util
        spec = importlib.util.find_spec("PySide6")
        if spec is not None and spec.submodule_search_locations:
            base = list(spec.submodule_search_locations)[0]
            plugins = os.path.join(base, "plugins")
            if os.path.isdir(plugins):
                os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plugins
        os.environ.pop("QT_QPA_PLATFORM", None)
    except Exception:
        pass


_bootstrap_qt()

if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Prevent double-launch (same logic as main.py)
from PySide6.QtWidgets import QApplication
_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)

from main import BuddyDeskApp
BuddyDeskApp().run()
