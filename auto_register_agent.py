"""
Auto-register agent.

Polls the gpt2api server's /auto-register/status endpoint. When the server
reports enabled && need_refill, runs the local registration tool to top the
account pool back up, then uploads results via the built-in CPA uploader.

Usage:
    python auto_register_agent.py          # run forever (Ctrl+C to stop)
    python auto_register_agent.py --once   # single check and exit
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_URL = "https://api.deeproast.sryze.cc/api/auto_register/status"
AGENT_CFG = os.path.join(BASE_DIR, "auto_register_agent.json")
LOG_FILE = os.path.join(BASE_DIR, "auto_register_agent.log")


def log(msg: str):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_management_key():
    try:
        with open(os.path.join(BASE_DIR, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        return str(cfg.get("cpa_management_key") or "").strip()
    except Exception:
        return ""


def get_status():
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    }
    key = load_management_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(STATUS_URL, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_registration(count: int) -> int:
    log(f"running registration count={count}")
    try:
        proc = subprocess.run(
            [sys.executable, "chatgpt_register_ttk.py", "cli", "--count", str(count)],
            cwd=BASE_DIR,
            timeout=60 * 60,
        )
        return proc.returncode
    except Exception as exc:
        log(f"registration subprocess error: {exc}")
        return -1


def check_once():
    try:
        data = get_status()
    except Exception as e:
        log(f"status error: {e}")
        return
    log(
        f"pool={data.get('pool_count')} min={data.get('min_pool')} "
        f"enabled={data.get('enabled')} need_refill={data.get('need_refill')}"
    )
    if data.get("enabled") and data.get("need_refill"):
        count = max(1, int(data.get("refill_count") or 1))
        try:
            run_registration(count)
        except Exception as exc:
            log(f"registration error: {exc}")


def main():
    once = "--once" in sys.argv
    while True:
        try:
            check_once()
        except Exception as exc:
            log(f"check error: {exc}")
        if once:
            break
        try:
            with open(AGENT_CFG, encoding="utf-8") as f:
                interval = int(json.load(f).get("interval_sec", 600))
        except Exception:
            interval = 600
        time.sleep(max(30, interval))


if __name__ == "__main__":
    main()
