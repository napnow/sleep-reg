"""
Turnstile token minting script for ChatGPT registration.
Based on grokRegister-cpa scripts/turnstile_mint.py

This script opens a minimal browser session to obtain a valid
Cloudflare Turnstile token which is needed for some signup flows.
"""

import sys
import json
import time
import argparse
from typing import Optional

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)


def mint_turnstile_token(
    site_key: str,
    page_url: str,
    headless: bool = True,
    timeout: int = 60,
    proxy: str = None
) -> Optional[str]:
    """
    Mint a Turnstile token for the given site.

    Args:
        site_key: Cloudflare Turnstile site key
        page_url: URL of the page with Turnstile
        headless: Run browser in headless mode
        timeout: Max time to wait for token (seconds)
        proxy: Optional proxy URL

    Returns:
        Turnstile token string or None on failure
    """
    token = None

    with sync_playwright() as p:
        # Launch browser with stealth options
        browser_args = {
            "headless": headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ]
        }

        if proxy:
            browser_args["proxy"] = {"server": proxy}

        browser = p.chromium.launch(**browser_args)

        try:
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
            )

            # Add stealth scripts
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
            """)

            page = context.new_page()

            # Set up token capture
            page.evaluate("""
                window.turnstileToken = null;
                const originalRender = window.turnstile?.render;
                if (originalRender) {
                    window.turnstile.render = function(container, options) {
                        const origCallback = options.callback;
                        options.callback = function(token) {
                            window.turnstileToken = token;
                            if (origCallback) origCallback(token);
                        };
                        return originalRender.call(this, container, options);
                    };
                }
            """)

            # Navigate to page
            print(f"Navigating to {page_url}")
            page.goto(page_url, wait_until="networkidle", timeout=30000)

            # Wait for Turnstile to be ready and solve
            start_time = time.time()
            while time.time() - start_time < timeout:
                # Check if we got a token
                token = page.evaluate("window.turnstileToken")
                if token:
                    print(f"Got Turnstile token: {token[:30]}...")
                    break

                # Try to trigger Turnstile if not already
                page.evaluate("""
                    if (window.turnstile && !window.turnstileToken) {
                        const containers = document.querySelectorAll('[class*="cf-turnstile"], [data-sitekey]');
                        containers.forEach(c => {
                            if (!c.hasAttribute('data-rendered')) {
                                c.setAttribute('data-rendered', 'true');
                                window.turnstile.render(c, {
                                    sitekey: c.getAttribute('data-sitekey') || arguments[0],
                                    callback: function(t) { window.turnstileToken = t; }
                                });
                            }
                        });
                    }
                """, site_key)

                time.sleep(1)

            if not token:
                print("Failed to obtain Turnstile token within timeout")

        except Exception as e:
            print(f"Error minting Turnstile token: {e}")
        finally:
            browser.close()

    return token


def main():
    parser = argparse.ArgumentParser(description="Mint Cloudflare Turnstile token")
    parser.add_argument("--site-key", required=True, help="Turnstile site key")
    parser.add_argument("--page-url", required=True, help="Page URL with Turnstile")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds")
    parser.add_argument("--proxy", help="Proxy URL")
    parser.add_argument("--output", help="Output file for token")

    args = parser.parse_args()

    token = mint_turnstile_token(
        site_key=args.site_key,
        page_url=args.page_url,
        headless=args.headless,
        timeout=args.timeout,
        proxy=args.proxy
    )

    if token:
        result = {
            "token": token,
            "site_key": args.site_key,
            "timestamp": time.time()
        }

        if args.output:
            with open(args.output, "w") as f:
                json.dump(result, f)
            print(f"Token saved to {args.output}")
        else:
            print(json.dumps(result))

        sys.exit(0)
    else:
        print("Failed to mint token")
        sys.exit(1)


if __name__ == "__main__":
    main()
