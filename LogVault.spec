# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys


ROOT = Path(SPECPATH)
if sys.platform == "win32":
    ICON_FILE = str(ROOT / "assets" / "logvault.ico")
elif sys.platform == "darwin":
    ICON_FILE = str(ROOT / "assets" / "logvault.icns")
else:
    ICON_FILE = None

a = Analysis(
    [str(ROOT / "run_gui.py")],
    pathex=[str(ROOT), str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "assets" / "logvault.png"), "assets"),
        (str(ROOT / "assets" / "logvault.svg"), "assets"),
        (str(ROOT / "assets" / "logvault.ico"), "assets"),
        (str(ROOT / "assets" / "logvault.icns"), "assets"),
        (str(ROOT / "assets" / "WordMark.svg"), "assets"),
    ],
    hiddenimports=[
        "tkinter",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.scrolledtext",
        "tkinter.ttk",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="LogVault",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_FILE,
)
