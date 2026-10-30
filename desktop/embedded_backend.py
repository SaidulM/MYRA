"""Run MYRA's local HTTP backend inside the desktop GUI process.

There is deliberately no child Python process, no Command Prompt and no
PowerShell: the packaged ``MYRA.exe`` (or ``pythonw`` in source mode)
owns both the Qt event loop and this daemon server thread.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path


class EmbeddedBackend:
    def __init__(self, host="127.0.0.1", port=8765):
        self.host = host
        self.port = int(port)
        self._server = None
        self._thread = None

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self):
        if self.running:
            return True
        root = Path(__file__).resolve().parent.parent
        backend = root / "backend"
        # In a PyInstaller one-folder build the backend package is already
        # importable; these path inserts are harmless in source mode too.
        for candidate in (str(root), str(backend)):
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
        os.environ.setdefault("MYRA_HOST", self.host)
        os.environ.setdefault("MYRA_PORT", str(self.port))

        import server

        # Creates/checks MYRA's unified DB, workspace, voice/news/feedback
        # files, .env starter and default UI settings.  It is idempotent
        # and does not start external processes or download models.
        server.initialize_runtime()
        try:
            self._server = server.create_server(self.host, self.port)
        except OSError:
            # A MYRA backend may already be running on this loopback port.
            # The GUI health check decides whether it is usable.
            return False
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="myra-embedded-backend",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self):
        if self._server is not None:
            try:
                self._server.shutdown()
            finally:
                self._server.server_close()
                self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
