"""
Upload registered ChatGPT accounts to a remote gpt2api server.

POST /api/accounts with Authorization: Bearer <management-key>
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from curl_cffi import requests as curl_requests

logger = logging.getLogger(__name__)


class CPAUploader:
    """Upload accounts to a remote gpt2api (chatgpt2api) server."""

    def __init__(
        self,
        remote_url: str,
        management_key: str,
        on_log: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[str], None]] = None,
    ):
        self.remote_url = str(remote_url or "").strip().rstrip("/")
        self.management_key = str(management_key or "").strip()
        self.on_log = on_log or (lambda msg: None)
        self.on_progress = on_progress or (lambda msg: None)
        self.session = curl_requests.Session()

    def _log(self, msg: str):
        self.on_log(msg)

    @property
    def enabled(self) -> bool:
        return bool(self.remote_url and self.management_key)

    def upload_account(self, account: Dict[str, Any]) -> bool:
        """Upload a single registered account."""
        if not self.enabled:
            self._log("CPA upload skipped: remote_url/management_key not configured")
            return False
        access_token = str(account.get("access_token") or account.get("accessToken") or "").strip()
        if not access_token:
            self._log("CPA upload skipped: no access_token in account")
            return False

        payload = {"accounts": [self._normalize_account(account)]}
        headers = {
            "Authorization": f"Bearer {self.management_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = self.session.post(
                f"{self.remote_url}/api/accounts",
                json=payload,
                headers=headers,
                timeout=60,
            )
            if resp.status_code in (200, 201):
                data = resp.json() if resp.text else {}
                added = data.get("added", 0)
                self._log(f"CPA upload OK: {account.get('email')} (added={added})")
                return True
            else:
                self._log(f"CPA upload failed: HTTP {resp.status_code} {resp.text[:200]}")
                return False
        except Exception as e:
            self._log(f"CPA upload error: {e}")
            return False

    @staticmethod
    def _normalize_account(account: Dict[str, Any]) -> Dict[str, Any]:
        """Build the account dict expected by gpt2api /api/accounts."""
        result = {
            "email": str(account.get("email") or "").strip(),
            "password": str(account.get("password") or "").strip(),
            "access_token": str(account.get("access_token") or account.get("accessToken") or "").strip(),
            "type": str(account.get("type") or "chatgpt").strip(),
        }
        for key in ("refresh_token", "id_token", "session_token", "user_id", "account_id"):
            value = account.get(key)
            if value:
                result[key] = value
        return result
