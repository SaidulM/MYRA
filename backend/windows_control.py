"""Semantic Windows control backend for MYRA.

Preferred path: Windows UI Automation through pywinauto.  Coordinate
fallback through PyAutoGUI is available only through separate high-risk,
confirmation-required skills.  Password/OTP fields are refused.
"""
from __future__ import annotations

import importlib.util
import os
import threading


class WindowsControlError(Exception):
    pass


_SECRET_WORDS = ("password", "passcode", "one-time", "one time", "otp", "pin code", "security code", "cvv")


def _clean(value, limit=250):
    return " ".join(str(value or "").split())[:limit]


def _is_secret_control(metadata):
    haystack = " ".join(
        str(metadata.get(key) or "") for key in ("name", "automation_id", "class_name")
    ).lower()
    return bool(metadata.get("is_password")) or any(word in haystack for word in _SECRET_WORDS)


class _PywinautoBackend:
    def __init__(self):
        if os.name != "nt":
            raise WindowsControlError("Windows UI Automation is available only on Windows.")
        try:
            from pywinauto import Desktop
        except ImportError as exc:
            raise WindowsControlError(
                "pywinauto is not installed. Install requirements-automation.txt to enable semantic Windows control."
            ) from exc
        self.Desktop = Desktop

    def _desktop(self):
        return self.Desktop(backend="uia")

    @staticmethod
    def _is_password(wrapper):
        try:
            return bool(wrapper.iface_element.CurrentIsPassword)
        except Exception:
            pass
        try:
            return bool(wrapper.element_info.element.CurrentIsPassword)
        except Exception:
            return False

    def metadata(self, wrapper, include_value=False):
        info = wrapper.element_info
        rect = info.rectangle
        data = {
            "name": _clean(getattr(info, "name", "") or wrapper.window_text()),
            "control_type": _clean(getattr(info, "control_type", ""), 80),
            "automation_id": _clean(getattr(info, "automation_id", ""), 160),
            "class_name": _clean(getattr(info, "class_name", ""), 160),
            "process_id": getattr(info, "process_id", None),
            "rectangle": {
                "left": int(rect.left), "top": int(rect.top),
                "right": int(rect.right), "bottom": int(rect.bottom),
            },
            "is_password": self._is_password(wrapper),
        }
        try:
            data["enabled"] = bool(wrapper.is_enabled())
        except Exception:
            data["enabled"] = None
        try:
            data["visible"] = bool(wrapper.is_visible())
        except Exception:
            data["visible"] = None
        if include_value and not _is_secret_control(data):
            try:
                data["value"] = _clean(wrapper.window_text(), 1000)
            except Exception:
                data["value"] = ""
        return data

    def windows(self):
        out = []
        for wrapper in self._desktop().windows():
            try:
                data = self.metadata(wrapper)
            except Exception:
                continue
            if data.get("name") or data.get("visible"):
                out.append(data)
        return out

    def _find_window(self, title=""):
        title = _clean(title, 250).casefold()
        candidates = []
        for wrapper in self._desktop().windows():
            try:
                name = _clean(wrapper.window_text())
                if not title:
                    if wrapper.is_visible() and name:
                        candidates.append(wrapper)
                elif name.casefold() == title:
                    return wrapper
                elif title in name.casefold():
                    candidates.append(wrapper)
            except Exception:
                continue
        if candidates:
            return candidates[0]
        raise WindowsControlError("The requested window was not found.")

    def _find_control(self, window_title="", name="", automation_id="", control_type="", class_name="", index=0):
        window = self._find_window(window_title)
        matches = []
        try:
            wrappers = [window] + list(window.descendants())
        except Exception:
            wrappers = [window]
        for wrapper in wrappers:
            try:
                data = self.metadata(wrapper, include_value=False)
            except Exception:
                continue
            if name and _clean(name).casefold() not in data["name"].casefold():
                continue
            if automation_id and automation_id != data["automation_id"]:
                continue
            if control_type and control_type.casefold() != data["control_type"].casefold():
                continue
            if class_name and class_name.casefold() not in data["class_name"].casefold():
                continue
            matches.append((wrapper, data))
        index = max(0, int(index or 0))
        if index >= len(matches):
            raise WindowsControlError("The requested control was not found in that window.")
        return matches[index]

    def observe(self, window_title="", max_controls=160):
        window = self._find_window(window_title)
        controls = []
        try:
            wrappers = list(window.descendants())
        except Exception:
            wrappers = []
        for wrapper in wrappers[: max(1, min(int(max_controls or 160), 500))]:
            try:
                data = self.metadata(wrapper, include_value=True)
            except Exception:
                continue
            if _is_secret_control(data):
                data.pop("value", None)
                data["value_redacted"] = True
            controls.append(data)
        return {"window": self.metadata(window), "controls": controls, "count": len(controls), "verified": True}

    def focus_window(self, window_title):
        window = self._find_window(window_title)
        window.set_focus()
        return {"window": self.metadata(window), "focused": True, "verified": True}

    def invoke(self, **query):
        wrapper, data = self._find_control(**query)
        if _is_secret_control(data):
            raise WindowsControlError("MYRA refuses to interact with password/OTP controls.")
        try:
            wrapper.iface_invoke.Invoke()
            method = "invoke"
        except Exception:
            wrapper.click_input()
            method = "click_input"
        return {"control": data, "method": method, "verified": True}

    def set_text(self, text, **query):
        wrapper, data = self._find_control(**query)
        if _is_secret_control(data):
            raise WindowsControlError("MYRA refuses to type into password/OTP/security-code fields.")
        text = str(text)
        try:
            wrapper.set_edit_text(text)
        except Exception:
            wrapper.set_focus()
            wrapper.type_keys("^a{BACKSPACE}", set_focus=False)
            wrapper.type_keys(text, with_spaces=True, set_focus=False)
        verified = False
        try:
            verified = wrapper.window_text() == text
        except Exception:
            pass
        return {"control": data, "verified": verified}

    def send_keys(self, keys, window_title=""):
        if window_title:
            window = self._find_window(window_title)
            window.set_focus()
            window.type_keys(str(keys), with_spaces=True, set_focus=False)
            target = self.metadata(window)
        else:
            from pywinauto.keyboard import send_keys as pywinauto_send_keys
            pywinauto_send_keys(str(keys), with_spaces=True)
            target = {}
        return {"window": target, "keys_sent": True, "verified": True}


class WindowsController:
    def __init__(self, backend=None, coordinate_backend=None):
        self._backend = backend
        self._coordinate_backend = coordinate_backend
        self._stop = threading.Event()

    def status(self):
        return {
            "platform_windows": os.name == "nt",
            "pywinauto_installed": importlib.util.find_spec("pywinauto") is not None,
            "pyautogui_installed": importlib.util.find_spec("pyautogui") is not None,
            "semantic_ready": os.name == "nt" and importlib.util.find_spec("pywinauto") is not None,
            "coordinate_ready": importlib.util.find_spec("pyautogui") is not None,
            "emergency_stopped": self._stop.is_set(),
            "safety": "Semantic actions are confirmation-required and disabled by default; password/OTP fields are refused.",
        }

    def emergency_stop(self):
        self._stop.set()
        return {"ok": True, "emergency_stopped": True}

    def reset_emergency_stop(self):
        self._stop.clear()
        return {"ok": True, "emergency_stopped": False}

    def _check(self):
        if self._stop.is_set():
            raise WindowsControlError("MYRA computer control is emergency-stopped. Reset it manually in the desktop UI.")

    def _semantic(self):
        self._check()
        if self._backend is not None:
            return self._backend
        self._backend = _PywinautoBackend()
        return self._backend

    def list_windows(self):
        backend = self._semantic()
        if hasattr(backend, "list_windows"):
            windows = backend.list_windows()
        else:
            windows = backend.windows()
        return {"windows": windows, "count": len(windows), "verified": True}

    def observe(self, window_title="", max_controls=160):
        return self._semantic().observe(window_title=window_title, max_controls=max_controls)

    def focus_window(self, window_title):
        return self._semantic().focus_window(window_title)

    def invoke_control(self, window_title="", name="", automation_id="", control_type="", class_name="", index=0):
        return self._semantic().invoke(
            window_title=window_title, name=name, automation_id=automation_id,
            control_type=control_type, class_name=class_name, index=index,
        )

    def set_text(self, text, window_title="", name="", automation_id="", control_type="", class_name="", index=0):
        return self._semantic().set_text(
            text, window_title=window_title, name=name, automation_id=automation_id,
            control_type=control_type, class_name=class_name, index=index,
        )

    def send_keys(self, keys, window_title=""):
        if not str(keys).strip():
            raise WindowsControlError("Keys are required.")
        return self._semantic().send_keys(keys, window_title=window_title)

    # Coordinate fallback ----------------------------------------------
    def _gui(self):
        self._check()
        if self._coordinate_backend is not None:
            return self._coordinate_backend
        try:
            import pyautogui
        except ImportError as exc:
            raise WindowsControlError(
                "PyAutoGUI is not installed. Install requirements-automation.txt to enable coordinate fallback."
            ) from exc
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.08
        self._coordinate_backend = pyautogui
        return pyautogui

    def click_point(self, x, y, button="left", double=False):
        gui = self._gui()
        x, y = int(x), int(y)
        try:
            width, height = gui.size()
            if not (0 <= x < width and 0 <= y < height):
                raise WindowsControlError("Click point is outside the screen.")
        except WindowsControlError:
            raise
        except Exception:
            pass
        if double:
            gui.doubleClick(x=x, y=y, button=button)
        else:
            gui.click(x=x, y=y, button=button)
        return {"x": x, "y": y, "button": button, "double": bool(double), "verified": True}

    def type_text(self, text, interval_seconds=0.01):
        text = str(text)
        if len(text) > 5000:
            raise WindowsControlError("Coordinate typing is limited to 5000 characters per action.")
        self._gui().typewrite(text, interval=max(0.0, min(float(interval_seconds or 0), 0.2)))
        return {"characters": len(text), "verified": True}

    def hotkey(self, keys):
        if isinstance(keys, str):
            parts = [part.strip() for part in keys.replace("+", ",").split(",") if part.strip()]
        else:
            parts = [str(part).strip() for part in (keys or []) if str(part).strip()]
        if not parts or len(parts) > 5:
            raise WindowsControlError("Hotkey requires 1–5 keys.")
        self._gui().hotkey(*parts)
        return {"keys": parts, "verified": True}


_CONTROLLER = None


def get_windows_controller():
    global _CONTROLLER
    if _CONTROLLER is None:
        _CONTROLLER = WindowsController()
    return _CONTROLLER
