"""
ChatGPT Registration Tool - Main GUI/CLI Entry Point
Based on grokRegister-cpa grok_register_ttk.py architecture

Features:
- Protocol-based (HTTP) and browser-based registration modes
- Multiple temporary email providers
- Batch registration with pipeline
- GUI and CLI interfaces
- Token extraction and export
"""

import json
import os
import sys
import time
import random
import argparse
import threading
import logging
import queue
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox

# Force UTF-8 output on Windows consoles (GBK default crashes on non-ASCII chars)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from email_providers.common import EmailProvider
from email_providers.duckmail import DuckMailProvider
from email_providers.outlook import OutlookProvider
from email_providers.cloudflare_temp import CloudflareTempProvider
from protocol.gpt_register import GPTRegistrar
from browser_register import BrowserRegistrar
from cpa_upload import CPAUploader

EMAIL_PROVIDER_NAMES = ["duckmail", "mail_tm", "outlook", "cloudflare_temp"]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ChatGPTRegisterApp:
    """Main application class with GUI and CLI support."""

    def __init__(self):
        self.config = self._load_config()
        self.running = False
        self.results = []
        self.email_provider = None
        self.ui_queue = queue.Queue()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from config.json."""
        config_path = Path("config.json")
        if config_path.exists():
            with open(config_path) as f:
                return json.load(f)

        # Return defaults
        return {
            "email_provider": "duckmail",
            "email_config": {},
            "register_mode": "protocol",
            "register_workers": 2,
            "count": 1,
            "proxy": "",
            "headless": True,
            "chrome_profile": "",
            "output_dir": "./accounts",
            "timeout": 120,
            "retries": 3,
            "delay_between": [5, 15]
        }

    def _save_config(self):
        """Save current configuration."""
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)

    def _get_email_provider(self) -> EmailProvider:
        """Get configured email provider instance."""
        provider_name = self.config.get("email_provider", "duckmail")
        email_config = self.config.get("email_config", {}).get(provider_name, {})

        if provider_name == "duckmail":
            return DuckMailProvider(email_config)
        elif provider_name == "mail_tm":
            return DuckMailProvider(email_config)  # Same implementation
        elif provider_name == "outlook":
            return OutlookProvider(email_config)
        elif provider_name == "cloudflare_temp":
            return CloudflareTempProvider(email_config)
        else:
            # Default to duckmail
            return DuckMailProvider({})

    def generate_password(self) -> str:
        """Generate a secure random password."""
        import string
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(random.choices(chars, k=16))

    def register_single(self, email: str = None) -> Optional[Dict[str, Any]]:
        """Register a single account."""
        mode = self.config.get("register_mode", "protocol")
        try:
            # Create email if not provided
            if not email:
                if not self.email_provider:
                    self.email_provider = self._get_email_provider()

                self.log("Creating temporary email...")
                email = self.email_provider.create_email()
                self.log(f"Created email: {email}")

            # Generate password
            password = self.generate_password()

            if mode == "browser":
                self.log("Browser mode: a Chrome window will open. Please complete signup when prompted.")
                registrar = BrowserRegistrar(
                    email_provider=self.email_provider,
                    proxy=self.config.get("proxy"),
                    chrome_profile=self.config.get("chrome_profile", ""),
                    on_log=self.log,
                    on_progress=self.log,
                )
                result = registrar.register(email=email, password=password)
            else:
                # Protocol mode (pure HTTP via GPTRegistrar)
                registrar = GPTRegistrar(
                    email_provider=self.email_provider,
                    proxy=self.config.get("proxy", ""),
                    on_log=self.log,
                    on_progress=self.log,
                )

                self.log(f"Starting registration for {email}...")

                result = registrar.register(email=email, password=password)

            if result:
                # Add additional info
                result["registered_at"] = datetime.now().isoformat()
                result["provider"] = self.config.get("email_provider")

                self.log(f"[OK] Successfully registered: {email}")
                return result
            else:
                self.log(f"[FAIL] Registration failed for {email}")
                return None

        except Exception as e:
            self.log(f"Error during registration: {e}")
            return None

    def _get_verification_code(self, email: str) -> Optional[str]:
        """Get verification code for email."""
        if not self.email_provider:
            self.email_provider = self._get_email_provider()

        self.log(f"Waiting for verification code for {email}...")
        code = self.email_provider.wait_for_code(
            email,
            timeout=self.config.get("timeout", 120)
        )

        if code:
            masked = code if len(code) <= 2 else f"{code[:2]}***{code[-2:]}"
            self.log(f"Got verification code: {masked}")
        else:
            self.log("Failed to get verification code")

        return code

    def register_batch(self, count: int) -> List[Dict[str, Any]]:
        """Register multiple accounts."""
        results = []
        self.running = True

        for i in range(count):
            if not self.running:
                break

            self.log(f"\n--- Starting registration {i + 1}/{count} ---")

            result = self.register_single()
            if result:
                results.append(result)
                self._save_result(result)
                self._upload_result(result)

            # Delay between registrations
            if i < count - 1:
                delay_cfg = self.config.get("delay_between") or [5, 15]
                delay_min = delay_cfg[0] if len(delay_cfg) > 0 and isinstance(delay_cfg[0], int) else 5
                delay_max = delay_cfg[1] if len(delay_cfg) > 1 and isinstance(delay_cfg[1], int) else 15
                delay = random.randint(min(delay_min, delay_max), max(delay_min, delay_max))
                self.log(f"Waiting {delay}s before next registration...")
                for _ in range(delay):
                    if not self.running:
                        break
                    time.sleep(1)

        self.running = False
        return results

    def _save_result(self, result: Dict[str, Any]):
        """Save registration result to file."""
        output_dir = Path(self.config.get("output_dir", "./accounts"))
        output_dir.mkdir(exist_ok=True)

        # Save individual JSON
        email = result.get("email", "unknown")
        safe_email = email.replace("@", "_at_").replace(".", "_")
        json_path = output_dir / f"chatgpt_{safe_email}.json"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        # Append to accounts.txt
        accounts_path = output_dir / "accounts.txt"
        with open(accounts_path, "a", encoding="utf-8") as f:
            f.write(f"{email}----{result.get('password', '')}\n")

        self.log(f"Saved result to {json_path}")

    def _upload_result(self, result: Dict[str, Any]):
        """Upload registration result to remote gpt2api if configured."""
        remote_url = self.config.get("cpa_remote_url", "")
        management_key = self.config.get("cpa_management_key", "")
        if not remote_url or not management_key:
            self.log("CPA upload skipped: cpa_remote_url/cpa_management_key not configured")
            return
        uploader = CPAUploader(
            remote_url=remote_url,
            management_key=management_key,
            on_log=self.log,
            on_progress=self.log,
        )
        uploader.upload_account(result)

    def log(self, message: str):
        """Log message (override in GUI/CLI)."""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        logger.info(message)

    def run_cli(self, count: int = None, once: bool = False):
        """Run in CLI mode."""
        count = count or self.config.get("count", 1)
        if once:
            count = 1

        self.log(f"Starting ChatGPT registration tool (count={count})")
        self.log(f"Mode: {self.config.get('register_mode')}")
        self.log(f"Email provider: {self.config.get('email_provider')}")

        results = self.register_batch(count)

        self.log(f"\n=== Completed: {len(results)}/{count} successful ===")

        if results:
            print("\nRegistered accounts:")
            for r in results:
                print(f"  {r['email']} | Password: {r['password']}")

    def run_gui(self):
        """Run GUI mode."""
        root = tk.Tk()
        root.title("ChatGPT Registration Tool")
        root.geometry("800x600")
        self.root_ref = root

        # Create main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configuration frame
        config_frame = ttk.LabelFrame(main_frame, text="Configuration", padding="5")
        config_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        # Email provider
        ttk.Label(config_frame, text="Email Provider:").grid(row=0, column=0, sticky=tk.W)
        current_provider = self.config.get("email_provider", "duckmail")
        provider_values = EMAIL_PROVIDER_NAMES if current_provider in EMAIL_PROVIDER_NAMES else [current_provider] + EMAIL_PROVIDER_NAMES
        self.email_var = tk.StringVar(value=current_provider)
        email_combo = ttk.Combobox(config_frame, textvariable=self.email_var,
                                   values=provider_values)
        email_combo.grid(row=0, column=1, padx=5)

        # Count
        ttk.Label(config_frame, text="Count:").grid(row=0, column=2, sticky=tk.W, padx=(20, 0))
        self.count_var = tk.IntVar(value=self.config.get("count", 1))
        ttk.Spinbox(config_frame, from_=1, to=100, textvariable=self.count_var, width=10).grid(row=0, column=3)

        # Mode
        ttk.Label(config_frame, text="Mode:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.mode_var = tk.StringVar(value=self.config.get("register_mode", "protocol"))
        ttk.Radiobutton(config_frame, text="Protocol (HTTP)", variable=self.mode_var, value="protocol").grid(row=1, column=1)
        ttk.Radiobutton(config_frame, text="Browser", variable=self.mode_var, value="browser").grid(row=1, column=2)

        # Proxy
        ttk.Label(config_frame, text="Proxy:").grid(row=2, column=0, sticky=tk.W)
        self.proxy_var = tk.StringVar(value=self.config.get("proxy", ""))
        ttk.Entry(config_frame, textvariable=self.proxy_var, width=40).grid(row=2, column=1, columnspan=3, sticky=(tk.W, tk.E))

        # Log frame
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="5")
        log_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Control frame
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=2, column=0, columnspan=2, pady=10)

        self.start_btn = ttk.Button(control_frame, text="Start Registration", command=self._gui_start)
        self.start_btn.grid(row=0, column=0, padx=5)

        self.stop_btn = ttk.Button(control_frame, text="Stop", command=self._gui_stop, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, padx=5)

        ttk.Button(control_frame, text="Clear Log", command=lambda: self.log_text.delete(1.0, tk.END)).grid(row=0, column=2, padx=5)
        ttk.Button(control_frame, text="Save Config", command=self._gui_save_config).grid(row=0, column=3, padx=5)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(main_frame, textvariable=self.status_var).grid(row=3, column=0, columnspan=2, sticky=tk.W)

        # Configure grid weights
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        # Override log method for GUI: worker threads only push to queue
        self.log = self._gui_log

        # Poll UI queue on the main thread (Tkinter is not thread-safe)
        root.after(100, self._poll_ui)

        root.mainloop()

    def _poll_ui(self):
        """Drain UI events queue on the main thread."""
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "log":
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    self.log_text.insert(tk.END, f"[{timestamp}] {payload}\n")
                    self.log_text.see(tk.END)
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "running":
                    self.start_btn.config(state=tk.DISABLED if payload else tk.NORMAL)
                    self.stop_btn.config(state=tk.NORMAL if payload else tk.DISABLED)
        except queue.Empty:
            pass
        if self.root_ref:
            self.root_ref.after(100, self._poll_ui)

    def _gui_log(self, message: str):
        """GUI log handler - thread-safe: pushes to queue, main thread renders."""
        self.ui_queue.put(("log", message))

    def _gui_start(self):
        """GUI start button handler."""
        self.config["email_provider"] = self.email_var.get()
        self.config["count"] = self.count_var.get()
        self.config["register_mode"] = self.mode_var.get()
        self.config["proxy"] = self.proxy_var.get()

        self._save_config()

        self.ui_queue.put(("running", True))
        self.ui_queue.put(("status", "Running..."))

        # Run in thread
        def run():
            self.results = self.register_batch(self.config["count"])
            self.ui_queue.put(("status", f"Completed: {len(self.results)} successful"))
            self.ui_queue.put(("running", False))

        threading.Thread(target=run, daemon=True).start()

    def _gui_stop(self):
        """GUI stop button handler."""
        self.running = False
        self.ui_queue.put(("running", False))

    def _gui_save_config(self):
        """GUI save config handler."""
        self.config["email_provider"] = self.email_var.get()
        self.config["count"] = self.count_var.get()
        self.config["register_mode"] = self.mode_var.get()
        self.config["proxy"] = self.proxy_var.get()

        self._save_config()
        messagebox.showinfo("Success", "Configuration saved")


def main():
    parser = argparse.ArgumentParser(description="ChatGPT Registration Tool")
    parser.add_argument("mode", nargs="?", choices=["gui", "cli"], default="gui",
                        help="Run mode: gui or cli (default: gui)")
    parser.add_argument("--count", type=int, help="Number of accounts to register")
    parser.add_argument("--once", action="store_true", help="Register single account and exit")
    parser.add_argument("--config", help="Path to config file")

    args = parser.parse_args()

    app = ChatGPTRegisterApp()

    # Override config path if specified
    if args.config:
        with open(args.config) as f:
            app.config = json.load(f)

    if args.mode == "cli":
        app.run_cli(count=args.count, once=args.once)
    else:
        app.run_gui()


if __name__ == "__main__":
    main()
