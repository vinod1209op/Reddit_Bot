#!/usr/bin/env python3
"""Streamlit UI to drive Selenium prefill (dry-run only)."""

import os
import sys
from pathlib import Path
from typing import Optional

import streamlit as st

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

    st.session_state.bot = bot
    return bot


def close_bot() -> None:
    bot = st.session_state.get("bot")
    if bot:
        bot.close()
    st.session_state.bot = None


def main() -> None:
    st.set_page_config(page_title="Reddit Selenium Prefill", layout="wide")
    st.title("Reddit Selenium Prefill (Dry-Run)")
    st.write("Prefills a reply in Reddit's composer using Selenium. No auto-submit.")

    if not require_auth():
        return

    cfg = load_config()

    with st.sidebar:
        st.subheader("Status & Controls")
        bot_active = bool(st.session_state.get("bot"))
        st.write(f"Browser status: {'🟢 Ready' if bot_active else '🔴 Not started'}")
        if st.button("Start / Reconnect Browser"):
            if ensure_bot(cfg):
                st.success("Browser ready.")
        if st.button("Close Browser"):
            close_bot()
            st.info("Browser closed.")
        st.markdown(
            "- Uses your server-side Reddit session.\n"
            "- Dry-run only; you must manually submit in the browser.\n"
            "- LLM uses OpenRouter if `OPENROUTER_API_KEY` is set."
        )

    st.header("Find Posts")
    with st.form("search_form", clear_on_submit=False):
        subreddit = st.text_input("Subreddit", value="microdosing", help="Name without r/")
        limit = st.number_input("How many posts?", min_value=1, max_value=100, value=15, step=1)
        submitted_search = st.form_submit_button("Search")
    if submitted_search:
        bot = ensure_bot(cfg)
        if bot:
            st.info(f"Searching r/{subreddit}...")
            posts = bot.search_posts(subreddit=subreddit.strip() or None, limit=int(limit), include_body=False, include_comments=False)
            st.session_state["last_posts"] = posts
            if posts:
                st.success(f"Found {len(posts)} posts.")
            else:
                st.warning("No posts found.")
    posts = st.session_state.get("last_posts", [])
    if posts:
        st.subheader("Posts")
        for idx, post in enumerate(posts, 1):
            title = post.get("title") or "No title"
            url = post.get("url") or post.get("permalink") or ""
            subreddit = post.get("subreddit", "")
            col1, col2 = st.columns([0.8, 0.2])
            with col1:
                st.markdown(f"**{idx}. {title}**  _(r/{subreddit})_")
                if url:
                    st.code(url, language="")
            with col2:
                if url and st.button("Use for prefill", key=f"use_{idx}"):
                    st.session_state["prefill_url"] = url
    st.header("Prefill Reply")
    with st.form("prefill_form", clear_on_submit=False):
        prefill_default = st.session_state.get("prefill_url", "")
        post_url = st.text_input(
            "Post URL or path",
            value=prefill_default,
            help="Accepts full URL or paths like /r/sub/comments/xyz/title/",
        )
        use_llm = st.checkbox("Generate reply with LLM (OpenRouter)", value=False)
        use_page_context = st.checkbox("Use page title/body as context (fetches post)", value=True)
        manual_context = st.text_area(
            "Manual context (optional)",
            placeholder="Provide a brief prompt/context for the reply.",
        )
        manual_reply = st.text_area(
            "Manual reply (used if LLM disabled or fails)",
            placeholder="Enter reply text to prefill",
        )
        submitted = st.form_submit_button("Prefill (dry-run)")

    if submitted:
        if not post_url.strip():
            st.error("Please provide a post URL or path.")
            return

        bot = ensure_bot(cfg)
        if not bot:
            return

        reply_text = manual_reply.strip()
        if use_llm:
            bot.use_llm = True  # ensure LLM is allowed for this run
            context = ""
            if use_page_context:
                st.info("Fetching post context...")
                context = bot.fetch_post_context(post_url) or ""
            if not context:
                context = manual_context.strip() or "Provide a concise, supportive, safe reply."
            st.info("Generating reply via OpenRouter...")
            llm_text = bot.generate_llm_reply(context)
            if llm_text:
                reply_text = llm_text
                st.success("LLM reply generated:")
                st.code(reply_text)
            else:
                st.warning("LLM generation unavailable; falling back to manual reply.")

        if not reply_text:
            st.error("No reply text available. Enter a manual reply or enable LLM.")
            return

        st.info("Attempting to prefill (no auto-submit)...")
        result = bot.reply_to_post(post_url, reply_text, dry_run=True)
        if result.get("success"):
            st.success("Prefill attempted. Review the browser window and submit manually.")
        else:
            st.error(f"Failed to prefill: {result.get('error', 'unknown error')}")


if __name__ == "__main__":
    main()
