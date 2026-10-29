# PyInstaller spec for the MYRA native desktop build.
# Build from the repository root with packaging/build_windows.ps1.
from pathlib import Path

root = Path(SPECPATH).parent

hiddenimports = [
    "keyring.backends.Windows",
    "keyring.backends.fail",
    "keyring.backends.null",
]

a = Analysis(
    [str(root / "run_desktop.py")],
    pathex=[str(root), str(root / "backend")],
    binaries=[],
    datas=[
        (str(root / "ui"), "ui"),
        (str(root / "assets"), "assets"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MYRA",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(root / "assets" / "myra.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MYRA",
)
