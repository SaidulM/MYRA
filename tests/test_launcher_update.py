import builtins
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

import launcher  # noqa: E402
import server  # noqa: E402


class LauncherUpdateTests(unittest.TestCase):
    def test_say_survives_missing_gui_stdout(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "launcher-log.txt"
            with mock.patch.object(launcher, "LOG_FILE", log), mock.patch.object(
                builtins, "print", side_effect=AttributeError("stdout is None under pythonw")
            ):
                launcher.say("update message")
            self.assertEqual(log.read_text(encoding="utf-8"), "update message\n")

    def _run_try_update(self, copy_result, save_result=True):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        source_zip = root / "source.zip"
        with zipfile.ZipFile(source_zip, "w") as archive:
            archive.writestr("MYRA-new/launcher.py", "# updated launcher\n")

        def fake_download(_url, dest):
            shutil.copyfile(source_zip, dest)

        save = mock.Mock(return_value=save_result)
        with mock.patch.object(launcher, "TMP_ZIP", root / "download.zip"), mock.patch.object(
            launcher, "TMP_DIR", root / "extract"
        ), mock.patch.object(launcher, "fetch_latest_sha", return_value="new-sha"), mock.patch.object(
            launcher, "local_version", return_value="old-sha"
        ), mock.patch.object(launcher, "_download", side_effect=fake_download), mock.patch.object(
            launcher, "_copy_update", return_value=copy_result
        ), mock.patch.object(launcher, "save_version", save), mock.patch.object(launcher, "say"):
            return launcher.try_update(), save

    def test_partial_copy_is_failed_and_version_is_not_saved(self):
        status, save = self._run_try_update((3, 1))
        self.assertEqual(status, "failed")
        save.assert_not_called()

    def test_version_marker_failure_is_failed(self):
        status, save = self._run_try_update((3, 0), save_result=False)
        self.assertEqual(status, "failed")
        save.assert_called_once_with("new-sha")

    def test_update_apply_endpoint_reports_failure_truthfully(self):
        srv = server.create_server("127.0.0.1", 0)
        port = srv.server_address[1]
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{port}/api/system/update-apply"
            with mock.patch.object(server.launcher, "try_update", return_value="failed"):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(
                        urllib.request.Request(url, data=b"", method="POST"), timeout=10
                    )
                self.assertEqual(caught.exception.code, 503)
                payload = json.loads(caught.exception.read().decode("utf-8"))
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["status"], "failed")

            with mock.patch.object(server.launcher, "try_update", return_value="updated"):
                with urllib.request.urlopen(
                    urllib.request.Request(url, data=b"", method="POST"), timeout=10
                ) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(json.loads(response.read().decode("utf-8"))["status"], "updated")
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=5)

    def test_update_popup_is_dismissible_and_failure_is_not_success(self):
        html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="closeUpdateBtn"', html)
        self.assertIn('id="dismissUpdateBtn"', html)
        self.assertIn("Later — Continue MYRA", html)
        self.assertIn("UPDATE_DISMISSED_KEY", js)
        self.assertIn("closeUpdateModal", js)
        self.assertIn("if (!res.ok || !data.ok)", js)


if __name__ == "__main__":
    unittest.main()
