"""BuddyDesk — PyInstaller entry point.

When frozen (packaged as .exe), this script IS the application.
The icon is embedded in the .exe via build.spec.
"""
import sys
import os

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
