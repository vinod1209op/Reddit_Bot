#!/usr/bin/env python3
"""
Auto-discover newly moderated subreddits for a given account and run full moderation setup.
Scopes to a single account (default: account4) and assigns a profile automatically based on subreddit name.
"""

import argparse
import json
import os
import pickle
from pathlib import Path
from typing import Dict, List, Set

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))

from microdose_study_bot.core.logging import UnifiedLogger
from scripts.moderation.manage_moderation import SeleniumModerationManager

logger = UnifiedLogger("AutoModerationSetup").get_logger()

MOD_LIST_URL = "https://www.reddit.com/subreddits/mine/moderator.json?limit=100"
KNOWN_PATH = Path("data/moderated_known.json")


def load_cookies(cookie_path: Path) -> List[Dict]:
    if not cookie_path.exists():
        raise FileNotFoundError(f"Cookie file not found: {cookie_path}")
    with cookie_path.open("rb") as f:
        return pickle.load(f)


def fetch_moderated_subs(cookie_path: Path, user_agent: str = "modsetup-script/1.0") -> List[str]:
    cookies = load_cookies(cookie_path)
    session = requests.Session()
    for c in cookies:
        if "domain" in c and c["domain"].startswith("."):
            c["domain"] = c["domain"][1:]
        session.cookies.set(c["name"], c["value"], domain=c.get("domain", "reddit.com"))
    headers = {"User-Agent": user_agent}
    resp = session.get(MOD_LIST_URL, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    children = data.get("data", {}).get("children", []) or []
    subs = []
    for child in children:
        sub = child.get("data", {}).get("display_name")
        if sub:
            subs.append(sub)
    return subs


def load_known(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text())
        return set(data.get("subreddits", [])) if isinstance(data, dict) else set(data)
    except Exception:
        return set()


def save_known(path: Path, subs: Set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"subreddits": sorted(subs)}, indent=2))


def load_profile_map(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data.get("profile_map", {}) or {}
    except Exception:
        return {}


def save_profile_map(path: Path, profile_map: Dict[str, str]) -> None:
    if not path.exists():
        base = {"profile_map": profile_map}
    else:
        base = json.loads(path.read_text())
        base["profile_map"] = profile_map
    path.write_text(json.dumps(base, indent=2))


def guess_profile(subreddit: str) -> str:
    name = subreddit.lower()
    if any(k in name for k in ("clinic", "clinical", "trial")):
        return "clinical"
    if any(k in name for k in ("wellbeing", "wellness", "support", "therapy", "mental")):
        return "wellbeing"
    if any(k in name for k in ("science", "study", "studies", "research")):
        return "research"
    return "research"


def main():
    parser = argparse.ArgumentParser(description="Auto setup moderation for newly moderated subreddits")
    parser.add_argument("--account", default="account4", help="Account name (default: account4)")
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without changes")
    parser.add_argument("--max-new", type=int, default=1, help="Max new subreddits to process per run")
    parser.add_argument("--force", action="store_true", help="Reapply setup even for subs already processed (ignores known cache)")
    args = parser.parse_args()

    # Force to single account (per user request)
    if args.account != "account4":
        logger.info("Overriding account to account4")
        args.account = "account4"

    # Prefer bundled chromedriver if present
    bundled_driver = ROOT / "chromedriver-mac-x64" / "chromedriver"
    if bundled_driver.exists():
        os.environ.setdefault("CHROMEDRIVER_PATH", str(bundled_driver))
    os.environ.setdefault("SELENIUM_USE_UNDETECTED", "0")

    # Discover moderated subs
    account_config_path = ROOT / "config" / "accounts.json"
    accounts = json.loads(account_config_path.read_text())
    acct = next((a for a in accounts if a.get("name") == args.account), None)
    if not acct:
        raise SystemExit(f"Account {args.account} not found in config/accounts.json")
    cookie_path = ROOT / acct.get("cookies_path", f"data/cookies_{args.account}.pkl")

    try:
        moderated = fetch_moderated_subs(cookie_path)
    except Exception as exc:
        logger.error(f"Failed to fetch moderated subreddits: {exc}")
        raise SystemExit(1)

    known = load_known(KNOWN_PATH)
    candidates = moderated if args.force else [s for s in moderated if s not in known]
    new_subs = candidates[: args.max_new]

    if not new_subs:
        logger.info("No new subreddits to set up.")
        return

    profile_map_path = ROOT / "config" / "subreddit_network.json"
    profile_map = load_profile_map(profile_map_path)

    manager = SeleniumModerationManager(account_name=args.account, headless=args.headless, dry_run=args.dry_run)

    for sub in new_subs:
        profile = guess_profile(sub)
        profile_map[sub] = profile
        manager.profile_map[sub] = profile  # update in-memory map
        logger.info(f"[{sub}] assigned profile '{profile}'")

        if args.dry_run:
            logger.info(f"[dry-run] Would run setup for r/{sub}")
            known.add(sub)
            continue

        ok = manager.setup_complete_moderation(sub)
        if ok:
            known.add(sub)
            logger.info(f"[{sub}] setup complete")
        else:
            logger.warning(f"[{sub}] setup failed")

    if not args.dry_run:
        save_known(KNOWN_PATH, known)
        save_profile_map(profile_map_path, profile_map)

    manager.cleanup()


if __name__ == "__main__":
    main()
