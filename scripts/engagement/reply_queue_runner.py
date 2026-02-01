#!/usr/bin/env python3
"""
Queue-based engagement replies:
- account1 generates 3 replies for a random recent post, posts one, queues the rest.
- account2/3 consume one queued reply each (no re-scrape).
Queue is stored locally and synced to Supabase.
"""
import argparse
import json
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests

from microdose_study_bot.core.config import ConfigManager
from microdose_study_bot.core.logging import UnifiedLogger
from microdose_study_bot.reddit_selenium.main import RedditAutomation

try:
    from openai import OpenAI  # Optional
except ImportError:  # pragma: no cover
    OpenAI = None


logger = UnifiedLogger("EngagementQueue").get_logger()


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        content = path.read_text().strip()
        return json.loads(content) if content else default
    except Exception:
        return default


def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _load_replied_map(prefix: str) -> Dict[str, List[str]]:
    key = f"{prefix}/engagement_replied_posts.json"
    content = sb_download(key)
    if content:
        try:
            data = json.loads(content.decode())
            if isinstance(data, dict):
                return {k: list(v or []) for k, v in data.items()}
        except Exception:
            pass
    return {}


def _save_replied_map(prefix: str, data: Dict[str, List[str]]) -> None:
    key = f"{prefix}/engagement_replied_posts.json"
    sb_upload(key, json.dumps(data, indent=2).encode("utf-8"))


def sb_download(key: str) -> Optional[bytes]:
    url = f"{os.environ.get('SUPABASE_URL','').rstrip('/')}/storage/v1/object/{os.environ.get('SUPABASE_BUCKET','')}/{key}"
    headers = {
        "Authorization": f"Bearer {os.environ.get('SUPABASE_SERVICE_ROLE_KEY','')}",
        "apikey": os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.content
    except Exception:
        return None
    return None


def sb_upload(key: str, data: bytes, content_type: str = "application/json") -> None:
    url = f"{os.environ.get('SUPABASE_URL','').rstrip('/')}/storage/v1/object/{os.environ.get('SUPABASE_BUCKET','')}/{key}"
    headers = {
        "Authorization": f"Bearer {os.environ.get('SUPABASE_SERVICE_ROLE_KEY','')}",
        "apikey": os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        "Content-Type": content_type,
    }
    try:
        requests.put(url, headers=headers, data=data, timeout=15)
    except Exception:
        pass


def _default_keyword_map() -> Dict[str, List[str]]:
    return {
        "research": ["study", "trial", "paper", "preprint", "evidence", "meta", "method", "results"],
        "policy": ["policy", "regulation", "legal", "law", "decriminal", "approval"],
        "experience": ["experience", "felt", "journey", "helped", "struggle", "story"],
        "clarification_seeker": ["confused", "clarify", "explain", "understand", "question"],
        "resource_provider": ["resource", "source", "guide", "book", "link", "reading"],
        "question_expander": ["why", "how", "what", "when", "where", "?"],
    }


def _pick_categories(text: str, available: List[str], k: int = 3, keyword_map: Optional[Dict[str, List[str]]] = None) -> List[str]:
    keyword_map = keyword_map or _default_keyword_map()
    text_l = (text or "").lower()
    hits = []
    for category, words in keyword_map.items():
        if category not in available:
            continue
        if any(w in text_l for w in words):
            hits.append(category)
    # Ensure variety
    random.shuffle(hits)
    picks = []
    for c in hits:
        if c not in picks:
            picks.append(c)
        if len(picks) >= k:
            return picks
    # Fill remaining randomly
    remaining = [c for c in available if c not in picks]
    random.shuffle(remaining)
    picks.extend(remaining[: max(0, k - len(picks))])
    return picks[:k]


def _load_templates(path: Path) -> Dict[str, List[str]]:
    return _load_json(path, {})


def _generate_replies(templates: Dict[str, List[str]], categories: List[str], bot_prefix: str = "") -> List[str]:
    replies = []
    for cat in categories:
        pool = templates.get(cat) or templates.get("default") or []
        if not pool:
            continue
        reply = random.choice(pool)
        if bot_prefix and not reply.startswith(bot_prefix):
            reply = f"{bot_prefix}{reply}"
        if reply not in replies:
            replies.append(reply)
    return replies


SAFETY_PROMPT = """You are a careful, neutral assistant generating Reddit comment drafts.
Rules:
- Do not give medical or dosing advice.
- Do not encourage illegal activity or acquisition of substances.
- Do not promote products, brands, or vendors.
- Keep replies short (2-4 sentences), respectful, and open-ended.
- Ask one thoughtful question, avoid certainty.
"""


def _llm_generate_replies(title: str, body: str, count: int = 3) -> List[str]:
    if OpenAI is None:
        return []
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return []
    base_url = os.getenv("OPENROUTER_BASE_URL", "").strip() or "https://openrouter.ai/api/v1"
    client_kwargs = {"api_key": api_key, "base_url": base_url}
    if api_key.startswith("sk-or-"):
        client_kwargs["default_headers"] = {
            "HTTP-Referer": os.getenv("OPENAI_HTTP_REFERER", "http://localhost"),
            "X-Title": os.getenv("OPENAI_X_TITLE", "Reddit_Bot"),
        }
    try:
        client = OpenAI(**client_kwargs)
    except Exception:
        return []
    prompt = (
        SAFETY_PROMPT
        + "\n\n"
        + f"Post title: {title}\n"
        + f"Post body: {body}\n"
        + f"Write {count} distinct reply drafts as a JSON array of strings."
    )
    try:
        resp = client.completions.create(
            model="gpt-3.5-turbo-instruct",
            prompt=prompt,
            max_tokens=300,
            temperature=0.5,
        )
        text = resp.choices[0].text.strip()
        # Try to parse JSON array; fallback to line split
        if text.startswith("["):
            data = json.loads(text)
            return [str(x).strip() for x in data if str(x).strip()]
        lines = [l.strip("- ").strip() for l in text.splitlines() if l.strip()]
        return [l for l in lines if l]
    except Exception:
        return []


def _init_bot(account: str, headless: bool) -> RedditAutomation:
    config = ConfigManager().load_env()
    if not hasattr(config, "selenium_settings") or not isinstance(config.selenium_settings, dict):
        config.selenium_settings = {}
    config.selenium_settings["headless"] = headless
    config.selenium_settings["cookie_file"] = f"data/cookies_{account}.pkl"
    bot = RedditAutomation(config=config)
    if not bot.setup():
        raise RuntimeError("Browser setup failed")
    if not bot.login(use_cookies_only=True):
        raise RuntimeError("Login failed")
    return bot


def _select_random_post(bot: RedditAutomation, subreddits: List[str], limit: int = 20) -> Optional[Dict]:
    posts = []
    for sub in subreddits:
        posts.extend(bot.search_posts(subreddit=sub, limit=limit, include_body=True, include_comments=False))
    posts = [p for p in posts if p.get("url") and p.get("title")]
    if not posts:
        return None
    return random.choice(posts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Engagement reply queue runner")
    parser.add_argument("--account", default="account1")
    parser.add_argument("--role", choices=["generate", "consume"], default="consume")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--post", action="store_true", help="Actually post replies (default: dry-run)")
    parser.add_argument("--queue-path", default="data/engagement_reply_queue.json")
    parser.add_argument("--supabase-prefix", default="posting")
    parser.add_argument("--subreddits", nargs="*", default=["ClinicalMicrodosingHu", "MindWellBeing"])
    parser.add_argument("--use-llm", action="store_true", help="Use LLM to draft replies (falls back to templates)")
    parser.add_argument("--force", action="store_true", help="Do not skip when queue has pending; consume or generate anyway")
    args = parser.parse_args()

    queue_path = Path(args.queue_path)
    queue_key = f"{args.supabase_prefix}/engagement_reply_queue.json"
    replied_map = _load_replied_map(args.supabase_prefix)

    # Sync queue from Supabase
    content = sb_download(queue_key)
    if content:
        try:
            queue_path.parent.mkdir(parents=True, exist_ok=True)
            queue_path.write_bytes(content)
        except Exception:
            pass

    queue = _load_json(queue_path, [])

    if args.role == "generate":
        # If pending exists and force, post one pending instead of skipping
        pending = [q for q in queue if q.get("status") == "pending"]
        if pending and args.force:
            item = pending[0]
            bot = _init_bot(args.account, args.headless)
            # Ensure no double-reply
            if item.get("post_url") in set(_load_replied_map(args.supabase_prefix).get(args.account, [])):
                queue = [q for q in queue if q.get("id") != item.get("id")]
                _save_json(queue_path, queue)
                sb_upload(queue_key, queue_path.read_bytes())
                return 0
            result = bot.reply_to_post(item["post_url"], item["reply"], dry_run=not args.post)
            logger.info("Force-consumed pending reply (dry_run=%s): %s", str(not args.post), result.get("success"))
            if result.get("success") or not args.post:
                queue = [q for q in queue if q.get("id") != item.get("id")]
                _save_json(queue_path, queue)
                sb_upload(queue_key, queue_path.read_bytes())
                if args.post and result.get("success"):
                    replied_map.setdefault(args.account, []).append(item["post_url"])
                    _save_replied_map(args.supabase_prefix, replied_map)
            return 0
        if pending:
            logger.info("Queue already has %s pending replies; skipping generation.", len(pending))
            return 0

        bot = _init_bot(args.account, args.headless)
        post = _select_random_post(bot, args.subreddits)
        if not post:
            logger.info("No posts found to generate replies.")
            return 0
        # Avoid replying to the same post twice for this account
        seen = set(replied_map.get(args.account, []))
        attempts = 0
        while post and post.get("url") in seen and attempts < 5:
            post = _select_random_post(bot, args.subreddits)
            attempts += 1
        if not post or post.get("url") in seen:
            logger.info("All candidate posts already replied to by %s; skipping.", args.account)
            return 0

        templates = _load_templates(Path("config/engagement_reply_templates.json"))
        cfg = _load_json(Path("config/engagement_program.json"), {})
        categories = list((cfg.get("comment_strategy", {}).get("types", {}) or {}).keys()) or list(templates.keys())
        keyword_map = cfg.get("keyword_map") or _default_keyword_map()
        combined_text = f"{post.get('title','')} {post.get('body','')}"
        picks = _pick_categories(combined_text, categories, k=args.count, keyword_map=keyword_map)
        replies = []
        if args.use_llm:
            replies = _llm_generate_replies(post.get("title", ""), post.get("body", ""), count=args.count)
        if not replies:
            replies = _generate_replies(templates, picks, bot_prefix=cfg.get("bot_prefix", ""))

        # Post first reply as account1
        first_reply = replies[0] if replies else None
        if first_reply:
            result = bot.reply_to_post(post["url"], first_reply, dry_run=not args.post)
            logger.info("Posted first reply (dry_run=%s): %s", str(not args.post), result.get("success"))
            if args.post and result.get("success"):
                replied_map.setdefault(args.account, []).append(post["url"])

        # Queue remaining replies
        for reply in replies[1:]:
            queue.append(
                {
                    "id": f"reply_{int(datetime.now().timestamp())}_{random.randint(1000,9999)}",
                    "post_url": post.get("url"),
                    "subreddit": post.get("subreddit"),
                    "post_title": post.get("title"),
                    "reply": reply,
                    "status": "pending",
                    "generated_by": args.account,
                    "created_at": datetime.now().isoformat(),
                }
            )
        _save_json(queue_path, queue)
        sb_upload(queue_key, queue_path.read_bytes())
        if args.post:
            _save_replied_map(args.supabase_prefix, replied_map)
        return 0

    # consume role
    pending = [q for q in queue if q.get("status") == "pending"]
    if not pending:
        logger.info("No pending replies in queue.")
        return 0
    item = pending[0]
    bot = _init_bot(args.account, args.headless)
    # Ensure this account does not reply to the same post twice
    if item.get("post_url") in set(replied_map.get(args.account, [])):
        logger.info("Already replied to this post with %s; skipping.", args.account)
        queue = [q for q in queue if q.get("id") != item.get("id")]
        _save_json(queue_path, queue)
        sb_upload(queue_key, queue_path.read_bytes())
        return 0
    result = bot.reply_to_post(item["post_url"], item["reply"], dry_run=not args.post)
    logger.info("Posted reply (dry_run=%s): %s", str(not args.post), result.get("success"))
    if result.get("success") or not args.post:
        queue = [q for q in queue if q.get("id") != item.get("id")]
        _save_json(queue_path, queue)
        sb_upload(queue_key, queue_path.read_bytes())
        if args.post and result.get("success"):
            replied_map.setdefault(args.account, []).append(item["post_url"])
            _save_replied_map(args.supabase_prefix, replied_map)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
