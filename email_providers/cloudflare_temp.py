"""
Cloudflare Temp Mail provider (self-hosted worker).
Adapted from grok-auto-register-latest cloudflare_temp_email implementation.
"""

import re
import time
import random
import string
import logging
import secrets
import email as email_mod
from email.header import decode_header
from typing import Optional, Dict, Any, List

from curl_cffi import requests as curl_requests

from .common import EmailProvider, EmailProviderError, EmailTimeoutError, wait_with_timeout

logger = logging.getLogger(__name__)


class CloudflareTempProvider(EmailProvider):
    """Cloudflare temp mail via self-hosted worker API."""

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.api_base = str((config or {}).get("api_base") or "").strip().rstrip("/")
        self.api_key = str((config or {}).get("api_key") or "").strip()
        self.auth_mode = str((config or {}).get("auth_mode") or "bearer").strip().lower()
        self.domain = (config or {}).get("domain") or []
        self.enable_random_subdomain = bool((config or {}).get("enable_random_subdomain", True))
        self.create_path = str((config or {}).get("create_path") or "/api/new_address").strip()
        self.messages_path = str((config or {}).get("messages_path") or "/api/mails").strip()
        self.session = curl_requests.Session()
        self._current_jwt = None

    def _build_headers(self, content_type: bool = False) -> dict:
        headers = {"Content-Type": "application/json"} if content_type else {}
        key = self.api_key
        if not key:
            return headers
        mode = self.auth_mode
        if mode == "x-admin-auth":
            headers["x-admin-auth"] = key
        elif mode == "x-api-key":
            headers["X-API-Key"] = key
        elif mode == "bearer":
            headers["Authorization"] = f"Bearer {key}"
        return headers

    @staticmethod
    def _next_domain(domains) -> str:
        if not domains:
            return ""
        if isinstance(domains, str):
            domains = [d.strip() for d in domains.split(",") if d.strip()]
        if isinstance(domains, (list, tuple)):
            domains = [str(d).strip() for d in domains if str(d).strip()]
        return random.choice(domains) if domains else ""

    def create_email(self) -> str:
        """Create a new Cloudflare temp email address."""
        if not self.api_base:
            raise EmailProviderError("Cloudflare temp mail api_base not configured")
        url = f"{self.api_base}{self.create_path}"
        domain = self._next_domain(self.domain)
        is_admin = self.create_path.rstrip("/").lower() == "/admin/new_address"
        if is_admin:
            payload = {"name": ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10)), "enablePrefix": True}
            if domain:
                payload["domain"] = domain
            if self.enable_random_subdomain:
                payload["enableRandomSubdomain"] = True
            headers = self._build_headers(content_type=True)
        else:
            payload = {}
            if domain:
                payload["domain"] = domain
            if self.enable_random_subdomain:
                payload["enableRandomSubdomain"] = True
            headers = {"Content-Type": "application/json"}
        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code != 200:
                raise EmailProviderError(f"Cloudflare create failed: HTTP {resp.status_code} {resp.text[:200]}")
            data = resp.json()
        except EmailProviderError:
            raise
        except Exception as e:
            raise EmailProviderError(f"Cloudflare create error: {e}")
        address = str(data.get("address") or "").strip()
        jwt = str(data.get("jwt") or "").strip()
        if not address or not jwt:
            raise EmailProviderError(f"Cloudflare create missing address/jwt: {data}")
        self._current_email = address
        self._current_jwt = jwt
        self._current_token = jwt
        logger.info(f"Created Cloudflare temp email: {address}")
        return address

    def _get_messages(self) -> List[Dict[str, Any]]:
        if not self._current_jwt:
            raise EmailProviderError("No JWT available")
        headers = {"Authorization": f"Bearer {self._current_jwt}"}
        resp = self.session.get(f"{self.api_base}{self.messages_path}", headers=headers,
                                params={"limit": 30, "offset": 0}, timeout=30)
        if resp.status_code >= 400:
            logger.debug(f"Cloudflare messages HTTP {resp.status_code}")
            return []
        data = resp.json() if resp.text else {}
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("results", "hydra:member", "data", "messages"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    def _get_message_detail(self, message_id: str) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._current_jwt}"}
        import urllib.parse
        encoded = urllib.parse.quote(str(message_id), safe="")
        for path in (f"/api/mail/{encoded}", f"/api/mails/{encoded}"):
            try:
                resp = self.session.get(f"{self.api_base}{path}", headers=headers, timeout=30)
                if resp.status_code >= 400:
                    continue
                data = resp.json()
                if isinstance(data, dict):
                    nested = data.get("data")
                    return dict(nested) if isinstance(nested, dict) else data
            except Exception:
                continue
        return {}

    def _parse_raw(self, raw: Any) -> Dict[str, Any]:
        """Parse raw email into subject/from/content."""
        if not raw:
            return {}
        if not isinstance(raw, str):
            try:
                raw = str(raw)
            except Exception:
                return {}
        try:
            msg = email_mod.message_from_string(raw)
        except Exception:
            return {}
        result = {}
        try:
            subject = ""
            for part, enc in decode_header(str(msg.get("Subject", ""))):
                if isinstance(part, bytes):
                    subject += part.decode(enc or "utf-8", errors="replace")
                else:
                    subject += str(part)
            result["subject"] = subject
        except Exception:
            pass
        try:
            result["from"] = str(msg.get("From", ""))
        except Exception:
            pass
        try:
            result["to"] = str(msg.get("To", ""))
        except Exception:
            pass
        parts = []
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" or ct == "text/html":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        text = payload.decode("utf-8", errors="replace")
                        if ct == "text/html":
                            text = re.sub(r"<[^>]+>", " ", text)
                        parts.append(text)
                except Exception:
                    continue
        result["content"] = "\n".join(parts)
        return result

    def _flatten_content(self, item: Dict[str, Any], detail: Dict[str, Any]) -> str:
        parsed = self._parse_raw(item.get("raw"))
        subject = str(item.get("subject") or detail.get("subject") or parsed.get("subject") or "")
        parts = [subject]
        if parsed.get("content"):
            parts.append(parsed["content"])
        for src in (item, detail):
            for key in ("text", "raw", "content", "intro", "body", "snippet"):
                value = src.get(key)
                if isinstance(value, str) and value.strip() and key != "raw":
                    parts.append(value)
            html = src.get("html")
            if isinstance(html, str):
                html = [html]
            if isinstance(html, list):
                for h in html:
                    if isinstance(h, str):
                        parts.append(re.sub(r"<[^>]+>", " ", h))
        return "\n".join(parts)

    def _extract_code(self, content: str) -> Optional[str]:
        patterns = [
            r'\b(\d{6})\b',
            r'code[:\s]*(\d{6})',
            r'verification[:\s]*(\d{6})',
            r'(\d{6})\s*(?:is|code|验证码)',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                if len(match) == 6 and match.isdigit():
                    if not match.startswith('20') and not match.startswith('19'):
                        return match
        return None

    def wait_for_code(self, email: str, timeout: int = 120) -> Optional[str]:
        if email != self._current_email:
            raise EmailProviderError(f"Email mismatch: expected {self._current_email}, got {email}")

        def check():
            try:
                messages = self._get_messages()
                for msg in messages:
                    msg_id = msg.get("id") or msg.get("msgid")
                    parsed = self._parse_raw(msg.get("raw"))
                    content = self._flatten_content(msg, {})
                    combined_lower = content.lower()
                    sender = str(msg.get("source") or msg.get("from") or parsed.get("from") or "")
                    if "openai" not in combined_lower and "openai" not in sender.lower():
                        continue
                    code = self._extract_code(content)
                    if code:
                        return code
                    if msg_id:
                        detail = self._get_message_detail(msg_id)
                        content2 = self._flatten_content(msg, detail)
                        code = self._extract_code(content2)
                        if code:
                            return code
                return None
            except Exception as e:
                logger.debug(f"Cloudflare check error: {e}")
                return None

        try:
            return wait_with_timeout(check, timeout=timeout, interval=3.0, description="waiting for verification code")
        except EmailTimeoutError:
            logger.warning(f"Timeout waiting for code for {email}")
            return None

    def get_inbox(self, email: str) -> list:
        try:
            return self._get_messages()
        except Exception as e:
            logger.error(f"Error getting inbox: {e}")
            return []

    def cleanup(self):
        self._current_email = None
        self._current_jwt = None
        self._current_token = None
