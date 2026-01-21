#!/usr/bin/env python3
"""
Manual login helper to capture Reddit cookies into a .pkl file.

Usage:
  python scripts/one_time/capture_cookies.py --output data/cookies_account1.pkl
  python scripts/one_time/capture_cookies.py --name account1
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]

from selenium_automation.login_manager import LoginManager


def build_output_path(name: str, output: str) -> Path:
    if output:
        return Path(output)
    suffix = name.strip() or datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("data") / f"cookies_{suffix}.pkl"

def load_accounts(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def save_accounts(path: Path, accounts: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(accounts, indent=2), encoding="utf-8")


def find_account(accounts: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    for account in accounts:
        if account.get("name") == name:
            return account
    return None


def infer_env_vars(name: str) -> Dict[str, str]:
    name = name.strip()
    if name.lower().startswith("account") and name[7:].isdigit():
        suffix = name[7:]
        return {
            "email_env_var": f"REDDIT_EMAIL_{suffix}",
            "password_env_var": f"REDDIT_PASSWORD_{suffix}",
        }
    return {}


def init_accounts(count: int) -> List[Dict[str, Any]]:
    accounts: List[Dict[str, Any]] = []
    for idx in range(1, count + 1):
        name = f"account{idx}"
        entry = {
            "name": name,
            "cookies_path": f"data/cookies_{name}.pkl",
            "activity_profile": "researcher",
        }
        entry.update(infer_env_vars(name))
        accounts.append(entry)
    return accounts


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture Reddit cookies after manual login.")
    parser.add_argument("--output", default="", help="Path to save cookies (e.g., data/cookies_account1.pkl).")
    parser.add_argument("--name", default="", help="Account name (used to find/update config/accounts.json).")
    parser.add_argument("--init-accounts", type=int, default=0, help="Create N placeholder accounts when none exist.")
    parser.add_argument("--accounts-path", default="config/accounts.json", help="Path to accounts.json")
    parser.add_argument("--url", default="https://www.reddit.com/login", help="Login URL to open.")
    parser.add_argument("--headless", action="store_true", help="Run headless (manual login not recommended).")
    args = parser.parse_args()

    accounts_path = Path(args.accounts_path)
    accounts = load_accounts(accounts_path)

    if not args.name:
        if args.output:
            raise RuntimeError("Use --output only with --name to avoid overwriting multiple accounts.")
        if not accounts and args.init_accounts > 0:
            accounts = init_accounts(args.init_accounts)
            save_accounts(accounts_path, accounts)
        if not accounts:
            raise RuntimeError("No accounts found. Provide --name to create a new entry.")
        print("No --name provided; capturing cookies for all accounts in config/accounts.json.")
        target_names = [acc.get("name", "") for acc in accounts if acc.get("name")]
    else:
        target_names = [args.name]

    if args.headless:
        print("Warning: headless mode makes manual login difficult.")

    for name in target_names:
        if not name:
            continue
        account = find_account(accounts, name)
        if account is None:
            account = {"name": name, "activity_profile": "researcher"}
            account.update(infer_env_vars(name))
            accounts.append(account)

        output_path = build_output_path(name, args.output or account.get("cookies_path", ""))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        login_manager = LoginManager(headless=args.headless)
        driver = login_manager.create_driver(headless=args.headless)
        if not driver:
            raise RuntimeError("Failed to create browser driver.")

        print(f"Opening {args.url} for {name}...")
        driver.get(args.url)
        print(f"Please log in as {name} in the browser window.")
        input("Press Enter once you are logged in and the page is fully loaded...")

        saved = login_manager.save_login_cookies(str(output_path))
        if saved:
            account["cookies_path"] = str(output_path)
            save_accounts(accounts_path, accounts)
            print(f"Cookies saved to {output_path} and linked in {accounts_path}")
        else:
            print("Failed to save cookies.")

        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
