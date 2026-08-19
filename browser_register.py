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
        headless: bool = False,
    ):
        self.email_provider = email_provider
        self.proxy = proxy or ""
        self.chrome_profile = chrome_profile or ""
        self.headless = bool(headless)
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
                    "button:has-text('Next')", "button:has-text('Create')",
                    "button:has-text('Sign up')", "button:has-text('完成')",
                    "button:has-text('继续')", "button[data-testid*='continue' i]",
                    "button[aria-label*='continue' i]"]:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click(timeout=3000)
                    return True
            except Exception:
                continue
        return False

    def _detect_profile_fields(self, page):
        """Locate the name/username + birthdate/age fields. Returns dict or None."""
        try:
            name_fields = []
            for sel in [
                "input[name='firstName']", "input[name='lastName']",
                "input[placeholder*='First name' i]", "input[placeholder*='Last name' i]",
                "input[aria-label*='first name' i]", "input[aria-label*='last name' i]",
            ]:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    name_fields.append(loc.first)
            single_field = None
            for sel in [
                "input[name='name']", "input[name='username']",
                "input[autocomplete='name']", "input[autocomplete='username']",
                "input[placeholder*='full name' i]", "input[placeholder*='Full name' i]",
            ]:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    single_field = loc.first
                    break
            age_field = None
            for sel in [
                "input[name='age']", "input[placeholder*='age' i]", "input[aria-label*='age' i]",
            ]:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    age_field = loc.first
                    break
            birthdate_hint = self._find_birthdate_locators(page)
            if single_field is not None or len(name_fields) > 0 or age_field is not None or birthdate_hint:
                return {"single": single_field, "name_fields": name_fields,
                        "age": age_field, "birthdate": birthdate_hint}
        except Exception:
            pass
        return None

    def _find_birthdate_locators(self, page):
        """Return month/day/year locators if the birthdate step is present."""
        found = []

        def pick(kind):
            for sel in [
                f"select[aria-label*='{kind}' i]", f"select[data-testid*='{kind}' i]",
                f"select[placeholder*='{kind}' i]",
                f"input[autocomplete='bday-{kind}']",
                f"input[placeholder*='{kind}' i]", f"input[aria-label*='{kind}' i]",
            ]:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    return loc.first
            return None

        for kind in ("month", "day", "year"):
            loc = pick(kind)
            if loc is not None:
                found.append(loc)
        if len(found) == 3:
            return found
        try:
            selects = [s for s in page.locator("select:visible").all() if s.is_visible()]
            if len(selects) == 3:
                return selects
        except Exception:
            pass
        return None if not found else found

    def _fill_birthdate(self, page, locators=None) -> bool:
        """Auto-fill the birthdate step (Month/Day/Year)."""
        import random
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        year = random.randint(1995, 2004)
        month_names = ["January", "February", "March", "April", "May", "June",
                       "July", "August", "September", "October", "November", "December"]
        filled_any = False

        def try_select(locator, value, label=None):
            nonlocal filled_any
            try:
                if label:
                    try:
                        locator.select_option(label=label)
                    except Exception:
                        locator.select_option(value=str(value))
                else:
                    locator.select_option(value=str(value))
                filled_any = True
                return True
            except Exception:
                try:
                    locator.select_option(value=str(value))
                    filled_any = True
                    return True
                except Exception:
                    pass
            return False

        def try_fill(locator, value):
            nonlocal filled_any
            try:
                locator.fill(str(value), timeout=3000)
                filled_any = True
                return True
            except Exception:
                pass
            return False

        if locators is None:
            locators = self._find_birthdate_locators(page)
        if not locators or len(locators) < 3:
            return False

        kinds = ["month", "day", "year"]
        vals = [month, day, year]
        for i, loc in enumerate(locators[:3]):
            kind = kinds[i]
            try:
                is_select = loc.evaluate("el => el.tagName") == "SELECT"
            except Exception:
                is_select = False
            if is_select:
                if kind == "month":
                    try_select(loc, vals[i], month_names[month - 1])
                else:
                    try_select(loc, vals[i])
            else:
                try_fill(loc, vals[i])
        return filled_any

    def _click_welcome_continue(self, page) -> bool:
        """Click the welcome-screen Continue CTA on chatgpt.com (idempotent)."""
        try:
            for sel in ["button:has-text('Continue')", "button:has-text('Next')",
                        "button:has-text('开始')", "button:has-text('继续')",
                        "button[data-testid*='continue' i]"]:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(timeout=3000)
                    self._log("Clicked welcome Continue")
                    return True
        except Exception:
            pass
        return False

    def _accept_terms(self, page) -> bool:
        """Check the Terms of Service checkbox and click Continue (poll up to 15s)."""
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                cb = None
                for sel in ["input[type='checkbox']", "input[aria-label*='agree' i]",
                            "input[name*='terms' i]", "input[aria-label*='terms' i]"]:
                    loc = page.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        cb = loc.first
                        break
                if cb is not None:
                    checked = False
                    try:
                        cb.check(timeout=3000)
                        checked = cb.is_checked()
                    except Exception:
                        pass
                    if not checked:
                        try:
                            cb.click(timeout=3000)
                            checked = cb.is_checked()
                        except Exception:
                            pass
                    if not checked:
                        try:
                            cb.evaluate("el => el.click()")
                            checked = True
                        except Exception:
                            pass
                    self._log("Terms accepted")
                    time.sleep(1)
                    for _ in range(3):
                        if self._click_submit(page):
                            break
                        time.sleep(2)
                    return True
            except Exception:
                pass
            time.sleep(2)
        return False

    def _auto_complete_signup(self, page) -> bool:
        """Try to fully automate the post-OTP steps (Continue -> name -> birthdate/age).
        Returns True if everything was handled, False if manual help is needed."""
        import random
        first_names = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley",
                       "Avery", "Sam", "Quinn", "Drew", "Lee", "Kai"]
        last_names = ["Chen", "Smith", "Johnson", "Lee", "Kim", "Brown",
                      "Davis", "Wilson", "Moore", "Taylor", "Wang", "Park"]
        try:
            # click continue after OTP — keep trying for up to 20s,
            # pressing Enter as fallback while the OTP page is still visible
            clicked = False
            click_deadline = time.time() + 20
            while time.time() < click_deadline:
                if self._click_submit(page):
                    clicked = True
                    break
                try:
                    otp_visible = page.locator(
                        "input[autocomplete='one-time-code'], input[inputmode='numeric']"
                    ).first.is_visible()
                except Exception:
                    otp_visible = False
                if otp_visible:
                    try:
                        page.keyboard.press("Enter")
                        clicked = True
                        break
                    except Exception:
                        pass
                time.sleep(2)
            if not clicked:
                self._log("Could not click Continue after OTP, will wait for page transition")

            handled = False

            # step 1: name/birthdate/age profile step (may be skipped by the flow)
            deadline = time.time() + 25
            fields = None
            while time.time() < deadline:
                fields = self._detect_profile_fields(page)
                if fields is not None:
                    break
                time.sleep(2)
            if fields is None:
                self._log("No profile fields found after Continue")
            else:
                self._fill_birthdate(page, fields.get("birthdate"))
                age = fields.get("age")
                if age is not None:
                    try:
                        age.fill(str(random.randint(22, 30)), timeout=5000)
                    except Exception:
                        pass
                single = fields.get("single")
                name_fields = fields.get("name_fields") or []
                if single is not None:
                    try:
                        single.fill(random.choice(first_names) + " " + random.choice(last_names), timeout=5000)
                    except Exception:
                        pass
                elif len(name_fields) >= 1:
                    try:
                        name_fields[0].fill(random.choice(first_names), timeout=5000)
                    except Exception:
                        pass
                if len(name_fields) >= 2:
                    try:
                        name_fields[1].fill(random.choice(last_names), timeout=5000)
                    except Exception:
                        pass
                time.sleep(1)
                self._click_submit(page)
                self._log("Auto-filled name/birthdate and submitted")
                handled = True

            # step 2: terms of service checkbox (may be the only step, or after profile)
            if self._accept_terms(page):
                handled = True
            else:
                self._log("No terms checkbox found, continuing")

            return handled
        except Exception as e:
            self._log(f"Auto-complete error: {e}")
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
            import tempfile as _tempfile
            profile = _tempfile.mkdtemp(prefix="opencode_chrome_")
            self._log("No Chrome profile, using fresh temp profile")

        # Use the real Chrome channel when a system Chrome is present,
        # otherwise fall back to the bundled Playwright Chromium (e.g. on servers).
        channel = None
        try:
            from playwright.sync_api import sync_playwright as _sp
            with _sp() as _p:
                _p.chromium.launch(channel="chrome", headless=True).close()
            channel = "chrome"
        except Exception:
            channel = None

        proxy_cfg = {"server": self.proxy} if self.proxy else None
        result: Dict[str, Any] = {}

        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                profile,
                channel=channel,
                headless=self.headless,
                proxy=proxy_cfg,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
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
                self._log("OTP filled")
                self._progress("Auto-completing signup...")
                if not self._auto_complete_signup(page):
                    self._log("Auto-complete unavailable - PLEASE click Continue/complete signup manually in the browser window")

                # Wait for signup to complete, polling session token
                self._progress("Waiting for signup to complete...")
                start = time.time()
                session_data = {}
                last_welcome_click = 0.0
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
                    # auto-click the welcome Continue CTA on chatgpt.com
                    if not session_data and time.time() - last_welcome_click > 5:
                        try:
                            if "chatgpt.com" in page.url and self._click_welcome_continue(page):
                                last_welcome_click = time.time()
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
