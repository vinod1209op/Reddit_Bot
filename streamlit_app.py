#!/usr/bin/env python3
"""Streamlit UI to drive Selenium prefill (dry-run only)."""

import os
import sys
import time
import hashlib
from pathlib import Path
from typing import Optional

import streamlit as st
import json

# Ensure project imports work when launched from elsewhere (Render, etc.)
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.config_manager import ConfigManager  # type: ignore
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
    return post.get("id") or post.get("url") or post.get("permalink") or post.get("title") or ""

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
        @import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap");
        :root {
            --bg-1: #f4f1ea;
            --bg-2: #e7f2ee;
            --ink-1: #1e2a35;
            --ink-2: #4b5b6b;
            --accent: #1f8a70;
            --accent-2: #f2a154;
            --card: rgba(255, 255, 255, 0.9);
            --border: rgba(30, 42, 53, 0.08);
            --shadow: 0 10px 30px rgba(30, 42, 53, 0.08);
            --radius: 18px;
        }

        html, body, [data-testid="stAppViewContainer"] {
            background: radial-gradient(1200px 600px at 10% -10%, #ffffff 0%, var(--bg-1) 40%, var(--bg-2) 100%);
            color: var(--ink-1);
            font-family: "IBM Plex Sans", sans-serif;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(245, 242, 236, 0.95));
            border-right: 1px solid var(--border);
        }

        .block-container {
            padding-top: 2.2rem;
            max-width: 1200px;
        }

        h1, h2, h3, h4 {
            font-family: "Space Grotesk", sans-serif;
            color: var(--ink-1);
            letter-spacing: -0.02em;
        }

        h1 {
            font-size: 2.7rem;
            margin-bottom: 0.4rem;
        }

        h2 {
            font-size: 1.4rem;
            margin-top: 2rem;
        }

        .hero {
            background: linear-gradient(120deg, rgba(31, 138, 112, 0.12), rgba(242, 161, 84, 0.14));
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
            background: rgba(31, 138, 112, 0.12);
            color: var(--accent);
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .hero__subtitle {
            color: var(--ink-2);
            margin-top: 0.4rem;
            font-size: 1rem;
        }

        .status-row {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-weight: 600;
            color: var(--ink-1);
        }

        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #8b98a7;
            box-shadow: 0 0 0 4px rgba(139, 152, 167, 0.12);
        }

        .status-dot.ok {
            background: #31b072;
            box-shadow: 0 0 0 4px rgba(49, 176, 114, 0.18);
        }

        .card-surface {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 1.2rem;
            box-shadow: var(--shadow);
            animation: fadeIn 0.6s ease-out;
        }

        div[data-testid="stForm"], div[data-testid="stExpander"] {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 0.6rem 0.8rem;
            box-shadow: var(--shadow);
        }

        div.stButton > button {
            background: linear-gradient(120deg, var(--accent), #2aa385);
            color: #fff;
            border: none;
            border-radius: 12px;
            padding: 0.45rem 1rem;
            font-weight: 600;
            transition: transform 0.15s ease, box-shadow 0.2s ease;
            box-shadow: 0 6px 14px rgba(31, 138, 112, 0.2);
        }

        div.stButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 10px 18px rgba(31, 138, 112, 0.25);
        }

        input, textarea {
            border-radius: 12px !important;
        }

        div[data-baseweb="input"] input,
        div[data-baseweb="textarea"] textarea,
        div[data-baseweb="select"] > div {
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid var(--border);
        }

        hr {
            border: none;
            height: 1px;
            background: linear-gradient(90deg, rgba(31,138,112,0.0), rgba(31,138,112,0.35), rgba(31,138,112,0.0));
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
            h1 { font-size: 2.1rem; }
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
    st.session_state.setdefault("auto_submit_count", 0)
    st.session_state.setdefault("last_action", "")
    st.session_state.setdefault("error_count", 0)
    st.session_state.setdefault("auto_submit_guard", {})

    with st.sidebar:
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
            st.caption(f"Driver alive • {current_url[:40] + '...' if len(current_url) > 43 else current_url}")
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
                if key.startswith("search_cache_"):
                    st.session_state.pop(key, None)
            st.session_state.pop("last_posts", None)
            st.session_state.pop("last_posts_fetched_count", None)
            st.session_state.pop("last_requested_limit", None)
            st.session_state.pop("post_context_cache", None)
            st.info("Search cache cleared.")
        if auto_submit_limit:
            st.caption(f"Auto-submit used: {st.session_state['auto_submit_count']}/{auto_submit_limit}")
        if st.session_state.get("last_action"):
            st.caption(f"Last action: {st.session_state['last_action']}")
        if st.session_state.get("error_count"):
            st.caption(f"Errors: {st.session_state['error_count']}")
        st.subheader("Tips")
        st.markdown(
            "- Start browser, then search.\n"
            "- Edit or generate a reply.\n"
            "- Prefill keeps it manual; Auto-submit posts immediately.\n"
            "- Mark submitted/ignored to hide later."
        )
        st.caption("LLM uses OpenRouter when `OPENROUTER_API_KEY` is set.")

    st.subheader("Find Posts")
    with st.form("search_form", clear_on_submit=False):
        subreddit = st.text_input("Subreddit", value="microdosing", help="Name without r/")
        limit = st.number_input("How many posts?", min_value=1, max_value=50, value=10, step=1)
        submitted_search = st.form_submit_button("Search")
    if submitted_search:
        bot = ensure_bot(cfg)
        if bot:
            requested = int(limit)
            cache_key = f"search_cache_{subreddit.strip().lower()}_{requested}"
            cached = st.session_state.get(cache_key)
            if cached and search_cache_ttl > 0 and (time.time() - cached.get("ts", 0)) < search_cache_ttl:
                posts = _normalize_cached_posts(cached.get("posts", []))
                cached["posts"] = posts
                st.session_state[cache_key] = cached
            else:
                search_status = st.empty()
                search_status.info(f"Searching r/{subreddit}...")
                fetch_limit = requested + len(post_state.get("submitted", [])) + len(post_state.get("ignored", [])) + 5
                posts = bot.search_posts(subreddit=subreddit.strip() or None, limit=fetch_limit, include_body=False, include_comments=False)
                posts = _normalize_cached_posts(posts)
                st.session_state[cache_key] = {"ts": time.time(), "posts": posts}
                search_status.empty()
            st.session_state["last_posts"] = posts
            st.session_state["last_posts_fetched_count"] = len(posts)
            st.session_state["last_requested_limit"] = requested
    posts = _normalize_cached_posts(st.session_state.get("last_posts", []))
    st.session_state["last_posts"] = posts
    fetched_count = st.session_state.get("last_posts_fetched_count")
    requested_limit = st.session_state.get("last_requested_limit", 0)
    if posts:
        filtered_posts = []
        seen = set()
        for p in posts:
            key = _post_key(p)
            if key in post_state["submitted"] or key in post_state["ignored"]:
                continue
            dedupe_key = key or p.get("title", "")
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            filtered_posts.append(p)
        # Cap to requested limit to avoid overshooting the user's requested count.
        posts = filtered_posts[:requested_limit or len(filtered_posts)]
        shown_count = len(posts)
        if requested_limit and shown_count < requested_limit:
            st.success(f"Showing {shown_count} of requested {requested_limit} (filtered out submitted/ignored or not enough new posts).")
        else:
            st.success(f"Showing {shown_count} posts.")
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
                    url = f"https://www.reddit.com/r/{sub}/comments/{pid}/"
            subreddit = post.get("subreddit", "")
            st.markdown(f"**{idx}. {title}**  _(r/{subreddit})_")
            if url:
                st.code(url, language="")
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

                # Render status message for this post outside the expander
            if status_key in st.session_state:
                level, msg = st.session_state[status_key]
                if level == "success":
                    st.success(msg)
                elif level == "warning":
                    st.warning(msg)
                elif level == "error":
                    st.error(msg)

            # Post-level actions (outside the expander)
            pad_left, col_a, col_b, pad_right = st.columns([0.1, 2, 2, 5], gap="small")
            mark_sub_key = f"mark_submitted_{post_key}"
            mark_submitted_box = col_a.checkbox("Mark submitted", key=mark_sub_key, value=False)
            ignore_key = f"ignore_post_{post_key}"
            ignore_checked = col_b.checkbox("Ignore this post", key=ignore_key, value=False)

            if mark_submitted_box and post_key not in post_state["submitted"]:
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
                st.success("Marked as submitted.")
                st.session_state["last_action"] = f"mark_submitted {post_key}"
                st.rerun()

            if ignore_checked and post_key not in post_state["ignored"]:
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
                st.success("Post ignored.")
                st.session_state["last_action"] = f"ignore {post_key}"
                st.rerun()

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
                for d in list(submitted_details):
                    title = d.get("title") or "Untitled"
                    key_val = d.get("key", title)
                    chk_key = f"submitted_item_{key_val}"
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
                for d in list(entries):
                    title = d.get("title") or "Untitled"
                    key_val = d.get("key", title)
                    chk_key = f"ignored_item_{key_val}"
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
