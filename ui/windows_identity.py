import ctypes
import logging
import sys


def set_app_identity():
    if sys.platform != "win32":
        return
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    function = shell.SetCurrentProcessExplicitAppUserModelID
    function.argtypes = [ctypes.c_wchar_p]
    function.restype = ctypes.c_long
    result = function("BuddyDesk.DesktopAgent")
    if result < 0:
        logging.getLogger(__name__).warning("Windows application identity could not be set")
