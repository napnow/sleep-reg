"""
Outlook/Office365 IMAP email provider.
Uses IMAP with app password to receive verification codes.
"""

import imaplib
import email
import re
import time
import logging
import random
import string
from email.header import decode_header
from typing import Optional, Dict, Any, List

from .common import EmailProvider, EmailProviderError, EmailTimeoutError, wait_with_timeout

logger = logging.getLogger(__name__)

IMAP_HOST = "outlook.office365.com"
IMAP_PORT = 993


class OutlookProvider(EmailProvider):
    """Outlook IMAP provider using app password.

    Supports generating random addresses via + alias:
    base+random@outlook.com — all land in the same inbox.
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.base_email = str((config or {}).get("email") or "").strip()
        self.password = str((config or {}).get("app_password") or (config or {}).get("password") or "").strip()
        self.use_alias = bool((config or {}).get("use_alias", True))
        self.alias_count = 0
        self._conn = None

    @property
    def email(self) -> str:
        return self._current_email or self.base_email

    def _connect(self) -> imaplib.IMAP4_SSL:
        if self._conn is not None:
            return self._conn
        if not self.email or not self.password:
            raise EmailProviderError("Outlook email/app_password not configured")
        try:
            conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            conn.login(self.email, self.password)
            self._conn = conn
            return conn
        except Exception as e:
            raise EmailProviderError(f"Outlook IMAP login failed: {e}")

    def create_email(self) -> str:
        """Generate a random address via + alias, or return base address."""
        if not self.base_email:
            raise EmailProviderError("Outlook email not configured")
        if self.use_alias:
            self.alias_count += 1
            local, _, domain = self.base_email.partition("@")
            if not domain:
                raise EmailProviderError(f"Invalid Outlook email: {self.base_email}")
            tag = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            addr = f"{local}+{tag}@{domain}"
            self._current_email = addr
            return addr
        self._current_email = self.base_email
        return self.base_email

    def _search_openai_messages(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            conn.select("INBOX")
            status, data = conn.search(None, "ALL")
            if status != "OK":
                return []
            ids = data[0].split()
            messages = []
            for mid in reversed(ids[-20:]):
                try:
                    status, msg_data = conn.fetch(mid, "(RFC822)")
                    if status != "OK":
                        continue
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)
                    from_addr = ""
                    for part, enc in decode_header(msg.get("From", "")):
                        if isinstance(part, bytes):
                            from_addr += part.decode(enc or "utf-8", errors="replace")
                        else:
                            from_addr += part
                    subject = ""
                    for part, enc in decode_header(msg.get("Subject", "")):
                        if isinstance(part, bytes):
                            subject += part.decode(enc or "utf-8", errors="replace")
                        else:
                            subject += part
                    messages.append({
                        "id": mid.decode() if isinstance(mid, bytes) else str(mid),
                        "from": from_addr,
                        "subject": subject,
                        "raw": raw,
                    })
                except Exception:
                    continue
            return messages
        except Exception as e:
            logger.error(f"Outlook search error: {e}")
            return []

    def _get_message_content(self, msg: Dict[str, Any]) -> str:
        raw = msg.get("raw", b"")
        if not raw:
            return ""
        try:
            parsed = email.message_from_bytes(raw)
        except Exception:
            return ""
        parts = []
        try:
            body = parsed.get_body(preferencelist=("plain", "html"))
            if body:
                content = body.get_content()
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="replace")
                parts.append(str(content))
        except Exception:
            pass
        for part in parsed.walk():
            if part.get_content_type() == "text/plain" and part not in parts:
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        parts.append(payload.decode("utf-8", errors="replace"))
                except Exception:
                    continue
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
                messages = self._search_openai_messages()
                for msg in messages:
                    frm = msg.get("from", "").lower()
                    if "openai" in frm or "chatgpt" in frm or "openai" in msg.get("subject", "").lower():
                        content = self._get_message_content(msg)
                        code = self._extract_code(content)
                        if code:
                            return code
                return None
            except Exception as e:
                logger.debug(f"Outlook check error: {e}")
                return None

        try:
            return wait_with_timeout(check, timeout=timeout, interval=3.0, description="waiting for verification code")
        except EmailTimeoutError:
            logger.warning(f"Timeout waiting for code for {email}")
            return None

    def get_inbox(self, email: str) -> list:
        try:
            return self._search_openai_messages()
        except Exception as e:
            logger.error(f"Error getting inbox: {e}")
            return []

    def cleanup(self):
        try:
            if self._conn:
                self._conn.logout()
        except Exception:
            pass
        self._conn = None
