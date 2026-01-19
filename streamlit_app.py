#!/usr/bin/env python3
"""Streamlit UI to drive Selenium prefill (dry-run only)."""

import os
import sys
import time
import hashlib
import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import streamlit as st
import json
import requests

# Ensure project imports work when launched from elsewhere (Render, etc.)
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.config_manager import ConfigManager  # type: ignore
from shared.api_utils import matched_keywords as _match_keywords  # type: ignore
from selenium_automation.main import RedditAutomation  # type: ignore


def require_auth() -> bool:
    """Simple password gate using env STREAMLIT_APP_PASSWORD."""
    password = os.getenv("STREAMLIT_APP_PASSWORD", "").strip()
    if not password:
        return True  # no password set, allow access
    if st.session_state.get("authed"):
        return True
    entered = st.text_input("Enter access password", type="password")
    if st.button("Unlock"):
        if entered == password:
            st.session_state["authed"] = True
            st.success("Access granted.")
            return True
        st.error("Incorrect password.")
    st.stop()


@st.cache_resource
def load_config() -> ConfigManager:
    cfg = ConfigManager()
    cfg.load_env()
    return cfg


def ensure_bot(cfg: ConfigManager) -> Optional[RedditAutomation]:
    """Create or reuse a Selenium bot instance."""
    bot = st.session_state.get("bot")
    if bot:
        return bot

    bot = RedditAutomation(config=cfg)
    if not bot.setup():
        st.error("Browser setup failed. Check Chrome/driver availability.")
        return None

    # Login best-effort (may rely on saved cookies)
    if not bot.login():
        st.warning("Login might be required; ensure cookies/creds are valid.")
    else:
        try:
            cookie_path = PROJECT_ROOT / "cookies.pkl"
            bot.save_login_cookies(str(cookie_path))
            st.info(f"Cookies saved to {cookie_path}")
        except Exception:
            st.warning("Logged in, but could not save cookies.")

    st.session_state.bot = bot
    return bot


def close_bot() -> None:
    bot = st.session_state.get("bot")
    if bot:
        bot.close()
    st.session_state.bot = None


STATE_FILE = PROJECT_ROOT / "data" / "post_state.json"


def _post_key(post: dict) -> str:
    return post.get("post_key") or post.get("id") or post.get("url") or post.get("permalink") or post.get("title") or ""


def _display_reddit_url(url: str) -> str:
    if not url:
        return url
    if "old.reddit.com" in url:
        return url.replace("old.reddit.com", "www.reddit.com")
    if "://reddit.com" in url:
        return url.replace("://reddit.com", "://www.reddit.com")
    return url


def _normalize_cached_posts(posts):
    """Normalize cached post URLs to canonical reddit.com URLs."""
    if not isinstance(posts, list):
        return posts
    for post in posts:
        if not isinstance(post, dict):
            continue
        url = post.get("url")
        if url:
            post["url"] = RedditAutomation._normalize_post_url(url)
        permalink = post.get("permalink")
        if permalink:
            post["permalink"] = RedditAutomation._normalize_post_url(permalink)
    return posts


def _supabase_config() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    if not key:
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    return url, key


def _supabase_headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _fetch_supabase_posts(subreddit: str, limit: int, query: str) -> list[dict]:
    return _fetch_supabase_posts_page(subreddit, limit, query, 0, True)[0]


def _fetch_supabase_posts_page(
    subreddit: str,
    limit: int,
    query: str,
    offset: int,
    hide_used: bool,
) -> tuple[list[dict], int]:
    url, key = _supabase_config()
    if not url or not key:
        return [], 0
    table = "scanned_posts_clean" if hide_used else "scan_posts"
    base = f"{url.rstrip('/')}/rest/v1/{table}"
    params = {
        "select": "post_key,post_id,title,url,subreddit,matched_keywords,last_seen_at,scan_sort,scan_time_range,scan_page_offset",
        "order": "last_seen_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }
    if subreddit:
        if "," in subreddit:
            subs = ",".join([s.strip() for s in subreddit.split(",") if s.strip()])
            if subs:
                params["subreddit"] = f"in.({subs})"
        else:
            params["subreddit"] = f"eq.{subreddit}"
    if query:
        q = query.replace("%", "").replace("*", "")
        params["or"] = f"(title.ilike.*{q}*,url.ilike.*{q}*)"
    headers = _supabase_headers(key)
    headers["Prefer"] = "count=exact"
    resp = requests.get(base, headers=headers, params=params, timeout=20)
    if resp.status_code >= 300:
        st.warning(f"Supabase query failed ({resp.status_code}): {resp.text}")
        return [], 0
    rows = resp.json() if isinstance(resp.json(), list) else []
    total = 0
    content_range = resp.headers.get("Content-Range", "")
    if "/" in content_range:
        try:
            total = int(content_range.split("/")[-1])
        except Exception:
            total = 0
    return rows, total


def _compute_post_matches(post: dict, keywords: list[str]) -> list[str]:
    title = post.get("title") or ""
    body = post.get("body") or ""
    combined = f"{title} {body}".lower()
    return _match_keywords(combined, keywords)


def _mark_supabase_used(post_key: str, action: str) -> bool:
    url, key = _supabase_config()
    if not url or not key or not post_key:
        return False
    base = f"{url.rstrip('/')}/rest/v1/scan_posts"
    used_by = os.getenv("STREAMLIT_USER") or os.getenv("RENDER_SERVICE_NAME") or os.getenv("HOSTNAME") or "streamlit"
    payload = {
        "used_at": datetime.now(timezone.utc).isoformat(),
        "used_by": used_by,
        "used_action": action,
    }
    resp = requests.patch(
        base,
        headers=_supabase_headers(key),
        params={"post_key": f"eq.{post_key}"},
        json=payload,
        timeout=20,
    )
    if resp.status_code >= 300:
        st.warning(f"Supabase update failed ({resp.status_code}): {resp.text}")
        return False
    return True


def _context_cache() -> dict:
    return st.session_state.setdefault("post_context_cache", {})


def load_post_state() -> dict:
    if "post_state" in st.session_state:
        return st.session_state["post_state"]
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
                st.session_state["post_state"] = {
                    "submitted": set(data.get("submitted", [])),
                    "ignored": set(data.get("ignored", [])),
                    "submitted_details": data.get("submitted_details", []),
                    "ignored_details": data.get("ignored_details", []),
                }
                return st.session_state["post_state"]
        except Exception:
            pass
    st.session_state["post_state"] = {
        "submitted": set(),
        "ignored": set(),
        "submitted_details": [],
        "ignored_details": [],
    }
    return st.session_state["post_state"]


def save_post_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "submitted": sorted(state.get("submitted", [])),
        "ignored": sorted(state.get("ignored", [])),
        "submitted_details": state.get("submitted_details", []),
        "ignored_details": state.get("ignored_details", []),
    }
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def main() -> None:
    st.set_page_config(page_title="Reddit Reply Helper", layout="wide")
    st.markdown(
        """
        <style>
        @import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=Space+Grotesk:wght@500;600;700&display=swap");
        :root {
            --background: #fbf8ff;
            --foreground: #2d2142;
            --card: #ffffff;
            --card-foreground: #2d2142;
            --popover: #ffffff;
            --popover-foreground: #2d2142;
            --primary: #7b5dbe;
            --primary-foreground: #ffffff;
            --secondary: #f3eefc;
            --secondary-foreground: #2d2142;
            --muted: #f7f4ff;
            --muted-foreground: #72628d;
            --accent: #a690e6;
            --accent-foreground: #ffffff;
            --destructive: #b455d6;
            --border: #e6dcf6;
            --input: #e6dcf6;
            --ring: #d6c9ee;
            --sidebar: #f6f1ff;
            --sidebar-foreground: #2d2142;
            --sidebar-primary: #7b5dbe;
            --sidebar-primary-foreground: #ffffff;
            --sidebar-accent: #f3eefc;
            --sidebar-accent-foreground: #2d2142;
            --sidebar-border: #e2d6f4;
            --sidebar-ring: #d6c9ee;
            --shadow: 0 10px 24px rgba(74, 58, 110, 0.12);
            --radius: 18px;
        }

        html, body, [data-testid="stAppViewContainer"] {
            background: radial-gradient(1200px 600px at 12% -10%, #ffffff 0%, var(--background) 55%, #f6f0ff 100%),
                        linear-gradient(180deg, var(--background) 0%, #f7f2ff 100%);
            color: var(--foreground);
            font-family: "IBM Plex Sans", sans-serif;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, var(--sidebar), #f3efff);
            border-right: 1px solid var(--sidebar-border);
        }

        .block-container {
            padding-top: 2rem;
            max-width: 1240px;
        }

        h1, h2, h3, h4 {
            font-family: "Space Grotesk", sans-serif;
            color: var(--foreground);
            letter-spacing: -0.02em;
        }

        h1 {
            font-size: 2.8rem;
            margin-bottom: 0.35rem;
        }

        h2 {
            font-size: 1.5rem;
            margin-top: 1.8rem;
        }

        .hero {
            background: linear-gradient(120deg, #fbf9ff, #ffffff);
            border: 1px solid var(--border);
            border-radius: calc(var(--radius) + 4px);
            padding: 1.6rem 1.8rem;
            box-shadow: var(--shadow);
            animation: rise 0.6s ease-out;
        }

        .hero__badge {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.2rem 0.7rem;
            background: linear-gradient(120deg, var(--primary), var(--accent));
            color: #ffffff;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            box-shadow: 0 6px 14px rgba(123, 93, 190, 0.2);
        }

        .hero__subtitle {
            color: var(--muted-foreground);
            margin-top: 0.4rem;
            font-size: 1.02rem;
        }

        .status-row {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-weight: 600;
            color: var(--foreground);
        }

        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #8b98a7;
            box-shadow: 0 0 0 4px rgba(139, 152, 167, 0.12);
        }

        .status-dot.ok {
            background: var(--primary);
            box-shadow: 0 0 0 3px rgba(123, 93, 190, 0.18);
        }

        div[data-testid="stForm"], div[data-testid="stExpander"] {
            background: linear-gradient(180deg, #ffffff 0%, #f8f4ff 100%);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 0.7rem 0.9rem;
            box-shadow: 0 10px 22px rgba(74, 58, 110, 0.12);
        }

        div.stButton > button {
            background: linear-gradient(120deg, var(--primary), var(--accent));
            color: var(--primary-foreground);
            border: none;
            border-radius: 10px;
            padding: 0.4rem 0.9rem;
            font-weight: 600;
            font-size: 0.85rem;
            letter-spacing: 0.01em;
            transition: transform 0.15s ease, box-shadow 0.2s ease, filter 0.2s ease;
            box-shadow: 0 8px 16px rgba(123, 93, 190, 0.18);
        }

        div.stButton > button,
        div.stButton > button * {
            color: #ffffff !important;
        }

        div.stButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 12px 22px rgba(123, 93, 190, 0.22);
            filter: brightness(1.02);
        }

        div.stButton > button:active {
            transform: translateY(0);
            box-shadow: 0 5px 10px rgba(123, 93, 190, 0.2);
        }

        input, textarea {
            border-radius: 12px !important;
        }

        input[type="checkbox"],
        input[type="radio"],
        input[type="range"] {
            accent-color: var(--primary) !important;
        }

        div[data-baseweb="checkbox"] input:checked + div,
        span[data-baseweb="checkbox"] input:checked + div {
            background: var(--primary) !important;
            border-color: var(--primary) !important;
        }

        div[data-testid="stCheckbox"] div[role="checkbox"],
        div[data-baseweb="checkbox"] div[role="checkbox"],
        span[data-baseweb="checkbox"] div[role="checkbox"] {
            border-color: var(--border) !important;
            background-color: #ffffff !important;
        }

        div[data-testid="stCheckbox"] div[role="checkbox"][aria-checked="true"],
        div[data-baseweb="checkbox"] div[role="checkbox"][aria-checked="true"],
        span[data-baseweb="checkbox"] div[role="checkbox"][aria-checked="true"] {
            background: var(--primary) !important;
            border-color: var(--primary) !important;
        }

        div[data-baseweb="checkbox"] svg,
        div[data-baseweb="checkbox"] svg path,
        span[data-baseweb="checkbox"] svg,
        span[data-baseweb="checkbox"] svg path,
        div[data-testid="stCheckbox"] svg,
        div[data-testid="stCheckbox"] svg path {
            color: #fff !important;
            fill: #fff !important;
        }

        div[data-baseweb="radio"] input:checked + div {
            border-color: var(--primary) !important;
        }

        div[data-testid="stRadio"] div[role="radio"][aria-checked="true"] {
            border-color: var(--primary) !important;
        }

        div[data-testid="stRadio"] div[role="radio"] svg {
            color: var(--primary) !important;
            fill: var(--primary) !important;
        }

        div[data-baseweb="radio"] svg {
            color: var(--primary) !important;
            fill: var(--primary) !important;
        }

        div[data-baseweb="toggle"] input:checked + div,
        span[data-baseweb="toggle"] input:checked + div {
            background-color: var(--primary) !important;
            border-color: var(--primary) !important;
        }

        div[data-testid="stToggle"] div[role="switch"][aria-checked="true"],
        div[data-baseweb="toggle"] div[role="switch"][aria-checked="true"],
        span[data-baseweb="toggle"] div[role="switch"][aria-checked="true"] {
            background-color: var(--primary) !important;
            border-color: var(--primary) !important;
        }

        div[data-testid="stToggle"] div[role="switch"],
        div[data-baseweb="toggle"] div[role="switch"],
        span[data-baseweb="toggle"] div[role="switch"] {
            border-color: var(--border) !important;
            background-color: var(--border) !important;
        }

        div[data-testid="stToggle"] div[role="switch"] > div,
        div[data-baseweb="toggle"] div[role="switch"] > div,
        span[data-baseweb="toggle"] div[role="switch"] > div {
            background-color: #ffffff !important;
        }

        div[data-baseweb="tag"],
        span[data-baseweb="tag"] {
            background: linear-gradient(120deg, var(--primary), var(--accent)) !important;
            background-color: var(--primary) !important;
            color: #fff !important;
            border: none !important;
            border-radius: 999px !important;
            box-shadow: 0 6px 12px rgba(123, 93, 190, 0.18);
        }

        div[data-baseweb="tag"] span,
        div[data-baseweb="tag"] svg,
        div[data-baseweb="tag"] svg path,
        span[data-baseweb="tag"] span,
        span[data-baseweb="tag"] svg,
        span[data-baseweb="tag"] svg path {
            color: #fff !important;
            fill: #fff !important;
        }

        div[data-baseweb="tag"] span,
        div[data-baseweb="tag"] span *,
        span[data-baseweb="tag"] span,
        span[data-baseweb="tag"] span * {
            color: #fff !important;
        }

        div[data-testid="stAlert"] {
            background: var(--muted);
            border: 1px solid var(--border);
            border-left: 4px solid var(--primary);
            color: var(--foreground);
        }

        div[data-testid="stAlert"] svg {
            color: var(--primary);
        }

        div[data-baseweb="input"] input,
        div[data-baseweb="textarea"] textarea,
        div[data-baseweb="select"] > div {
            background: var(--card);
            border: 1px solid var(--input);
            border-radius: 12px;
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.7);
        }

        .stCaption,
        .stCaption span {
            color: var(--muted-foreground) !important;
        }

        /* Radio pills for "Post source" */
        div[data-testid="stRadio"] > div[role="radiogroup"] {
            display: inline-flex;
            flex-wrap: nowrap;
            gap: 0.4rem;
            white-space: nowrap;
        }

        div[data-testid="stRadio"] div[role="radio"] {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 999px;
            padding: 0.3rem 0.9rem;
            color: var(--foreground);
            font-weight: 600;
        }

        div[data-testid="stRadio"] div[role="radio"] svg {
            display: none;
        }

        div[data-testid="stRadio"] div[role="radio"][aria-checked="true"] {
            background: linear-gradient(120deg, var(--primary), var(--accent));
            border-color: transparent;
            color: var(--primary-foreground);
            box-shadow: 0 6px 14px rgba(123, 93, 190, 0.18);
        }

        div[data-testid="stRadio"] div[role="radio"][aria-checked="true"] *,
        div[data-testid="stRadio"] div[role="radio"][aria-checked="true"] span {
            color: var(--primary-foreground) !important;
            fill: var(--primary-foreground) !important;
        }

        /* Sidebar radio group styled like the "All customers / Idle customers" pills */
        section[data-testid="stSidebar"] div[data-testid="stRadio"] > div[role="radiogroup"] {
            display: inline-flex;
            flex-direction: row;
            flex-wrap: nowrap;
            gap: 0.4rem;
            padding: 0.35rem 0.4rem;
            border: 1px solid var(--border);
            border-radius: 16px;
            background: rgba(255, 255, 255, 0.9);
            box-shadow: 0 6px 14px rgba(74, 58, 110, 0.1);
        }

        section[data-testid="stSidebar"] label[data-baseweb="radio"] {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 10px;
            padding: 0.25rem 0.8rem;
            font-weight: 600;
            font-size: 0.85rem;
            color: var(--primary) !important;
            background: transparent;
            margin: 0 !important;
            width: auto !important;
        }

        section[data-testid="stSidebar"] label[data-baseweb="radio"] > div:first-child {
            display: none;
        }

        section[data-testid="stSidebar"] label[data-baseweb="radio"]:hover {
            background: var(--secondary);
        }

        @supports selector(:has(*)) {
            section[data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) {
                background: var(--primary);
                color: #ffffff !important;
                box-shadow: 0 6px 14px rgba(123, 93, 190, 0.2);
            }
        }

        section[data-testid="stSidebar"] label[data-baseweb="radio"] input:checked + div,
        section[data-testid="stSidebar"] label[data-baseweb="radio"] input:checked ~ div {
            background: var(--primary) !important;
            color: #ffffff !important;
            border-radius: 10px;
            padding: 0.25rem 0.8rem;
            box-shadow: 0 6px 14px rgba(123, 93, 190, 0.2);
        }

        section[data-testid="stSidebar"] label[data-baseweb="radio"] input:checked ~ div,
        section[data-testid="stSidebar"] label[data-baseweb="radio"] input:checked ~ div * {
            color: #ffffff !important;
            fill: #ffffff !important;
        }

        section[data-testid="stSidebar"] > div {
            background: var(--sidebar);
            border-right: 1px solid var(--sidebar-border);
        }

        section[data-testid="stSidebar"] .stMarkdown,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] p {
            color: var(--sidebar-foreground);
        }

        .url-bar {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            background: linear-gradient(180deg, #ffffff 0%, #f6f2ff 100%);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 0.2rem 0.5rem;
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.4);
        }

        .url-text {
            flex: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
            font-size: 0.85rem;
            color: var(--foreground);
            padding: 0.35rem 0.5rem;
            border-radius: 8px;
            background: transparent;
        }

        .url-open {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 34px;
            height: 34px;
            border-radius: 999px;
            background: linear-gradient(120deg, var(--primary), var(--accent));
            color: var(--primary-foreground) !important;
            text-decoration: none !important;
            font-size: 0.85rem;
            box-shadow: 0 8px 16px rgba(123, 93, 190, 0.22);
            border: none;
            transition: transform 0.15s ease, box-shadow 0.2s ease;
        }

        .url-open:hover {
            transform: translateY(-1px);
            box-shadow: 0 10px 20px rgba(123, 93, 190, 0.26);
        }



        .post-title {
            font-weight: 600;
            color: var(--foreground);
            margin-bottom: 0.4rem;
            font-size: 1.05rem;
            line-height: 1.4;
        }

        .post-sub {
            color: var(--muted-foreground);
            font-weight: 500;
        }

        .post-tags {
            color: var(--muted-foreground);
            font-size: 0.85rem;
            margin-bottom: 0.6rem;
        }
        
        hr {
            border: none;
            height: 1px;
            background: linear-gradient(90deg, rgba(123, 93, 190, 0.0), rgba(123, 93, 190, 0.28), rgba(123, 93, 190, 0.0));
        }

        div[data-testid="stExpander"] > details > summary {
            font-weight: 600;
            color: var(--foreground);
        }

        div[data-testid="stExpander"] > details[open] > summary {
            color: var(--primary);
        }

        @keyframes rise {
            from { opacity: 0; transform: translateY(12px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @media (max-width: 900px) {
            .block-container { padding-top: 1.4rem; }
            h1 { font-size: 2.2rem; }
            .hero { padding: 1.3rem 1.4rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="hero">
            <span class="hero__badge">Selenium workspace</span>
            <h1>Reddit Reply Helper</h1>
            <div class="hero__subtitle">Search -> draft -> fill (optional auto-submit). Keep runs short to avoid session timeouts.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not require_auth():
        return

    cfg = load_config()
    post_state = load_post_state()
    auto_submit_limit = cfg.bot_settings.get("auto_submit_limit", 0)
    search_cache_ttl = int(os.getenv("SEARCH_CACHE_TTL", "0") or 0)
    keyword_list = cfg.bot_settings.get("keywords") or cfg.default_keywords
    available_subs = cfg.bot_settings.get("subreddits") or cfg.default_subreddits
    st.session_state.setdefault("auto_submit_count", 0)
    st.session_state.setdefault("last_action", "")
    st.session_state.setdefault("error_count", 0)
    st.session_state.setdefault("auto_submit_guard", {})
    st.session_state.setdefault("page_index", 0)
    st.session_state.setdefault("post_filter", "")

    with st.sidebar:
        st.subheader("Source")
        data_source = st.radio(
            "Post source",
            ["Live scan", "Database"],
            index=0,
            label_visibility="collapsed",
        )
        hide_used = False
        page_size_key = "page_size_db" if data_source == "Database" else "page_size_live"
        sort_choice_key = "sort_choice_db" if data_source == "Database" else "sort_choice_live"
        page_size = st.selectbox(
            "Page size",
            [10, 25, 50],
            index=0,
            key=page_size_key,
        )
        sort_choice = st.selectbox(
            "Sort",
            ["Newest", "Oldest", "Subreddit"],
            index=0,
            key=sort_choice_key,
        )

        st.subheader("Browser")
        bot_active = bool(st.session_state.get("bot"))
        bot = st.session_state.get("bot")
        driver_alive = bool(getattr(bot, "driver", None) and getattr(getattr(bot, "driver", None), "session_id", None))
        status_text = "Ready" if bot_active else "Not started"
        status_class = "ok" if bot_active else ""
        st.markdown(
            f"<div class='status-row'><span class='status-dot {status_class}'></span>{status_text}</div>",
            unsafe_allow_html=True,
        )
        if driver_alive:
            current_url = getattr(getattr(bot, "driver", None), "current_url", "") or ""
            display_current_url = _display_reddit_url(current_url)
            st.caption(
                f"Driver alive • {display_current_url[:40] + '...' if len(display_current_url) > 43 else display_current_url}"
            )
        else:
            st.caption("Driver: not started")
        if st.button("Start / Reconnect"):
            if ensure_bot(cfg):
                st.success("Browser ready.")
        if st.button("Close"):
            close_bot()
            st.info("Browser closed.")
        if st.button("Clear search cache"):
            for key in list(st.session_state.keys()):
                if key.startswith(
                    (
                        "search_cache_",
                        "last_posts_",
                        "page_index_",
                        "post_filter_",
                    )
                ):
                    st.session_state.pop(key, None)
            st.session_state.pop("last_posts", None)
            st.session_state.pop("post_context_cache", None)
            st.session_state.pop("post_filter", None)
            st.session_state.pop("page_index", None)
            st.info("Search cache cleared.")
        if auto_submit_limit:
            st.caption(f"Auto-submit used: {st.session_state['auto_submit_count']}/{auto_submit_limit}")
        if st.session_state.get("last_action"):
            st.caption(f"Last action: {st.session_state['last_action']}")
        if st.session_state.get("error_count"):
            st.caption(f"Errors: {st.session_state['error_count']}")
        if data_source == "Database":
            sb_url, sb_key = _supabase_config()
            if sb_url and sb_key:
                st.caption("Supabase: connected")
            else:
                st.warning("Supabase not configured. Set SUPABASE_URL + SUPABASE_ANON_KEY.")

    if st.session_state.get("last_data_source") != data_source:
        prev_source = st.session_state.get("last_data_source")
        if prev_source:
            st.session_state[f"last_posts_{prev_source}"] = st.session_state.get("last_posts", [])
            st.session_state[f"page_index_{prev_source}"] = st.session_state.get("page_index", 0)
            st.session_state[f"post_filter_{prev_source}"] = st.session_state.get("post_filter", "")
        st.session_state["last_data_source"] = data_source
        st.session_state["last_posts"] = st.session_state.get(f"last_posts_{data_source}", [])
        st.session_state["page_index"] = st.session_state.get(f"page_index_{data_source}", 0)
        st.session_state["post_filter"] = st.session_state.get(f"post_filter_{data_source}", "")

    st.subheader("Find Posts")
    if data_source == "Database":
        selected_subs = st.multiselect(
            "Subreddits",
            options=available_subs,
            default=available_subs[:2] if available_subs else [],
        )
        subreddit = ",".join(selected_subs)
    else:
        subreddit = st.text_input("Subreddit", value="microdosing", help="Name without r/")
    limit = st.number_input("How many posts?", min_value=1, max_value=100, value=10, step=5)
    query_text = st.text_input(
        "Filter results",
        key="post_filter",
        placeholder="Filter by title, URL, or keywords",
    )
    st.session_state[f"post_filter_{data_source}"] = st.session_state.get("post_filter", "")

    search_left, search_right = st.columns([1, 6])
    with search_left:
        submitted_search = st.button("Search", use_container_width=True)
    with search_right:
        pager_slot = st.empty()
    if submitted_search:
        st.session_state["page_index"] = 0
        st.session_state[f"page_index_{data_source}"] = 0
        requested = int(limit)
        cache_key = f"search_cache_{data_source}_{subreddit.strip().lower()}_{requested}_{hide_used}"
        cached = st.session_state.get(cache_key)
        if cached and search_cache_ttl > 0 and (time.time() - cached.get("ts", 0)) < search_cache_ttl:
            posts = _normalize_cached_posts(cached.get("posts", []))
            cached["posts"] = posts
            st.session_state[cache_key] = cached
        else:
            if data_source == "Database":
                st.caption("Loading posts from Supabase...")
                posts, total = _fetch_supabase_posts_page(
                    subreddit.strip().lower(),
                    requested,
                    "",
                    0,
                    hide_used,
                )
                for post in posts:
                    post["id"] = post.get("post_id", "")
                posts = _normalize_cached_posts(posts)
            else:
                bot = ensure_bot(cfg)
                if not bot:
                    posts = []
                    total = 0
                else:
                    st.caption(f"Searching r/{subreddit}...")
                    fetch_limit = requested
                    posts = bot.search_posts(
                        subreddit=subreddit.strip() or None,
                        limit=fetch_limit,
                        include_body=False,
                        include_comments=False,
                    )
                    posts = _normalize_cached_posts(posts)
                    total = len(posts)
            st.session_state[cache_key] = {"ts": time.time(), "posts": posts, "total": total}
        st.session_state["last_posts"] = posts
        st.session_state[f"last_posts_{data_source}"] = posts
    posts = _normalize_cached_posts(st.session_state.get("last_posts", []))
    st.session_state["last_posts"] = posts
    if posts:
        filtered_posts = []
        seen = set()
        query_lower = (query_text or "").strip().lower()
        for p in posts:
            key = _post_key(p)
            dedupe_key = key or p.get("title", "")
            if dedupe_key in seen:
                continue
            if data_source == "Live scan":
                p["matched_keywords"] = p.get("matched_keywords") or _compute_post_matches(p, keyword_list)
            if query_lower:
                title_val = (p.get("title") or "").lower()
                url_val = (p.get("url") or "").lower()
                keywords_val = " ".join(p.get("matched_keywords") or [])
                if query_lower not in title_val and query_lower not in url_val and query_lower not in keywords_val:
                    continue
            seen.add(dedupe_key)
            filtered_posts.append(p)
        if sort_choice == "Subreddit":
            filtered_posts.sort(key=lambda row: (row.get("subreddit") or "", row.get("title") or ""))
        elif sort_choice == "Oldest":
            filtered_posts.sort(key=lambda row: row.get("last_seen_at") or "")
        else:
            filtered_posts.sort(key=lambda row: row.get("last_seen_at") or "", reverse=True)

        total_filtered = len(filtered_posts)
        page_index = st.session_state.get("page_index", 0)
        start = page_index * page_size
        end = start + page_size
        posts = filtered_posts[start:end]
        total_pages = max(1, (total_filtered + page_size - 1) // page_size)
        if total_pages > 1:
            with pager_slot.container():
                _, col_prev, col_page, col_next = st.columns([6, 1.2, 1, 1.2], gap="small")
                with col_prev:
                    if st.button("Prev", disabled=page_index <= 0, use_container_width=True):
                        st.session_state["page_index"] = max(0, page_index - 1)
                        st.session_state[f"page_index_{data_source}"] = st.session_state["page_index"]
                        st.rerun()
                with col_page:
                    st.caption(f"Page {page_index + 1} of {total_pages}")
                with col_next:
                    if st.button("Next", disabled=(page_index + 1) >= total_pages, use_container_width=True):
                        st.session_state["page_index"] = min(total_pages - 1, page_index + 1)
                        st.session_state[f"page_index_{data_source}"] = st.session_state["page_index"]
                        st.rerun()
        st.subheader("Pick a Post")
        for idx, post in enumerate(posts, 1):
            title = post.get("title") or "No title"
            url = post.get("url") or post.get("permalink") or ""
            post_key = _post_key(post)
            status_key = f"post_status_{post_key}"
            if not url:
                pid = post.get("id")
                sub = post.get("subreddit")
                if pid and sub:
                    url = f"https://old.reddit.com/r/{sub}/comments/{pid}/"
            subreddit = post.get("subreddit", "")
            matched = post.get("matched_keywords") or []
            match_label = ", ".join(matched) if isinstance(matched, list) else ""
            title_safe = html.escape(title)
            sub_safe = html.escape(subreddit)
            st.markdown("<div class='post-card'>", unsafe_allow_html=True)
            st.markdown(
                f"<div class='post-title'>{idx}. {title_safe} <span class='post-sub'>(r/{sub_safe})</span></div>",
                unsafe_allow_html=True,
            )
            if match_label:
                st.markdown(
                    f"<div class='post-tags'>Keywords: {html.escape(match_label)}</div>",
                    unsafe_allow_html=True,
                )
            if url:
                display_url = _display_reddit_url(url)
                st.markdown(
                    f"""
                    <div class="url-bar">
                        <div class="url-text">{html.escape(display_url)}</div>
                        <a class="url-open" href="{html.escape(display_url)}" target="_blank" rel="noopener">↗</a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.caption("No link available for this post.")
            if url:
                with st.expander(f"Reply options #{idx}", expanded=False):
                    with st.form(f"inline_prefill_form_{idx}", clear_on_submit=False):
                        st.markdown("Write your reply")
                        use_page_context_inline = st.checkbox(
                            "Use page title/body as context",
                            value=True,
                            key=f"use_ctx_{post_key}",
                        )
                        llm_generated = st.session_state.get(f"llm_reply_{post_key}", "")
                        manual_context_val = st.session_state.get(f"manual_ctx_val_{post_key}", "")

                        if llm_generated:
                            edit_key = f"llm_edit_{post_key}"
                            if edit_key not in st.session_state:
                                st.session_state[edit_key] = llm_generated
                            generated_reply = st.text_area(
                                "Generated reply (editable)",
                                key=edit_key,
                            )
                            auto_submit = st.checkbox(
                                "Auto-submit (posts now)",
                                value=False,
                                key=f"auto_submit_{post_key}",
                            )
                            pad_btn_l, col_btn1, col_btn2, pad_btn_r = st.columns([0.1, 2, 2, 5], gap="small")
                            with col_btn1:
                                gen_llm = st.form_submit_button("Generate with LLM")
                            with col_btn2:
                                submitted_inline = st.form_submit_button("Prefill / Submit")
                            manual_context_inline = manual_context_val  # keep last context for regen
                            manual_reply_inline = ""  # not used in this view
                        else:
                            manual_context_inline = st.text_area(
                                "Manual context (optional)",
                                key=f"manual_ctx_{post_key}",
                                placeholder="Provide a brief prompt/context for the reply.",
                                value=manual_context_val,
                            )
                            manual_reply_inline = st.text_area(
                                "Reply text (edit or paste here)",
                                key=f"manual_reply_{post_key}",
                                placeholder="Enter reply text to prefill",
                                value="",
                            )
                            auto_submit = st.checkbox(
                                "Auto-submit (posts now)",
                                value=False,
                                key=f"auto_submit_{post_key}",
                            )
                            pad_btn_l, col_btn1, col_btn2, pad_btn_r = st.columns([0.1, 2, 2, 5], gap="small")
                            with col_btn1:
                                gen_llm = st.form_submit_button("Generate with LLM")
                            with col_btn2:
                                submitted_inline = st.form_submit_button("Prefill / Submit")

                    if submitted_inline:
                        bot = ensure_bot(cfg)
                        if not bot:
                            st.stop()
                        reply_text = (
                            st.session_state.get(f"llm_edit_{post_key}", "").strip()
                            if llm_generated
                            else manual_reply_inline.strip()
                        )
                        if not reply_text:
                            st.error("No reply text available. Enter a manual reply or enable LLM.")
                        else:
                            if auto_submit and auto_submit_limit > 0 and st.session_state["auto_submit_count"] >= auto_submit_limit:
                                auto_submit = False
                                st.session_state[status_key] = ("warning", "Auto-submit limit reached; prefilling only.")
                            if auto_submit:
                                guard_window = float(os.getenv("AUTO_SUBMIT_GUARD_SECONDS", "20") or 20)
                                reply_hash = hashlib.sha256(reply_text.encode("utf-8")).hexdigest()
                                guard = st.session_state.get("auto_submit_guard", {})
                                guard_entry = guard.get(post_key, {})
                                last_ts = float(guard_entry.get("ts", 0.0) or 0.0)
                                if guard_entry.get("hash") == reply_hash and (time.time() - last_ts) < guard_window:
                                    auto_submit = False
                                    st.session_state[status_key] = ("warning", "Auto-submit throttled; prefilling only.")
                                else:
                                    guard[post_key] = {"hash": reply_hash, "ts": time.time()}
                                    st.session_state["auto_submit_guard"] = guard
                            result = bot.reply_to_post(url, reply_text, dry_run=not auto_submit)
                            if result.get("success"):
                                submitted_flag = result.get("submitted")
                                if auto_submit:
                                    if submitted_flag:
                                        st.session_state[status_key] = ("success", "Auto-submit attempted. Check the thread to confirm it posted.")
                                    else:
                                        st.session_state[status_key] = ("warning", "Filled the comment box but could not confirm submit. Please verify in the browser.")
                                else:
                                    st.session_state[status_key] = ("success", "Prefill attempted. Review the browser window and submit manually.")
                                if submitted_flag:
                                    post_state["submitted"].add(post_key)
                                    post_state["submitted_details"].append(
                                        {
                                            "key": post_key,
                                            "title": post.get("title") or post.get("url") or "Untitled",
                                            "reply": reply_text,
                                            "subreddit": post.get("subreddit", ""),
                                        }
                                    )
                                    save_post_state(post_state)
                                    if auto_submit:
                                        st.session_state["auto_submit_count"] += 1
                                st.session_state["last_action"] = f"prefill {post_key}"
                            else:
                                if auto_submit:
                                    guard = st.session_state.get("auto_submit_guard", {})
                                    guard.pop(post_key, None)
                                    st.session_state["auto_submit_guard"] = guard
                                st.session_state[status_key] = ("error", f"Failed to prefill: {result.get('error', 'unknown error')}")
                                st.session_state["error_count"] += 1
                                st.session_state["last_action"] = f"prefill_failed {post_key}"
                            st.rerun()
                    if 'bot' not in locals():
                        bot = None
                    if gen_llm:
                        bot = bot or ensure_bot(cfg)
                        if not bot:
                            st.stop()
                        bot.use_llm = True
                        context = ""
                        if use_page_context_inline:
                            cache = _context_cache()
                            context = cache.get(post_key, "")
                            if not context:
                                st.info("Fetching post context...")
                                context = bot.fetch_post_context(url) or ""
                                if context:
                                    cache[post_key] = context
                        if not context:
                            context = manual_context_inline.strip() or "Provide a concise, supportive, safe reply."
                        gen_status = st.empty()
                        gen_status.info("Generating reply via OpenRouter...")
                        llm_text = bot.generate_llm_reply(context)
                        if llm_text:
                            st.session_state[f"llm_reply_{post_key}"] = llm_text
                            st.session_state[f"manual_ctx_val_{post_key}"] = manual_context_inline
                            st.session_state[f"llm_edit_{post_key}"] = llm_text
                            st.rerun()
                        else:
                            gen_status.warning("LLM generation unavailable; please enter a manual reply.")

            pad_left, col_a, col_b, pad_right = st.columns([0.1, 2, 2, 3], gap="small")
            mark_clicked = col_a.button("Mark submitted", key=f"mark_submit_{post_key}")
            ignore_clicked = col_b.button("Ignore this post", key=f"ignore_post_{post_key}")

            if mark_clicked and post_key not in post_state["submitted"]:
                post_state["submitted"].add(post_key)
                existing_keys_sub = {d.get("key") for d in post_state.get("submitted_details", [])}
                if post_key not in existing_keys_sub:
                    post_state["submitted_details"].append(
                        {
                            "key": post_key,
                            "title": post.get("title") or post.get("url") or "Untitled",
                            "reply": st.session_state.get(f"llm_edit_{post_key}", "").strip() if llm_generated else "",
                            "subreddit": post.get("subreddit", ""),
                        }
                    )
                # Clear per-post session state so UI resets on rerun
                st.session_state.pop(f"llm_reply_{post_key}", None)
                st.session_state.pop(f"manual_ctx_val_{post_key}", None)
                st.session_state.pop(f"llm_edit_{post_key}", None)
                st.session_state.pop(f"post_status_{post_key}", None)
                save_post_state(post_state)
                if data_source == "Database":
                    _mark_supabase_used(post_key, "submitted")
                st.caption("Marked as submitted.")
                st.session_state["last_action"] = f"mark_submitted {post_key}"
                st.rerun()

            if ignore_clicked and post_key not in post_state["ignored"]:
                post_state["ignored"].add(post_key)
                existing_keys = {d.get("key") for d in post_state.get("ignored_details", [])}
                if post_key not in existing_keys:
                    post_state["ignored_details"].append(
                        {
                            "key": post_key,
                            "title": post.get("title") or post.get("url") or "Untitled",
                            "subreddit": post.get("subreddit", ""),
                        }
                    )
                save_post_state(post_state)
                if data_source == "Database":
                    _mark_supabase_used(post_key, "ignored")
                st.caption("Post ignored.")
                st.session_state["last_action"] = f"ignore {post_key}"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    # Show ignored posts for current subreddit
    current_sub = subreddit.strip() if 'subreddit' in locals() else ""
    ignored_list = []
    ignored_details = []
    submitted_details = []
    if current_sub:
        for p in st.session_state.get("last_posts", []):
            key = _post_key(p)
            if key in post_state["ignored"] and p.get("subreddit", "") == current_sub:
                ignored_list.append(p)
        submitted_details = [
            d for d in post_state.get("submitted_details", []) if d.get("subreddit", "") == current_sub
        ]
        ignored_details = [
            d for d in post_state.get("ignored_details", []) if d.get("subreddit", "") == current_sub
        ]
    if submitted_details or ignored_details:
        st.markdown("---")
        st.subheader("Saved activity")
        if submitted_details:
            with st.expander(f"Submitted posts in r/{current_sub}", expanded=False):
                for idx, d in enumerate(list(submitted_details)):
                    title = d.get("title") or "Untitled"
                    key_val = d.get("key", title)
                    chk_key = f"submitted_item_{current_sub}_{idx}_{key_val}"
                    checked = st.checkbox(title, value=True, key=chk_key)
                    if not checked:
                        post_state["submitted"].discard(key_val)
                        post_state["submitted_details"] = [
                            x for x in post_state.get("submitted_details", []) if x.get("key") != key_val
                        ]
                        save_post_state(post_state)
                        st.success("Post unmarked as submitted. It will show up on next search.")
                        st.session_state["last_action"] = f"unmark_submitted {key_val}"
                        st.rerun()
                    reply_text = d.get("reply", "")
                    if reply_text:
                        st.code(reply_text)
        with st.expander(f"Ignored posts in r/{current_sub}", expanded=False):
            entries = ignored_details
            if entries:
                for idx, d in enumerate(list(entries)):
                    title = d.get("title") or "Untitled"
                    key_val = d.get("key", title)
                    chk_key = f"ignored_item_{current_sub}_{idx}_{key_val}"
                    checked = st.checkbox(title, value=True, key=chk_key)
                    if not checked:
                        post_state["ignored"].discard(key_val)
                        post_state["ignored_details"] = [
                            x for x in post_state.get("ignored_details", []) if x.get("key") != key_val
                        ]
                        save_post_state(post_state)
                        st.success("Post unignored. It will show up on next search.")
                        st.session_state["last_action"] = f"unignore {key_val}"
                        st.rerun()
            else:
                st.caption("No ignored posts yet.")
    # Prefill reply UI is now inline under each post above


if __name__ == "__main__":
    main()
