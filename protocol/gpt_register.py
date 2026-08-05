"""
GPT/ChatGPT registration via protocol mode.
Ported from gptGrok2api's ChatGPTWebRegistrar flow.

Pure curl_cffi implementation - no browser needed.
Flow:
1. NextAuth handshake (chatgpt.com /api/auth/csrf + signin)
2. GET authorize_url (establish auth context)
3. POST /api/accounts/authorize/continue (with full sentinel token)
4. GET /api/accounts/email-otp/send
5. Wait for OTP from mailbox
6. POST /api/accounts/email-otp/validate
7. POST /api/accounts/user/profile (name + birthdate)
8. Follow callback -> extract access_token from session
"""

import json
import random
import re
import secrets
import string
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from urllib.parse import urlparse, parse_qs, urljoin

from curl_cffi import requests as curl_requests

from .sentinel import build_sentinel_with_so_token
from .pkce import generate_pkce

AUTH_BASE = "https://auth.openai.com"
CHATGPT_BASE = "https://chatgpt.com"
CLIENT_ID = "app_X8zY6vW2pQ9tR3dE7nK1jL5gH"
CALLBACK_PATH = "/api/auth/callback/openai"
SESSION_PATH = "/api/auth/session"

BROWSER_PROFILES = (
    {
        "impersonate": "chrome142",
        "major": "142",
        "full_version": "142.0.0.0",
        "platform_version": "10.0.0",
        "accept_language": "en-US,en;q=0.9",
    },
)


def _chrome_user_agent(full_version: str) -> str:
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{full_version} Safari/537.36"
    )


def _chrome_sec_ch_ua(major: str) -> str:
    return f'"Chromium";v="{major}", "Google Chrome";v="{major}", "Not_A Brand";v="99"'


def _complete_fingerprint(profile: dict) -> dict:
    major = str(profile.get("major") or "142").strip()
    full_version = str(profile.get("full_version") or f"{major}.0.0.0").strip()
    return {
        **profile,
        "major": major,
        "full_version": full_version,
        "user_agent": _chrome_user_agent(full_version),
        "sec_ch_ua": _chrome_sec_ch_ua(major),
        "sec_ch_ua_full_version_list": (
            f'"Chromium";v="{full_version}", "Google Chrome";v="{full_version}", '
            '"Not_A Brand";v="99.0.0.0"'
        ),
    }


def _make_fingerprint() -> dict:
    return _complete_fingerprint(BROWSER_PROFILES[0])


def _is_cloudflare_challenge(resp) -> bool:
    if resp is None:
        return False
    try:
        status = int(getattr(resp, "status_code", 0) or 0)
    except (TypeError, ValueError):
        status = 0
    if status not in (403, 503):
        return False
    text = str(getattr(resp, "text", "") or "").lower()
    return (
        "<title>just a moment" in text
        or "<title>attention required! | cloudflare" in text
        or "cf-chl-" in text
        or "__cf_chl_" in text
    )


def _random_name() -> tuple:
    first = random.choice(["James", "Robert", "John", "Michael", "David", "Mary", "Emma", "Olivia"])
    last = random.choice(["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"])
    return first, last


def _random_birthdate() -> str:
    return f"{random.randint(1996, 2006):04d}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"


def _trace_headers() -> dict:
    return {
        "traceparent": f"00-{uuid.uuid4().hex}-{format(random.getrandbits(64), '016x')}-01",
        "tracestate": "dd=s:1;o:rum",
        "x-datadog-origin": "rum",
        "x-datadog-parent-id": str(random.getrandbits(64)),
        "x-datadog-sampling-priority": "1",
        "x-datadog-trace-id": str(random.getrandbits(64)),
    }


class GPTRegistrar:
    """Pure-protocol ChatGPT registration."""

    def __init__(
        self,
        email_provider: Any,
        proxy: str = "",
        on_log: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[str], None]] = None,
    ):
        self.email_provider = email_provider
        self.proxy = proxy or ""
        self.on_log = on_log or (lambda msg: None)
        self.on_progress = on_progress or (lambda msg: None)
        self.fingerprint = _make_fingerprint()
        self.session = self._create_session()
        self.device_id = ""
        self._otp_sentinel_token = ""
        self._otp_sentinel_so_token = ""

    def _log(self, msg: str):
        self.on_log(msg)

    def _progress(self, msg: str):
        self.on_progress(msg)

    def _create_session(self) -> curl_requests.Session:
        s = curl_requests.Session(impersonate=self.fingerprint["impersonate"])
        if self.proxy:
            s.proxies.update({"http": self.proxy, "https": self.proxy})
        s.headers.update({"user-agent": self.fingerprint["user_agent"]})
        return s

    def _set_sentinel_cookie(self, oai_sc: str):
        for domain in (".auth.openai.com", "auth.openai.com"):
            try:
                self.session.cookies.set("oai-sc", oai_sc, domain=domain)
            except Exception:
                pass

    def _set_device_id(self, device_id: str):
        self.device_id = device_id
        for domain in (".auth.openai.com", "auth.openai.com"):
            try:
                self.session.cookies.set("oai-did", device_id, domain=domain)
            except Exception:
                pass

    def _chatgpt_headers(self, target_path: str, referer: str = "", content_type: str = "application/json") -> dict:
        fp = self.fingerprint
        h = {
            "accept": "application/json",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": fp["accept_language"],
            "cache-control": "no-cache",
            "connection": "keep-alive",
            "content-type": content_type,
            "dnt": "1",
            "origin": CHATGPT_BASE,
            "priority": "u=1, i",
            "sec-gpc": "1",
            "sec-ch-ua": fp["sec_ch_ua"],
            "sec-ch-ua-arch": '"x86_64"',
            "sec-ch-ua-bitness": '"64"',
            "sec-ch-ua-full-version-list": fp["sec_ch_ua_full_version_list"],
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-model": '""',
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-platform-version": f'"{fp["platform_version"]}"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": fp["user_agent"],
            "referer": referer or f"{CHATGPT_BASE}/",
            "x-openai-target-path": target_path,
            "x-openai-target-route": target_path,
        }
        return h

    def _auth_headers(self, referer: str) -> dict:
        fp = self.fingerprint
        h = {
            "accept": "application/json",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": fp["accept_language"],
            "cache-control": "no-cache",
            "connection": "keep-alive",
            "content-type": "application/json",
            "dnt": "1",
            "origin": AUTH_BASE,
            "priority": "u=1, i",
            "sec-gpc": "1",
            "sec-ch-ua": fp["sec_ch_ua"],
            "sec-ch-ua-arch": '"x86_64"',
            "sec-ch-ua-bitness": '"64"',
            "sec-ch-ua-full-version-list": fp["sec_ch_ua_full_version_list"],
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-model": '""',
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-platform-version": f'"{fp["platform_version"]}"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": fp["user_agent"],
            "referer": referer,
        }
        if self.device_id:
            h["oai-device-id"] = self.device_id
        h.update(_trace_headers())
        return h

    def _auth_nav_headers(self, referer: str = "") -> dict:
        fp = self.fingerprint
        return {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": fp["accept_language"],
            "cache-control": "max-age=0",
            "connection": "keep-alive",
            "dnt": "1",
            "sec-gpc": "1",
            "sec-ch-ua": fp["sec_ch_ua"],
            "sec-ch-ua-arch": '"x86_64"',
            "sec-ch-ua-bitness": '"64"',
            "sec-ch-ua-full-version-list": fp["sec_ch_ua_full_version_list"],
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-model": '""',
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-platform-version": f'"{fp["platform_version"]}"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": fp["user_agent"],
            "referer": referer or f"{CHATGPT_BASE}/",
        }

    def _request(self, method: str, url: str, headers: dict, **kwargs):
        """Request with CF challenge and TLS retry."""
        last = None
        for attempt in range(4):
            try:
                resp = self.session.request(method, url, headers=headers, timeout=30, **kwargs)
            except Exception as e:
                last = e
                self._log(f"Request error ({attempt + 1}/4): {str(e)[:80]}")
                time.sleep(2)
                continue
            if not _is_cloudflare_challenge(resp):
                return resp
            self._log(f"Cloudflare challenge ({attempt + 1}/4), retrying...")
            time.sleep(2)
        if last is not None:
            raise last
        return resp

    def _get_chatgpt_csrf(self) -> str:
        path = "/api/auth/csrf"
        resp = self._request("get", f"{CHATGPT_BASE}{path}", headers=self._chatgpt_headers(path, f"{CHATGPT_BASE}/auth/login"))
        data = resp.json() if resp.text else {}
        token = str(data.get("csrfToken") or "").strip()
        if resp.status_code != 200 or not token:
            raise RuntimeError(f"chatgpt_csrf_http_{resp.status_code}")
        return token

    def _begin_chatgpt_signin(self, csrf_token: str) -> str:
        path = "/api/auth/signin/openai?prompt=login&screen_hint=login_or_signup"
        resp = self._request(
            "post",
            f"{CHATGPT_BASE}{path}",
            headers=self._chatgpt_headers(
                "/api/auth/signin/openai", f"{CHATGPT_BASE}/", "application/x-www-form-urlencoded"
            ),
            data={"csrfToken": csrf_token, "callbackUrl": f"{CHATGPT_BASE}/", "json": "true"},
        )
        data = resp.json() if resp.text else {}
        url = str(data.get("url") or "").strip()
        if resp.status_code != 200 or not url:
            raise RuntimeError(f"chatgpt_signin_http_{resp.status_code}")
        return url

    def _chatgpt_web_authorize(self, email: str = ""):
        """Establish OAuth context via direct authorize URL (auto-sends OTP)."""
        self._progress("Initializing ChatGPT web authorization...")
        device_id = str(uuid.uuid4())
        self._set_device_id(device_id)
        self.code_verifier, code_challenge = generate_pkce()
        params = {
            "issuer": AUTH_BASE,
            "client_id": CLIENT_ID,
            "scope": "openid email profile offline_access model.request model.read organization.read organization.write",
            "response_type": "code",
            "redirect_uri": f"{CHATGPT_BASE}/api/auth/callback/openai",
            "audience": "https://api.openai.com/v1",
            "device_id": device_id,
            "prompt": "login",
            "ext-oai-did": device_id,
            "auth_session_logging_id": str(uuid.uuid4()),
            "screen_hint": "login_or_signup",
            "login_hint": email,
            "ccaps": "login_methods",
            "max_age": "0",
            "response_mode": "query",
            "state": "".join(random.choices(string.ascii_letters + string.digits + "-_", k=32)),
            "nonce": "".join(random.choices(string.ascii_letters + string.digits + "-_", k=32)),
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "auth0Client": "eyJuYW1lIjoiYXV0aDAtc3BhLWpzIiwidmVyc2lvbiI6IjEuMjEuMCJ9",
        }
        url = f"{AUTH_BASE}/api/accounts/authorize"
        resp = self._request("get", url, headers=self._auth_nav_headers(), params=params, allow_redirects=True)
        if resp.status_code != 200:
            raise RuntimeError(f"chatgpt_authorize_http_{resp.status_code}: {resp.text[:300]}")
        self._log(f"OAuth context established (device_id={device_id[:8]}...)")


    def _chatgpt_web_authorize_nextauth(self):
        """Perform NextAuth CSRF/signin handshakes, land on auth.openai.com."""
        self._progress("Initializing ChatGPT web authorization (NextAuth)...")
        self._begin_chatgpt_signin(self._get_chatgpt_csrf())
        authorize_url = self._begin_chatgpt_signin(self._get_chatgpt_csrf())
        parsed = urlparse(authorize_url)
        if parsed.scheme != "https" or parsed.netloc != "auth.openai.com" or "/api/accounts/authorize" not in parsed.path:
            raise RuntimeError(f"ChatGPT did not return valid authorize URL: {authorize_url[:200]}")
        device_id = str((parse_qs(parsed.query).get("device_id") or [""])[0]).strip()
        if not device_id:
            raise RuntimeError("authorize URL missing device_id")
        self._set_device_id(device_id)
        self._log(f"OAuth context established (device_id={device_id[:8]}...)")

        resp = self._request(
            "get", authorize_url, headers=self._auth_nav_headers(f"{CHATGPT_BASE}/"), allow_redirects=True
        )
        if resp.status_code != 200:
            raise RuntimeError(f"chatgpt_authorize_http_{resp.status_code}")
        if urlparse(str(resp.url or "")).netloc != "auth.openai.com":
            raise RuntimeError(f"authorize redirect landed on unexpected host: {resp.url[:120]}")

    def _continue_username(self, email: str) -> dict:
        self._progress(f"Submitting email: {email}")
        url = f"{AUTH_BASE}/api/accounts/authorize/continue"
        body = {"username": {"kind": "email", "value": email}, "screen_hint": "login_or_signup"}
        sentinel_token, so_token, oai_sc = build_sentinel_with_so_token(
            self.session, self.device_id, "authorize_continue",
            user_agent=self.fingerprint["user_agent"],
            sec_ch_ua=self.fingerprint["sec_ch_ua"],
        )
        self._set_sentinel_cookie(oai_sc)
        self._otp_sentinel_token = sentinel_token
        self._otp_sentinel_so_token = so_token
        headers = self._auth_headers(f"{AUTH_BASE}/log-in-or-create-account")
        headers["openai-sentinel-token"] = sentinel_token
        if so_token:
            headers["openai-sentinel-so-token"] = so_token
        resp = self._request("post", url, headers=headers, json=body, allow_redirects=False)
        data = resp.json() if resp.text else {}
        if resp.status_code != 200:
            raise RuntimeError(
                f"authorize_continue_http_{resp.status_code}: {json.dumps(data, ensure_ascii=False)[:400]}"
            )
        page_type = str((data.get("page") or {}).get("type") or "").strip()
        if page_type != "email_otp_verification":
            raise RuntimeError(f"unexpected page_type: {page_type or '?'}")
        return data

    def _send_otp(self) -> None:
        self._progress("Requesting verification code...")
        url = f"{AUTH_BASE}/api/accounts/email-otp/send"
        if not self._otp_sentinel_token:
            raise RuntimeError("missing authorize/continue sentinel context")
        headers = self._auth_headers(f"{AUTH_BASE}/email-verification")
        headers["openai-sentinel-token"] = self._otp_sentinel_token
        if self._otp_sentinel_so_token:
            headers["openai-sentinel-so-token"] = self._otp_sentinel_so_token
        resp = self._request("get", url, headers=headers, allow_redirects=True)
        self._log(f"send_otp status={resp.status_code} body={resp.text[:200]}")
        if resp.status_code not in (200, 302):
            raise RuntimeError(f"send_otp_http_{resp.status_code}: {resp.text[:300]}")
        data = resp.json() if resp.text else {}
        error = data.get("error")
        if isinstance(error, dict):
            msg = str(error.get("message") or error.get("code") or "").strip()
            if msg:
                raise RuntimeError(f"send_otp_rejected: {msg}")
        if data.get("success") is False:
            raise RuntimeError(f"send_otp_rejected: {data.get('message') or 'unknown'}")
        page = data.get("page") if isinstance(data.get("page"), dict) else {}
        mode = str(((page.get("payload") or {}).get("email_verification_mode") or "")).strip()
        self._log(f"send_otp mode={mode}")

    def _validate_otp(self, code: str) -> str:
        self._progress("Verifying code...")
        url = f"{AUTH_BASE}/api/accounts/email-otp/validate"
        # Browser sends openai-sentinel-token + so-token, no oai-device-id
        headers = self._auth_headers(f"{AUTH_BASE}/email-verification")
        headers.pop("oai-device-id", None)
        if self._otp_sentinel_token:
            headers["openai-sentinel-token"] = self._otp_sentinel_token
        if self._otp_sentinel_so_token:
            headers["openai-sentinel-so-token"] = self._otp_sentinel_so_token
        resp = self._request("post", url, headers=headers, json={"code": code})
        if resp.status_code != 200:
            raise RuntimeError(f"validate_otp_http_{resp.status_code}: {resp.text[:400]}")
        data = resp.json() if resp.text else {}
        continue_url = str(data.get("continue_url") or "").strip()
        if not continue_url:
            raise RuntimeError("validate_otp missing continue_url")
        return continue_url

    def _create_profile(self, name: str, birthdate: str) -> str:
        self._progress("Creating account profile...")
        url = f"{AUTH_BASE}/api/accounts/user/profile"
        sentinel_token, so_token, oai_sc = build_sentinel_with_so_token(
            self.session, self.device_id, "oauth_create_account",
            user_agent=self.fingerprint["user_agent"],
            sec_ch_ua=self.fingerprint["sec_ch_ua"],
        )
        self._set_sentinel_cookie(oai_sc)
        headers = self._auth_headers(f"{AUTH_BASE}/about-you")
        headers["openai-sentinel-token"] = sentinel_token
        if so_token:
            headers["openai-sentinel-so-token"] = so_token
        resp = self._request("post", url, headers=headers, json={"name": name, "birthdate": birthdate}, allow_redirects=False)
        data = resp.json() if resp.text else {}
        if resp.status_code not in (200, 302):
            raise RuntimeError(f"user_profile_http_{resp.status_code}: {json.dumps(data, ensure_ascii=False)[:400]}")
        callback_url = (
            str(data.get("continue_url") or "").strip()
            or str(resp.headers.get("Location") or "").strip()
            or str(resp.url or "").strip()
        )
        parsed = urlparse(callback_url)
        if parsed.scheme != "https" or parsed.netloc != "chatgpt.com" or parsed.path != CALLBACK_PATH:
            raise RuntimeError(f"profile did not return callback: {callback_url[:160]}")
        return callback_url

    def _complete_callback(self, callback_url: str) -> dict:
        self._progress("Completing OAuth callback...")
        resp = self._request(
            "get", callback_url, headers=self._auth_nav_headers(f"{AUTH_BASE}/about-you"), allow_redirects=True
        )
        if resp.status_code != 200:
            raise RuntimeError(f"chatgpt_callback_http_{resp.status_code}")

        session_path = SESSION_PATH
        session_data = {}
        for attempt in range(1, 5):
            resp = self._request(
                "get", f"{CHATGPT_BASE}{session_path}",
                headers=self._chatgpt_headers(session_path, f"{CHATGPT_BASE}/"),
            )
            session_data = resp.json() if resp.text else {}
            access_token = str(session_data.get("accessToken") or session_data.get("access_token") or "").strip()
            if resp.status_code == 200 and access_token:
                break
            if resp.status_code != 200:
                raise RuntimeError(f"chatgpt_session_http_{resp.status_code}: {resp.text[:300]}")
            if attempt < 4:
                self._log(f"Session not ready, retry {attempt + 1}/4")
                time.sleep(attempt)
        else:
            raise RuntimeError("callback complete but session missing accessToken")
        return session_data

    def register(self, email: str, password: str = "") -> dict:
        first_name, last_name = _random_name()
        self._chatgpt_web_authorize(email)
        data = self._continue_username(email)
        page_type = str((data.get("page") or {}).get("type") or "").strip()

        if page_type == "create_account_password":
            # Traditional password signup branch
            self._log("Entering password signup branch")
            if not password:
                password = self._generate_password()
            self._register_user(email, password)
            self._send_otp()
            code = self.email_provider.wait_for_code(email, timeout=120)
            if not code:
                raise RuntimeError("Timed out waiting for verification code")
            self._log(f"Got verification code: {self._mask_code(code)}")
            self._validate_otp(code)
            continue_url = self._create_account(f"{first_name} {last_name}", _random_birthdate())
            callback_url = self._capture_callback(continue_url)
            session_data = self._complete_callback(callback_url)
            result = self._session_result(email, session_data)
            result["password"] = password
            return result

        # passwordless_signup branch
        self._progress("Waiting for verification code...")
        code = self.email_provider.wait_for_code(email, timeout=120)
        if not code:
            self._log("No auto code, trying explicit send_otp...")
            try:
                self._send_otp()
            except Exception as e:
                self._log(f"send_otp failed: {e}")
            code = self.email_provider.wait_for_code(email, timeout=120)
        if not code:
            raise RuntimeError("Timed out waiting for verification code")
        self._log(f"Got verification code: {self._mask_code(code)}")
        continue_url = self._validate_otp(code)
        callback_url = self._create_profile(f"{first_name} {last_name}", _random_birthdate())
        session_data = self._complete_callback(callback_url)

        user = session_data.get("user") if isinstance(session_data.get("user"), dict) else {}
        access_token = str(session_data.get("accessToken") or session_data.get("access_token") or "").strip()
        result = {
            "email": str(user.get("email") or email).strip(),
            "password": password,
            "access_token": access_token,
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
        if not access_token:
            raise RuntimeError("registration complete but no access_token")
        return result

    @staticmethod
    def _mask_code(code: str) -> str:
        """Mask verification codes in logs."""
        return code if len(code) <= 2 else f"{code[:2]}***{code[-2:]}"

    def _generate_password(self) -> str:
        chars = string.ascii_letters + string.digits + "!@#$%"
        value = list(
            secrets.choice(string.ascii_uppercase)
            + secrets.choice(string.ascii_lowercase)
            + secrets.choice(string.digits)
            + secrets.choice("!@#$%")
            + "".join(secrets.choice(chars) for _ in range(12))
        )
        random.shuffle(value)
        return "".join(value)

    def _register_user(self, email: str, password: str) -> None:
        self._progress("Registering password...")
        url = f"{AUTH_BASE}/api/accounts/user/register"
        sentinel_token, so_token, oai_sc = build_sentinel_with_so_token(
            self.session, self.device_id, "username_password_create",
            user_agent=self.fingerprint["user_agent"],
            sec_ch_ua=self.fingerprint["sec_ch_ua"],
        )
        self._set_sentinel_cookie(oai_sc)
        headers = self._auth_headers(f"{AUTH_BASE}/create-account/password")
        headers["openai-sentinel-token"] = sentinel_token
        if so_token:
            headers["openai-sentinel-so-token"] = so_token
        resp = self._request("post", url, headers=headers, json={"username": email, "password": password})
        if resp.status_code != 200:
            raise RuntimeError(f"user_register_http_{resp.status_code}: {resp.text[:300]}")
        self._otp_sentinel_token = sentinel_token
        self._otp_sentinel_so_token = so_token

    def _create_account(self, name: str, birthdate: str) -> str:
        self._progress("Creating account profile...")
        url = f"{AUTH_BASE}/api/accounts/create_account"
        sentinel_token, so_token, oai_sc = build_sentinel_with_so_token(
            self.session, self.device_id, "create_account",
            user_agent=self.fingerprint["user_agent"],
            sec_ch_ua=self.fingerprint["sec_ch_ua"],
        )
        self._set_sentinel_cookie(oai_sc)
        headers = self._auth_headers(f"{AUTH_BASE}/about-you")
        headers["openai-sentinel-token"] = sentinel_token
        if so_token:
            headers["openai-sentinel-so-token"] = so_token
        resp = self._request("post", url, headers=headers, json={"name": name, "birthdate": birthdate}, allow_redirects=False)
        data = resp.json() if resp.text else {}
        if resp.status_code not in (200, 302):
            raise RuntimeError(f"create_account_http_{resp.status_code}: {json.dumps(data, ensure_ascii=False)[:300]}")
        continue_url = (
            str(data.get("continue_url") or "").strip()
            or str(resp.headers.get("Location") or "").strip()
            or str(resp.url or "").strip()
        )
        if not continue_url:
            raise RuntimeError("create_account missing continue_url")
        return self._absolute_auth_url(continue_url)

    def _capture_callback(self, continue_url: str) -> str:
        self._progress("Following OAuth callback...")
        current = self._absolute_auth_url(continue_url)
        for _ in range(12):
            parsed = urlparse(current)
            if parsed.scheme == "https" and parsed.netloc == "chatgpt.com" and parsed.path == CALLBACK_PATH:
                return current
            headers = self._auth_nav_headers(f"{AUTH_BASE}/about-you")
            resp = self._request("get", current, headers=headers, allow_redirects=False)
            if resp is None:
                break
            if resp.status_code not in (301, 302, 303, 307, 308):
                break
            location = str(resp.headers.get("Location") or "").strip()
            if not location:
                break
            current = urljoin(current, location)
        raise RuntimeError(f"could not capture callback: {current[:200]}")

    def _session_result(self, email: str, session_data: dict) -> dict:
        user = session_data.get("user") if isinstance(session_data.get("user"), dict) else {}
        access_token = str(session_data.get("accessToken") or session_data.get("access_token") or "").strip()
        result = {
            "email": str(user.get("email") or email).strip(),
            "access_token": access_token,
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
        return result

    def _absolute_auth_url(self, url: str) -> str:
        value = str(url or "").strip()
        if value.startswith("/"):
            return f"{AUTH_BASE}{value}"
        return value
