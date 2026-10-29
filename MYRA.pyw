"""Double-click MYRA launcher for Windows source installs.

The .pyw extension uses pythonw.exe, so MYRA opens as a pure Python GUI
with no Command Prompt or PowerShell window.  The packaged MYRA.exe is
preferred once built.
"""
from run_desktop import main

if __name__ == "__main__":
    raise SystemExit(main())
