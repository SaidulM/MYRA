"""Small standard-library HTTP client for MYRA's local backend."""
import json
import os
import urllib.error
import urllib.request


class ApiError(Exception):
    pass


class ApiClient:
    def __init__(self, base_url=None, token=None):
        self.base_url = (base_url or os.environ.get("MYRA_BACKEND_URL") or "http://127.0.0.1:8765").rstrip("/")
        self.token = token or os.environ.get("MYRA_API_TOKEN", "")

    def request(self, method, path, payload=None, timeout=90):
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["X-MYRA-Token"] = self.token
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {"ok": True}
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode("utf-8"))
                message = body.get("error") or body.get("message") or str(body)
            except Exception:
                message = f"Backend returned HTTP {exc.code}"
            raise ApiError(message) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise ApiError(f"MYRA backend is not reachable: {exc}") from exc
        except ValueError as exc:
            raise ApiError("MYRA backend returned invalid JSON") from exc

    def get(self, path, timeout=30):
        return self.request("GET", path, timeout=timeout)

    def post(self, path, payload=None, timeout=90):
        return self.request("POST", path, payload=payload or {}, timeout=timeout)

    def stream_post(self, path, payload=None, timeout=180):
        """Yield parsed NDJSON events from a streaming POST endpoint."""
        data = json.dumps(payload or {}).encode("utf-8")
        headers = {"Accept": "application/x-ndjson", "Content-Type": "application/json"}
        if self.token:
            headers["X-MYRA-Token"] = self.token
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                for raw in response:
                    line = raw.decode("utf-8", errors="replace").strip() if isinstance(raw, bytes) else str(raw).strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode("utf-8"))
                message = body.get("error") or body.get("message") or str(body)
            except Exception:
                message = f"Backend returned HTTP {exc.code}"
            raise ApiError(message) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise ApiError(f"MYRA backend is not reachable: {exc}") from exc

    def put(self, path, payload=None, timeout=30):
        return self.request("PUT", path, payload=payload or {}, timeout=timeout)

    def delete(self, path, timeout=30):
        return self.request("DELETE", path, timeout=timeout)
