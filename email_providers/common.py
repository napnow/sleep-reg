"""
Email providers common interface for ChatGPT registration tool.
Based on grokRegister-cpa email_providers/common.py
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import time
import logging

logger = logging.getLogger(__name__)


class EmailProvider(ABC):
    """Abstract base class for email providers."""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self._current_email = None
        self._current_token = None

    @abstractmethod
    def create_email(self) -> str:
        """Create and return a new email address."""
        pass

    @abstractmethod
    def wait_for_code(self, email: str, timeout: int = 120) -> Optional[str]:
        """Wait for and return a 6-digit verification code."""
        pass

    @abstractmethod
    def get_inbox(self, email: str) -> list:
        """Get inbox messages for debugging."""
        pass

    def cleanup(self):
        """Cleanup resources if needed."""
        pass

    @property
    def current_email(self) -> Optional[str]:
        return self._current_email


class EmailProviderError(Exception):
    """Base exception for email provider errors."""
    pass


class EmailTimeoutError(EmailProviderError):
    """Raised when waiting for email code times out."""
    pass


def wait_with_timeout(condition_fn, timeout: int, interval: float = 2.0, description: str = "waiting"):
    """Wait for a condition with timeout."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            result = condition_fn()
            if result:
                return result
        except Exception as e:
            logger.debug(f"Error during {description}: {e}")
        time.sleep(interval)
    raise EmailTimeoutError(f"Timeout {description} after {timeout}s")
