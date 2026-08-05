"""
Cloudflare Workers email provider.
Based on grokRegister-cpa cloudflare.py

Supports custom Cloudflare Worker endpoints for email handling.
Can work in anonymous or admin mode.
"""

import requests
import random
import string
import time
import logging
from typing import Optional, Dict, Any, List
from .common import EmailProvider, EmailProviderError, EmailTimeoutError

logger = logging.getLogger(__name__)


class CloudflareProvider(EmailProvider):
    """
    Cloudflare Workers based email provider.
    Uses custom worker endpoints for email operations.
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.worker_url = config.get("worker_url", "") if config else ""
        self.admin_token = config.get("admin_token", "") if config else ""
        self.domain = config.get("domain", "") if config else ""
        self.custom_path = config.get("custom_path", "/email") if config else "/email"

        if not self.worker_url:
            raise EmailProviderError("Cloudflare worker_url is required")

        self.session = requests.Session()
        self._email_cache = {}

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with optional auth."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "chatgpt-register/1.0"
        }
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        return headers

    def create_email(self) -> str:
        """Create or allocate an email address."""
        try:
            if self.admin_token:
                # Admin mode: request new email allocation
                url = f"{self.worker_url}{self.custom_path}/allocate"
                resp = self.session.post(
                    url,
                    headers=self._get_headers(),
                    json={"action": "create"},
                    timeout=30
                )
            else:
                # Anonymous mode: generate email locally
                # Worker will accept any email on the domain
                if not self.domain:
                    raise EmailProviderError("Domain required for anonymous mode")

                username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
                email = f"{username}@{self.domain}"

                # Optionally notify worker of email usage
                url = f"{self.worker_url}{self.custom_path}/watch"
                try:
                    self.session.post(
                        url,
                        headers=self._get_headers(),
                        json={"email": email, "action": "watch"},
                        timeout=10
                    )
                except:
                    pass  # Non-critical

                self._current_email = email
                return email

            if resp.status_code == 200:
                data = resp.json()
                email = data.get("email")
                if email:
                    self._current_email = email
                    logger.info(f"Allocated Cloudflare email: {email}")
                    return email

            raise EmailProviderError(f"Failed to allocate email: {resp.status_code}")

        except requests.RequestException as e:
            logger.error(f"Cloudflare email creation error: {e}")
            raise EmailProviderError(f"Email creation failed: {e}")

    def wait_for_code(self, email: str, timeout: int = 120) -> Optional[str]:
        """Wait for verification code via worker."""
        if email != self._current_email:
            raise EmailProviderError(f"Email mismatch")

        def poll_inbox():
            try:
                url = f"{self.worker_url}{self.custom_path}/inbox"
                params = {"email": email}

                resp = self.session.get(
                    url,
                    headers=self._get_headers(),
                    params=params,
                    timeout=30
                )

                if resp.status_code == 200:
                    data = resp.json()
                    messages = data.get("messages", [])

                    for msg in messages:
                        content = str(msg.get("subject", "")) + " " + str(msg.get("body", ""))
                        code = self._extract_code(content)
                        if code:
                            return code

                return None

            except Exception as e:
                logger.debug(f"Error polling Cloudflare inbox: {e}")
                return None

        try:
            from .common import wait_with_timeout
            return wait_with_timeout(
                poll_inbox,
                timeout=timeout,
                interval=3.0,
                description="waiting for Cloudflare email code"
            )
        except EmailTimeoutError:
            return None

    def _extract_code(self, content: str) -> Optional[str]:
        """Extract 6-digit code from content."""
        import re

        patterns = [
            r'\b(\d{6})\b',
            r'code[:\s]*(\d{6})',
            r'验证码[:\s]*(\d{6})',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                if len(match) == 6 and match.isdigit():
                    return match

        return None

    def get_inbox(self, email: str) -> List[Dict[str, Any]]:
        """Get inbox messages."""
        try:
            url = f"{self.worker_url}{self.custom_path}/inbox"
            params = {"email": email}

            resp = self.session.get(
                url,
                headers=self._get_headers(),
                params=params,
                timeout=30
            )

            if resp.status_code == 200:
                data = resp.json()
                return data.get("messages", [])

        except Exception as e:
            logger.error(f"Error getting Cloudflare inbox: {e}")

        return []

    def cleanup(self):
        """Cleanup email allocation if in admin mode."""
        if self.admin_token and self._current_email:
            try:
                url = f"{self.worker_url}{self.custom_path}/release"
                self.session.post(
                    url,
                    headers=self._get_headers(),
                    json={"email": self._current_email},
                    timeout=10
                )
            except:
                pass

        self._current_email = None
