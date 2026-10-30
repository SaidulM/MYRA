"""Optional Playwright browser automation for MYRA.

The browser is visible by default and every write-like action is exposed
through confirmation-required skills.  MYRA refuses CAPTCHA/MFA/password
flows and asks the owner to complete those steps personally.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from urllib.parse import urlparse

import config
import paths


class BrowserControlError(Exception):
    pass


_CHALLENGE_WORDS = (
    "captcha", "recaptcha", "verify you are human", "i'm not a robot",
    "two-factor", "two factor", "multi-factor", "one-time password",
    "verification code", "enter the code", "authenticator app",
)
_SECRET_WORDS = ("password", "passcode", "one-time", "otp", "pin code", "security code", "cvv")


def detect_blocking_challenge(text):
    lowered = str(text or "").lower()
    return next((word for word in _CHALLENGE_WORDS if word in lowered), "")


def _validate_url(url):
    url = str(url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BrowserControlError("A complete http/https URL is required.")
    return url


def _looks_secret(selector, label=""):
    haystack = f"{selector or ''} {label or ''}".lower()
    return any(word in haystack for word in _SECRET_WORDS) or "type=password" in haystack.replace(" ", "")


def browser_status():
    installed = importlib.util.find_spec("playwright") is not None
    return {
        "playwright_package_installed": installed,
        "ready": installed,
        "visible_by_default": True,
        "preferred_channels": ["msedge", "chrome", "bundled-chromium"],
        "note": (
            "Install requirements-automation.txt and a Playwright browser, or use installed Edge/Chrome. "
            "MYRA never bypasses CAPTCHA, MFA or password prompts."
        ),
    }


class BrowserController:
    """Small stateless controller; each call opens and closes cleanly."""

    def __init__(self, playwright_factory=None):
        self._factory = playwright_factory

    def _sync_playwright(self):
        if self._factory:
            return self._factory()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserControlError(
                "Playwright is not installed. Install requirements-automation.txt to enable browser automation."
            ) from exc
        return sync_playwright()

    def _launch(self, playwright):
        headless = config.get("MYRA_BROWSER_HEADLESS", "").lower() in {"1", "true", "yes"}
        errors = []
        for channel in ("msedge", "chrome", None):
            try:
                kwargs = {"headless": headless}
                if channel:
                    kwargs["channel"] = channel
                return playwright.chromium.launch(**kwargs), channel or "bundled-chromium"
            except Exception as exc:
                errors.append(f"{channel or 'chromium'}: {exc.__class__.__name__}")
        raise BrowserControlError("No usable Edge/Chrome/Chromium browser was found for Playwright. " + "; ".join(errors))

    @staticmethod
    def _snapshot(page):
        text = ""
        try:
            text = page.locator("body").inner_text(timeout=3000)
        except Exception:
            text = page.content()[:8000]
        challenge = detect_blocking_challenge(text)
        links = []
        try:
            for item in page.locator("a[href]").all()[:40]:
                label = " ".join((item.inner_text(timeout=500) or "").split())[:120]
                href = item.get_attribute("href") or ""
                if href:
                    links.append({"label": label, "href": href[:500]})
        except Exception:
            pass
        controls = []
        try:
            for item in page.locator("button, input, select, textarea, [role='button']").all()[:80]:
                label = ""
                try:
                    label = " ".join((item.inner_text(timeout=300) or "").split())[:100]
                except Exception:
                    pass
                controls.append({
                    "label": label,
                    "type": item.get_attribute("type") or "",
                    "name": item.get_attribute("name") or "",
                    "placeholder": item.get_attribute("placeholder") or "",
                    "id": item.get_attribute("id") or "",
                })
        except Exception:
            pass
        return {
            "url": page.url,
            "title": page.title(),
            "text": " ".join(str(text).split())[:10000],
            "links": links,
            "controls": controls,
            "challenge_detected": challenge,
            "verified": True,
        }

    def _with_page(self, url, action=None):
        url = _validate_url(url)
        with self._sync_playwright() as playwright:
            browser, channel = self._launch(playwright)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(600)
                before = self._snapshot(page)
                if before.get("challenge_detected"):
                    raise BrowserControlError(
                        "A CAPTCHA/MFA/human-verification step was detected. Please complete it personally; MYRA will not bypass it."
                    )
                extra = action(page) if action else {}
                after = self._snapshot(page)
                return {"browser_channel": channel, "before": before, "after": after, **extra, "verified": True}
            finally:
                browser.close()

    def snapshot(self, url):
        result = self._with_page(url)
        return {**result["after"], "browser_channel": result["browser_channel"]}

    def screenshot(self, url, filename="browser.png"):
        name = Path(str(filename or "browser.png")).name
        if not name.lower().endswith((".png", ".jpg", ".jpeg")):
            name += ".png"
        destination = paths.workspace_dir() / name

        def action(page):
            page.screenshot(path=str(destination), full_page=False)
            return {"screenshot": destination.name, "bytes": destination.stat().st_size if destination.exists() else 0}

        return self._with_page(url, action)

    def click(self, url, selector="", text=""):
        selector = str(selector or "").strip()
        text = str(text or "").strip()
        if not selector and not text:
            raise BrowserControlError("Provide a CSS selector or visible text to click.")

        def action(page):
            locator = page.locator(selector).first if selector else page.get_by_text(text, exact=False).first
            locator.click(timeout=8000)
            page.wait_for_timeout(800)
            return {"clicked": selector or text}

        return self._with_page(url, action)

    def fill(self, url, selector, value, submit=False):
        selector = str(selector or "").strip()
        if not selector:
            raise BrowserControlError("A CSS selector is required for browser fill.")
        if _looks_secret(selector):
            raise BrowserControlError("MYRA refuses to fill password/OTP/security-code fields.")

        def action(page):
            locator = page.locator(selector).first
            input_type = (locator.get_attribute("type") or "").lower()
            label = " ".join(filter(None, [locator.get_attribute("name") or "", locator.get_attribute("placeholder") or "", locator.get_attribute("aria-label") or ""]))
            if input_type == "password" or _looks_secret("", label):
                raise BrowserControlError("MYRA refuses to fill password/OTP/security-code fields.")
            locator.fill(str(value), timeout=8000)
            if submit:
                locator.press("Enter")
                page.wait_for_timeout(900)
            return {"filled": selector, "submitted": bool(submit)}

        return self._with_page(url, action)


_CONTROLLER = None


def get_browser_controller():
    global _CONTROLLER
    if _CONTROLLER is None:
        _CONTROLLER = BrowserController()
    return _CONTROLLER
