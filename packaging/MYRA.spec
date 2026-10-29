# PyInstaller spec for the MYRA desktop build (smooth GPU web shell).
# The generated MYRA.exe is a windowed GUI executable (console=False):
# no Command Prompt or PowerShell window is opened at runtime.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent

hiddenimports = [
    # Local backend modules are imported through backend/ pathex.
    "agent", "api_v1", "browser_control", "chat", "config", "core_agent",
    "core_memory", "live_vision", "memory", "news", "notes", "paths",
    "providers", "reminders", "research", "server", "service",
    "skill_registry", "skills_manager", "voice", "voice_engine", "voice_studio",
    "windows_control",
    # Secure storage and optional engines.
    "keyring.backends.Windows", "keyring.backends.fail", "keyring.backends.null",
    "edge_tts", "faster_whisper", "huggingface_hub", "playwright.sync_api",
    "pyautogui", "pywinauto", "win32com.client", "webview", "clr",
]

datas = [
    (str(root / "ui"), "ui"),
    (str(root / "assets"), "assets"),
    (str(root / "docs"), "docs"),
]
binaries = []

# Optional engines are installed by packaging/build_windows.py.  collect_all
# is guarded so this spec can still be inspected on a minimal machine.
for package in ("faster_whisper", "playwright", "edge_tts", "webview"):
    try:
        package_datas, package_binaries, package_hidden = collect_all(package)
        datas += package_datas
        binaries += package_binaries
        hiddenimports += package_hidden
    except Exception:
        pass

a = Analysis(
    [str(root / "run_desktop.py")],
    pathex=[str(root), str(root / "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
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
    disable_windowed_traceback=False,
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
