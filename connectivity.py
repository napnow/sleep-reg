"""
Connectivity checker for ChatGPT registration tool.
Based on grokRegister-cpa connectivity.py
"""

import requests
import socket
from typing import Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)


def check_connectivity(
    proxy: str = None,
    timeout: int = 10
) -> Dict[str, Any]:
    """
    Check connectivity to required services.

    Returns dict with status of each check.
    """
    results = {
        "overall": True,
        "checks": {}
    }

    # Check endpoints
    endpoints = [
        ("auth.openai.com", "https://auth.openai.com", True),
        ("api.mail.tm", "https://api.mail.tm", False),
        ("chatgpt.com", "https://chatgpt.com", False),
    ]

    session = requests.Session()
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}

    for name, url, critical in endpoints:
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
            status = resp.status_code < 500
            results["checks"][name] = {
                "status": status,
                "code": resp.status_code,
                "critical": critical
            }
            if not status and critical:
                results["overall"] = False
        except Exception as e:
            results["checks"][name] = {
                "status": False,
                "error": str(e),
                "critical": critical
            }
            if critical:
                results["overall"] = False

    return results


def check_proxy(proxy: str) -> Tuple[bool, str]:
    """Check if proxy is working."""
    if not proxy:
        return True, "No proxy configured"

    try:
        session = requests.Session()
        session.proxies = {"http": proxy, "https": proxy}

        # Test with a simple endpoint
        resp = session.get("https://api.ipify.org?format=json", timeout=10)
        if resp.status_code == 200:
            ip = resp.json().get("ip", "unknown")
            return True, f"Proxy OK (IP: {ip})"
        else:
            return False, f"Proxy returned status {resp.status_code}"

    except Exception as e:
        return False, f"Proxy error: {e}"


def check_email_provider(provider_name: str, config: dict = None) -> Tuple[bool, str]:
    """Check if email provider is accessible."""
    try:
        if provider_name in ["duckmail", "mail_tm"]:
            resp = requests.get("https://api.mail.tm", timeout=10)
            if resp.status_code < 500:
                return True, "Mail.tm API accessible"
            else:
                return False, f"Mail.tm returned {resp.status_code}"

        elif provider_name == "cloudflare":
            if config and config.get("worker_url"):
                try:
                    resp = requests.get(config["worker_url"], timeout=10)
                    return True, "Cloudflare worker accessible"
                except:
                    return False, "Cannot reach Cloudflare worker"
            return False, "No worker_url configured"

        return True, f"Provider {provider_name} check skipped"

    except Exception as e:
        return False, f"Email provider error: {e}"


def run_all_checks(config: dict = None) -> Dict[str, Any]:
    """Run all connectivity checks."""
    config = config or {}
    results = {
        "timestamp": __import__("time").time(),
        "proxy": {},
        "endpoints": {},
        "email": {},
        "overall": True
    }

    # Check proxy
    proxy = config.get("proxy", "")
    if proxy:
        proxy_ok, proxy_msg = check_proxy(proxy)
        results["proxy"] = {"ok": proxy_ok, "message": proxy_msg}
        if not proxy_ok:
            results["overall"] = False

    # Check endpoints
    conn_results = check_connectivity(proxy)
    results["endpoints"] = conn_results
    if not conn_results["overall"]:
        results["overall"] = False

    # Check email provider
    provider = config.get("email_provider", "duckmail")
    email_config = config.get("email_config", {}).get(provider, {})
    email_ok, email_msg = check_email_provider(provider, email_config)
    results["email"] = {"ok": email_ok, "message": email_msg, "provider": provider}
    if not email_ok:
        results["overall"] = False

    return results


if __name__ == "__main__":
    import json
    import sys

    # Load config if exists
    config = {}
    try:
        with open("config.json") as f:
            config = json.load(f)
    except:
        pass

    results = run_all_checks(config)

    print(json.dumps(results, indent=2))

    if not results["overall"]:
        print("\n⚠️  Some connectivity checks failed!")
        sys.exit(1)
    else:
        print("\n✓ All connectivity checks passed")
        sys.exit(0)
