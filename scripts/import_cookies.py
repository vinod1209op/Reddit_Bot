#!/usr/bin/env python3
"""
Import a JSON cookie export and save as Selenium cookies.pkl, updating accounts.json.

Usage:
  python scripts/import_cookies.py --input cookies.json --name account1
"""
import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_cookies(raw: Any, domain_filter: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if isinstance(raw, dict) and "cookies" in raw:
        raw = raw.get("cookies", [])
    if not isinstance(raw, list):
        return items

    for cookie in raw:
        if not isinstance(cookie, dict):
            continue
        domain = cookie.get("domain", "") or ""
        if domain_filter and domain_filter not in domain:
            continue

        expiry = cookie.get("expiry", cookie.get("expirationDate"))
        if isinstance(expiry, float):
            expiry = int(expiry)
        if isinstance(expiry, str) and expiry.isdigit():
            expiry = int(expiry)

        item = {
            "name": cookie.get("name"),
            "value": cookie.get("value"),
            "domain": domain,
            "path": cookie.get("path", "/"),
            "expiry": expiry,
            "secure": cookie.get("secure"),
            "httpOnly": cookie.get("httpOnly"),
        }
        # Drop empty keys to keep Selenium happy.
        cleaned = {k: v for k, v in item.items() if v is not None}
        if cleaned.get("name") and cleaned.get("value"):
            items.append(cleaned)
    return items


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Import cookies JSON into Selenium .pkl format.")
    parser.add_argument("--input", required=True, help="Path to cookies JSON export.")
    parser.add_argument("--name", required=True, help="Account name (updates config/accounts.json).")
    parser.add_argument("--accounts-path", default="config/accounts.json")
    parser.add_argument("--output", default="", help="Optional output path for cookies.pkl")
    parser.add_argument("--domain", default="reddit.com", help="Domain filter (default: reddit.com)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    raw = load_json(input_path)
    cookies = normalize_cookies(raw, args.domain)
    if not cookies:
        raise SystemExit("No cookies matched the domain filter.")

    output_path = Path(args.output) if args.output else Path("data") / f"cookies_{args.name}.pkl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        pickle.dump(cookies, handle)

    accounts_path = Path(args.accounts_path)
    accounts = load_accounts(accounts_path)
    account = next((a for a in accounts if a.get("name") == args.name), None)
    if not account:
        account = {"name": args.name}
        accounts.append(account)
    account["cookies_path"] = str(output_path)
    save_accounts(accounts_path, accounts)

    print(f"Imported {len(cookies)} cookies -> {output_path}")
    print(f"Updated {accounts_path} for {args.name}")


if __name__ == "__main__":
    main()
