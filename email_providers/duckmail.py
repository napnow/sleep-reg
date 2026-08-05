"""
DuckMail / Mail.tm email provider implementation.
Based on grokRegister-cpa duckmail.py and common mail.tm API patterns.
"""

import requests
import random
import string
import time
import logging
from typing import Optional, Dict, Any
from .common import EmailProvider, EmailProviderError, EmailTimeoutError

logger = logging.getLogger(__name__)


class DuckMailProvider(EmailProvider):
    """
    Mail.tm based email provider.
    Uses the mail.tm API for temporary email creation and retrieval.
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.api_base = config.get('api_base', 'https://api.mail.tm') if config else 'https://api.mail.tm'
        self.session = requests.Session()
        self._current_password = None

    def _generate_password(self) -> str:
        """Generate a secure random password."""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=16))

    def _get_domains(self) -> list:
        """Get available email domains."""
        try:
            resp = self.session.get(f"{self.api_base}/domains", timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return [d['domain'] for d in data.get('hydra:member', [])]
        except Exception as e:
            logger.error(f"Failed to get domains: {e}")
            # Fallback domains
            return ['mail.tm', 'mailto.plus', 'fexpost.com']

    def create_email(self) -> str:
        """Create a new temporary email address."""
        try:
            # Get available domains
            domains = self._get_domains()
            if not domains:
                raise EmailProviderError("No domains available")

            domain = random.choice(domains)

            # Generate email and password
            username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            email = f"{username}@{domain}"
            password = self._generate_password()

            # Create account
            payload = {
                "address": email,
                "password": password
            }

            resp = self.session.post(f"{self.api_base}/accounts", json=payload, timeout=30)
            resp.raise_for_status()

            # Get auth token
            token_resp = self.session.post(
                f"{self.api_base}/token",
                json={"address": email, "password": password},
                timeout=30
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()

            self._current_email = email
            self._current_token = token_data.get('token')
            self._current_password = password

            logger.info(f"Created email: {email}")
            return email

        except requests.RequestException as e:
            logger.error(f"Request error creating email: {e}")
            raise EmailProviderError(f"Failed to create email: {e}")
        except Exception as e:
            logger.error(f"Error creating email: {e}")
            raise EmailProviderError(f"Failed to create email: {e}")

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authorization headers for API requests."""
        if not self._current_token:
            raise EmailProviderError("No authentication token available")
        return {"Authorization": f"Bearer {self._current_token}"}

    def wait_for_code(self, email: str, timeout: int = 120) -> Optional[str]:
        """Wait for and extract 6-digit verification code from email."""
        if email != self._current_email:
            raise EmailProviderError(f"Email mismatch: expected {self._current_email}, got {email}")

        def check_for_code():
            try:
                headers = self._get_auth_headers()
                resp = self.session.get(
                    f"{self.api_base}/messages",
                    headers=headers,
                    timeout=30
                )
                resp.raise_for_status()
                messages = resp.json()

                for msg in messages.get('hydra:member', []):
                    # Check if this is from OpenAI/ChatGPT
                    from_addr = msg.get('from', {}).get('address', '').lower()
                    subject = msg.get('subject', '').lower()

                    if 'openai' in from_addr or 'chatgpt' in from_addr or 'openai' in subject:
                        # Get full message content
                        msg_id = msg.get('id')
                        if msg_id:
                            content = self._get_message_content(msg_id, headers)
                            code = self._extract_code(content)
                            if code:
                                return code
                return None
            except Exception as e:
                logger.debug(f"Error checking messages: {e}")
                return None

        try:
            from .common import wait_with_timeout
            return wait_with_timeout(
                check_for_code,
                timeout=timeout,
                interval=3.0,
                description="waiting for verification code"
            )
        except EmailTimeoutError:
            logger.warning(f"Timeout waiting for code for {email}")
            return None

    def _get_message_content(self, msg_id: str, headers: Dict[str, str]) -> str:
        """Get full message content."""
        try:
            resp = self.session.get(
                f"{self.api_base}/messages/{msg_id}",
                headers=headers,
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()

            # Combine subject and text content
            content = data.get('subject', '') + '\n'
            content += data.get('text', '') + '\n'
            content += data.get('intro', '') + '\n'

            # Also check HTML if available
            html = data.get('html', [])
            if isinstance(html, list):
                content += ' '.join(html)

            return content
        except Exception as e:
            logger.debug(f"Error getting message content: {e}")
            return ""

    def _extract_code(self, content: str) -> Optional[str]:
        """Extract 6-digit verification code from email content."""
        import re

        # Common patterns for OpenAI verification codes
        patterns = [
            r'\b(\d{6})\b',  # Any 6-digit number
            r'code[:\s]*(\d{6})',  # "code: 123456"
            r'verification[:\s]*(\d{6})',  # "verification: 123456"
            r'(\d{6})\s*(?:is|code|验证码)',  # "123456 is/code"
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                # Verify it's likely a verification code (not a date, etc.)
                if isinstance(match, tuple):
                    match = match[0]
                if len(match) == 6 and match.isdigit():
                    # Skip obvious non-codes like dates
                    if not match.startswith('20') and not match.startswith('19'):
                        return match

        return None

    def get_inbox(self, email: str) -> list:
        """Get inbox messages for debugging."""
        if email != self._current_email or not self._current_token:
            return []

        try:
            headers = self._get_auth_headers()
            resp = self.session.get(
                f"{self.api_base}/messages",
                headers=headers,
                timeout=30
            )
            resp.raise_for_status()
            return resp.json().get('hydra:member', [])
        except Exception as e:
            logger.error(f"Error getting inbox: {e}")
            return []

    def cleanup(self):
        """Cleanup the email account."""
        # mail.tm accounts are temporary and auto-expire
        # No explicit cleanup needed
        self._current_email = None
        self._current_token = None
        self._current_password = None
