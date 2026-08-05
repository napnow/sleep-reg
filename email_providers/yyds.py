"""
YYDS email provider implementation.
Based on grokRegister-cpa yyds.py

YYDS typically provides fixed or auto-generated email domains.
"""

import requests
import random
import string
import time
import logging
from typing import Optional, Dict, Any, List
from .common import EmailProvider, EmailProviderError, EmailTimeoutError

logger = logging.getLogger(__name__)


class YYDSProvider(EmailProvider):
    """
    YYDS email provider.
    Supports fixed domains or auto domain selection.
    """

    # Common YYDS domains (update as needed)
    DEFAULT_DOMAINS = [
        "yyds.com",
        "mail.yyds.com",
        "temp.yyds.com",
    ]

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.fixed_domain = config.get("fixed_domain", "") if config else ""
        self.auto_domain = config.get("auto_domain", True) if config else True
        self.api_base = config.get("api_base", "https://api.yyds.com") if config else "https://api.yyds.com"
        self.session = requests.Session()
        self._inbox_cache = {}

    def _get_domains(self) -> List[str]:
        """Get available domains."""
        if self.fixed_domain:
            return [self.fixed_domain]

        if not self.auto_domain:
            return self.DEFAULT_DOMAINS

        try:
            # Try to fetch domains from API
            resp = self.session.get(f"{self.api_base}/domains", timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                domains = data.get("domains", [])
                if domains:
                    return domains
        except Exception as e:
            logger.debug(f"Failed to fetch domains from API: {e}")

        # Fallback to defaults
        return self.DEFAULT_DOMAINS

    def create_email(self) -> str:
        """Create a new email address."""
        try:
            domains = self._get_domains()
            if not domains:
                raise EmailProviderError("No domains available")

            domain = random.choice(domains)

            # Generate username
            username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

            # Some YYDS providers use specific formats
            formats = [
                f"{username}@{domain}",
                f"{username}_{int(time.time())}@{domain}",
                f"user_{username}@{domain}",
            ]
            email = random.choice(formats)

            self._current_email = email
            self._inbox_cache[email] = []

            logger.info(f"Created YYDS email: {email}")
            return email

        except Exception as e:
            logger.error(f"Error creating YYDS email: {e}")
            # Fallback to simple generation
            domain = self.fixed_domain or random.choice(self.DEFAULT_DOMAINS)
            email = f"{''.join(random.choices(string.ascii_lowercase, k=10))}@{domain}"
            self._current_email = email
            return email

    def wait_for_code(self, email: str, timeout: int = 120) -> Optional[str]:
        """Wait for verification code."""
        if email != self._current_email:
            raise EmailProviderError(f"Email mismatch: expected {self._current_email}, got {email}")

        def check_messages():
            messages = self.get_inbox(email)
            for msg in messages:
                subject = msg.get("subject", "").lower()
                body = msg.get("body", "").lower()
                content = subject + " " + body

                # Look for OpenAI/ChatGPT verification
                if "openai" in content or "chatgpt" in content or "verify" in content:
                    code = self._extract_code(content)
                    if code:
                        return code
            return None

        try:
            from .common import wait_with_timeout
            return wait_with_timeout(
                check_messages,
                timeout=timeout,
                interval=5.0,
                description="waiting for YYDS verification code"
            )
        except EmailTimeoutError:
            logger.warning(f"Timeout waiting for code for {email}")
            return None

    def _extract_code(self, content: str) -> Optional[str]:
        """Extract verification code from content."""
        import re

        # Common patterns
        patterns = [
            r'\b(\d{6})\b',
            r'code[:\s]*(\d{6})',
            r'验证码[:\s]*(\d{6})',
            r'(\d{6})\s*(?:is|code)',
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
        if email != self._current_email:
            return []

        try:
            # Try API first
            resp = self.session.get(
                f"{self.api_base}/inbox/{email}",
                timeout=30
            )

            if resp.status_code == 200:
                data = resp.json()
                messages = data.get("messages", [])
                self._inbox_cache[email] = messages
                return messages

        except Exception as e:
            logger.debug(f"API inbox fetch failed: {e}")

        # Return cached messages if API fails
        return self._inbox_cache.get(email, [])

    def _simulate_inbox(self, email: str) -> List[Dict[str, Any]]:
        """
        Simulate inbox for testing when no real API is available.
        In production, this should be replaced with actual API calls.
        """
        # This is a placeholder - real implementation needs actual YYDS API
        logger.warning("Using simulated YYDS inbox - implement real API integration")
        return []

    def cleanup(self):
        """Cleanup resources."""
        self._current_email = None
        self._inbox_cache.clear()
