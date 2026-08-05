"""
ChatGPT browser-assisted registration.
Uses Playwright + real Chrome profile for the CF/sentinel steps that
require a real browser, auto-fills email + OTP, and extracts tokens
from the authenticated session.

Flow:
1. Create Cloudflare temp email (or configured provider)
2. Open real Chrome (persistent profile copy) at chatgpt.com/auth/login
3. Auto-fill email, submit
4. Auto-fetch OTP from mailbox, auto-fill it
5. USER manually clicks Continue / completes signup in the visible window
6. Script polls /api/auth/session and extracts access_token
"""

import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from playwright.sync_api import sync_playwright


def _chrome_profile_copy(src_profile: str = "") -> str:
    """Copy real Chrome profile for persistent context (avoids locking)."""
    if not src_profile:
        candidates = [
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Default"),
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Profile 1"),
        ]
        for c in candidates:
            if Path(c).exists():
                src_profile = c
                break
    if not src_profile or not Path(src_profile).exists():
        return ""

    dst = Path(tempfile.gettempdir()) / "opencode" / f"chrome_profile_{int(time.time())}"
    dst.mkdir(parents=True, exist_ok=True)
    for f in ("Cookies", "Local State", "Preferences"):
        s = Path(src_profile) / f
        if not s.exists():
            continue
        try:
            if s.is_dir():
                shutil.copytree(str(s), str(dst / f), dirs_exist_ok=True)
            else:
                shutil.copy2(str(s), str(dst / f))
        except Exception:
            pass
    return str(dst)


class BrowserRegistrar:
    """Browser-assisted ChatGPT registration."""

    def __init__(
        self,
        email_provider: Any,
        proxy: str = "",
        chrome_profile: str = "",
        on_log: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[str], None]] = None,
    ):
        self.email_provider = email_provider
        self.proxy = proxy or ""
        self.chrome_profile = chrome_profile or ""
        self.on_log = on_log or (lambda msg: None)
        self.on_progress = on_progress or (lambda msg: None)

    def _log(self, msg: str):
        self.on_log(msg)

    def _progress(self, msg: str):
        self.on_progress(msg)

    def _fill_first(self, page, selectors, value, timeout=10000):
        for sel in selectors:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.fill(value, timeout=timeout)
                return True
        return False

    def _click_submit(self, page):
        for sel in ["button[type='submit']", "button:has-text('Continue')",
                    "button:has-text('Create')", "button:has-text('Sign up')",
                    "button:has-text('完成')", "button:has-text('继续')"]:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click(timeout=3000)
                    return True
            except Exception:
                continue
        return False

    def register(self, email: str = "", password: str = "") -> Dict[str, Any]:
        """Register a ChatGPT account. Returns dict with tokens."""
        if not email:
            self._progress("Creating email...")
            email = self.email_provider.create_email()
            self._log(f"Created email: {email}")
        else:
            self._progress(f"Using email: {email}")
            # Provider already has this email as current; ensure state matches
            self.email_provider._current_email = email
            if hasattr(self.email_provider, "_current_jwt"):
                pass  # keep existing JWT if already created for this address

        profile = _chrome_profile_copy(self.chrome_profile)
        if not profile:
            raise RuntimeError(
                "No Chrome profile found. Set chrome_profile or use a browser with existing profile."
            )

        proxy_cfg = {"server": self.proxy} if self.proxy else None
        result: Dict[str, Any] = {}

        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                profile,
                channel="chrome",
                headless=False,
                proxy=proxy_cfg,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                page = ctx.new_page()
                page.goto("https://chatgpt.com/auth/login", wait_until="load", timeout=60000)
                time.sleep(4)

                # Fill email
                self._progress("Filling email...")
                self._fill_first(
                    page,
                    ["input[type='email']", "input[name='email']", "input[type='text']"],
                    email,
                )
                page.keyboard.press("Enter")
                self._log("Email submitted")
                time.sleep(3)

                # Wait for and fill OTP
                self._progress("Waiting for verification code...")
                code = self.email_provider.wait_for_code(email, timeout=90)
                if not code:
                    raise RuntimeError("Timed out waiting for verification code")
                self._log(f"Got verification code: {code}")

                self._progress("Filling verification code...")
                filled = self._fill_first(
                    page,
                    [
                        "input[autocomplete='one-time-code']",
                        "input[inputmode='numeric']",
                        "input[placeholder*='code']",
                        "input[placeholder*='Code']",
                    ],
                    code,
                )
                if not filled:
                    for inp in page.locator("input:visible[type='text']").all():
                        ph = inp.get_attribute("placeholder") or ""
                        if "email" not in ph.lower():
                            inp.fill(code, timeout=5000)
                            filled = True
                            break
                if not filled:
                    raise RuntimeError("Could not find OTP input")
                self._log("OTP filled - PLEASE click Continue/complete signup in the browser window")

                # Wait for user to complete signup, polling session token
                self._progress("Waiting for you to complete signup in the browser...")
                start = time.time()
                session_data = {}
                while time.time() - start < 300:
                    time.sleep(2)
                    try:
                        resp = page.request.get("https://chatgpt.com/api/auth/session")
                        if resp.status == 200:
                            data = resp.json() if resp.text else {}
                            if data and data.get("accessToken"):
                                session_data = data
                                break
                    except Exception:
                        pass

                if not session_data:
                    raise RuntimeError("Registration may have completed but no access token found")

                # Extract result
                user = session_data.get("user") if isinstance(session_data.get("user"), dict) else {}
                result = {
                    "email": str(user.get("email") or email).strip(),
                    "password": password,
                    "access_token": str(session_data.get("accessToken") or session_data.get("access_token") or "").strip(),
                    "type": "chatgpt",
                }
                for camel, snake in (("refreshToken", "refresh_token"), ("idToken", "id_token"),
                                     ("sessionToken", "session_token"), ("expires", "expired")):
                    value = str(session_data.get(camel) or session_data.get(snake) or "").strip()
                    if value:
                        result[snake] = value
                user_id = str(user.get("id") or user.get("user_id") or "").strip()
                if user_id:
                    result["user_id"] = user_id
                account = session_data.get("account") if isinstance(session_data.get("account"), dict) else {}
                if account.get("id"):
                    result["account_id"] = account.get("id")

                if not result["access_token"]:
                    raise RuntimeError("Registration complete but no access_token")

                self._log(f"Registration successful: {result['email']}")
                return result
            finally:
                ctx.close()
