# -*- mode: python ; coding: utf-8 -*-
"""BuddyDesk Windows onedir build.

The runtime resolves frozen assets from ``<exe>/_internal/assets``. PyInstaller
places Analysis datas below ``_internal`` for onedir builds, so the source
assets directory is mapped to the ``assets`` destination here.
"""
from pathlib import Path

ROOT = Path(SPEC).parent
assets = ROOT / "assets"

# Keep this list explicit. Recursive collection of the project packages makes
# PyInstaller inspect unrelated packages installed in the developer's Python
# environment (notably torch, which produced a 4.2 GB build).
hiddenimports = [
    "openai",
    "requests",
    "PySide6.QtSvg",
    "PySide6.QtMultimedia",
    "sounddevice",
    "soundfile",
    "onnxruntime",
    "kaldi_native_fbank",
]

analysis = Analysis(
    [str(ROOT / "launch.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(assets), "assets")],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        # These are unrelated packages that may be present in a developer
        # environment and are not runtime dependencies of BuddyDesk.
        "torch",
        "torchvision",
        "torchaudio",
        "transformers",
        "pandas",
        "scipy",
        "sklearn",
        "cv2",
        "matplotlib",
        "jupyter",
        "IPython",
        "sympy",
    ],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="BuddyDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(assets / "buddydesk.ico"),
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="BuddyDesk",
)
