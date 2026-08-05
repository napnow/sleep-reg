#!/usr/bin/env python3
"""
Quick test script to verify ChatGPT registration tool setup.
Run this before attempting actual registrations.
"""

import sys
import json
from pathlib import Path

# Force UTF-8 output on Windows consoles (GBK default crashes on non-ASCII chars)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")

    required_modules = [
        ("curl_cffi", "curl-cffi for TLS fingerprinting"),
        ("requests", "requests for HTTP"),
    ]

    optional_modules = [
        ("playwright", "Playwright for browser automation"),
        ("tkinter", "tkinter for GUI"),
    ]

    failed = []

    for module, desc in required_modules:
        try:
            __import__(module.replace("-", "_"))
            print(f"  ✓ {module}: {desc}")
        except ImportError:
            print(f"  ✗ {module}: {desc} - NOT INSTALLED")
            failed.append(module)

    for module, desc in optional_modules:
        try:
            __import__(module.replace("-", "_"))
            print(f"  ✓ {module}: {desc}")
        except ImportError:
            print(f"  ⚠ {module}: {desc} - optional, not installed")

    return len(failed) == 0


def test_email_provider():
    """Test email provider initialization."""
    print("\nTesting email providers...")

    try:
        from email_providers import DuckMailProvider, get_provider

        # Test duckmail provider
        provider = DuckMailProvider({})
        print("  ✓ DuckMailProvider initialized")

        # Test provider registry
        p = get_provider("duckmail")
        print("  ✓ Provider registry working")

        return True
    except Exception as e:
        print(f"  ✗ Email provider test failed: {e}")
        return False


def test_protocol_signup():
    """Test protocol registration module."""
    print("\nTesting protocol registration...")

    try:
        from protocol.gpt_register import GPTRegistrar
        from protocol.pkce import generate_pkce

        # Test PKCE generation
        verifier, challenge = generate_pkce()
        if len(verifier) > 20 and len(challenge) > 20:
            print("  ✓ PKCE generation working")
        else:
            print("  ✗ PKCE generation issue")
            return False

        return True
    except Exception as e:
        print(f"  ✗ Protocol registration test failed: {e}")
        return False


def test_config():
    """Test configuration loading."""
    print("\nTesting configuration...")

    config_path = Path("config.json")
    example_path = Path("config.example.json")

    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
            print(f"  ✓ config.json loaded ({len(config)} settings)")
            return True
        except Exception as e:
            print(f"  ✗ config.json error: {e}")
            return False
    elif example_path.exists():
        print("  ⚠ Using config.example.json (copy to config.json)")
        try:
            with open(example_path) as f:
                config = json.load(f)
            print(f"  ✓ config.example.json loaded")
            return True
        except Exception as e:
            print(f"  ✗ config.example.json error: {e}")
            return False
    else:
        print("  ✗ No configuration file found")
        return False


def test_connectivity():
    """Quick connectivity test."""
    print("\nTesting connectivity...")

    try:
        import requests

        # Test basic connectivity
        resp = requests.get("https://auth.openai.com", timeout=10, allow_redirects=True)
        if resp.status_code < 500:
            print(f"  ✓ auth.openai.com reachable (status: {resp.status_code})")
        else:
            print(f"  ⚠ auth.openai.com returned {resp.status_code}")

        # Test mail provider
        resp = requests.get("https://api.mail.tm", timeout=10)
        if resp.status_code < 500:
            print(f"  ✓ api.mail.tm reachable (status: {resp.status_code})")
        else:
            print(f"  ⚠ api.mail.tm returned {resp.status_code}")

        return True
    except Exception as e:
        print(f"  ⚠ Connectivity test failed (may need proxy): {e}")
        return True  # Not critical for setup test


def main():
    print("=" * 50)
    print("ChatGPT Registration Tool - Setup Test")
    print("=" * 50)

    results = []

    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("Email Providers", test_email_provider()))
    results.append(("Protocol Signup", test_protocol_signup()))
    results.append(("Configuration", test_config()))
    results.append(("Connectivity", test_connectivity()))

    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)

    passed = 0
    for name, result in results:
        status = "PASS" if result else "FAIL"
        symbol = "✓" if result else "✗"
        print(f"  {symbol} {name}: {status}")
        if result:
            passed += 1

    print(f"\n{passed}/{len(results)} tests passed")

    if passed == len(results):
        print("\n✓ Setup looks good! Ready to run.")
        print("\nNext steps:")
        print("  1. Copy config.example.json to config.json")
        print("  2. Edit config.json with your settings")
        print("  3. Run: python chatgpt_register_ttk.py")
        return 0
    else:
        print("\n⚠ Some tests failed. Please fix issues above.")
        print("\nCommon fixes:")
        print("  - pip install -r requirements.txt")
        print("  - playwright install chromium")
        print("  - Copy config.example.json to config.json")
        return 1


if __name__ == "__main__":
    sys.exit(main())
