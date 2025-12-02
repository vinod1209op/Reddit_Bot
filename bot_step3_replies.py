"""
STEP 3: Keyword filtering + human-approved reply workflow with logging.

What this script does:
- Loads .env for Reddit credentials (and optional mock mode).
- Scans safe subreddits for posts containing configured keywords.
- Generates a short, neutral, harm-reduction-friendly reply (stubbed or via LLM).
- Asks the human to approve before posting; posting is disabled by default (dry-run).
- Logs every decision to a CSV so engagement analysis can be done later.

Safety/ethics reminders:
- Do NOT give medical or dosing advice.
- Do NOT encourage illegal activity.
- Do NOT add links or promote products.
- Human must stay in the loop; low-volume and explicit approval per post.
- Respect subreddit rules and Reddit's Responsible Builder Policy.
"""

import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

import praw
import prawcore
from dotenv import load_dotenv

try:
    import openai  # Optional; used only if USE_LLM=1 and OPENAI_API_KEY is set.
except ImportError:  # Optional dependency; safe to ignore when not installed.
    openai = None


SUBREDDITS: Sequence[str] = ["learnpython"]  # Swap to wellness subs later.
KEYWORDS: Sequence[str] = ["test", "python", "help"]  # Swap to wellness-related terms later.
LOG_PATH = Path("bot_logs.csv")

# Posting is disabled by default; set ENABLE_POSTING=1 to allow replies.
ENABLE_POSTING = os.getenv("ENABLE_POSTING") == "1"
# Optional hard cap to keep volume low per run.
MAX_APPROVED_PER_RUN = 10
# Optional flag to use LLM; falls back to stub if not configured/available.
USE_LLM = os.getenv("USE_LLM") == "1"
# Optional run identifier for grouping logs.
RUN_ID = os.getenv("RUN_ID") or datetime.now(timezone.utc).isoformat()

# Safety prompt for LLM calls (when enabled). Keep this strict and neutral.
SAFETY_PROMPT = """You are an educational assistant focused on harm reduction and neutral information.
Rules:
- Do not give medical or dosing advice.
- Do not encourage illegal activity or acquisition of substances.
- Do not promote products, brands, or websites.
- Keep replies short (2-5 sentences), neutral, and focus on general risks/considerations.
- Suggest speaking with qualified professionals for personal guidance.
- Respect community rules and be considerate in tone."""

# Mock data for offline/testing mode.
MOCK_POSTS: List[Mapping[str, str]] = [
    {
        "id": "mock1",
        "subreddit": "learnpython",
        "title": "Mock post asking for python help",
        "score": 10,
        "body": "Sample body mentioning python and a test script.",
    },
    {
        "id": "mock2",
        "subreddit": "learnpython",
        "title": "Mock post unrelated to keywords",
        "score": 5,
        "body": "This one should not match unless keywords change.",
    },
    {
        "id": "mock3",
        "subreddit": "learnpython",
        "title": "Need help debugging",
        "score": 8,
        "body": "Stuck on a problem; any python tips are welcome.",
    },
]


def get_reddit_client() -> praw.Reddit:
    """Create a Reddit client using environment variables. Errors bubble up to be handled in main."""
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        username=os.environ["REDDIT_USERNAME"],
        password=os.environ["REDDIT_PASSWORD"],
        user_agent=os.environ["REDDIT_USER_AGENT"],
    )


def fetch_posts(reddit: praw.Reddit, subreddit_name: str, limit: int = 50) -> Iterable:
    """Fetch posts from Reddit; on error, return mock posts."""
    try:
        subreddit = reddit.subreddit(subreddit_name)
        return subreddit.new(limit=limit)
    except (prawcore.exceptions.PrawcoreException, KeyError) as exc:
        print("Reddit API not available (or access limited). Running in mock mode instead.", file=sys.stderr)
        print(f"Details: {exc}", file=sys.stderr)
        return MOCK_POSTS
    except Exception as exc:
        print("Reddit API not available (or access limited). Running in mock mode instead.", file=sys.stderr)
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return MOCK_POSTS


def normalize_post(post, default_subreddit: str) -> Mapping[str, str]:
    """Convert either a PRAW submission or a mock dict into a consistent mapping."""
    return {
        "id": getattr(post, "id", None) or post.get("id", ""),
        "subreddit": getattr(post, "subreddit", None) or post.get("subreddit", default_subreddit),
        "title": getattr(post, "title", None) or post.get("title", ""),
        "score": getattr(post, "score", None) or post.get("score", 0),
        "body": getattr(post, "selftext", None) or post.get("body", ""),
    }


def matched_keywords(text: str, keywords: Sequence[str]) -> List[str]:
    """Return a list of keywords that appear in the text (case-insensitive)."""
    haystack = text.lower()
    return [kw for kw in keywords if kw.lower() in haystack]


def stub_reply(info: Mapping[str, str], hits: Sequence[str]) -> str:
    """Deterministic, safe fallback reply."""
    keyword_blurb = ", ".join(hits) if hits else "your topic"
    return (
        "Thanks for sharing this question. I’m just an info bot focused on general education and harm reduction. "
        f"People report different experiences around {keyword_blurb}; risks and benefits vary. "
        "For personal guidance, it’s best to speak with a qualified professional who knows your situation."
    )


def llm_reply(info: Mapping[str, str], hits: Sequence[str]) -> Optional[str]:
    """Attempt to generate a reply via OpenAI, respecting the safety prompt. Returns None on failure."""
    if not USE_LLM:
        return None
    if openai is None:
        return None
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    openai.api_key = api_key
    prompt = (
        SAFETY_PROMPT
        + "\n\n"
        + f"Reddit post title: {info['title']}\n"
        + f"Reddit post body: {info['body']}\n"
        + f"Matched keywords: {', '.join(hits)}\n"
        + "Write one short reply (2-5 sentences) that follows the rules."
    )
    try:
        # Using completions for simplicity; adjust model/params as needed later.
        resp = openai.Completion.create(
            model="gpt-3.5-turbo-instruct",
            prompt=prompt,
            max_tokens=160,
            temperature=0.4,
        )
        text = resp["choices"][0]["text"].strip()
        return text
    except Exception as exc:
        print(f"LLM generation failed; falling back to stub. Details: {exc}", file=sys.stderr)
        return None


def generate_reply(info: Mapping[str, str], hits: Sequence[str]) -> str:
    """Generate a safe reply via LLM when enabled, else use stub."""
    llm_text = llm_reply(info, hits)
    return llm_text if llm_text else stub_reply(info, hits)


def append_log(row: Mapping[str, str]) -> None:
    """Append a row to the CSV log, creating headers on first write."""
    header = [
        "run_id",
        "timestamp_utc",
        "mode",
        "subreddit",
        "post_id",
        "title",
        "matched_keywords",
        "reply_text",
        "approved",
        "posted",
        "comment_id",
        "error",
    ]
    file_exists = LOG_PATH.exists()
    with LOG_PATH.open("a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=header)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def iter_matches(posts: Iterable, keywords: Sequence[str], default_subreddit: str) -> Iterable[Tuple[Mapping[str, str], object, List[str]]]:
    """Yield (normalized_info, raw_post, hits) for posts matching keywords."""
    for post in posts:
        info = normalize_post(post, default_subreddit)
        combined = f"{info['title']} {info['body']}".lower()
        hits = matched_keywords(combined, keywords)
        if hits:
            yield info, post, hits


def main() -> None:
    load_dotenv()
    forced_mock = os.getenv("MOCK_MODE") == "1"

    approved_count = 0

    if forced_mock:
        print("MOCK_MODE is set; running with mock posts.")
        reddit = None
        mode = "mock"
    else:
        try:
            reddit = get_reddit_client()
            user = reddit.user.me()
            print(f"Logged in as: {user}")
            mode = "live"
        except Exception as exc:
            print("Reddit API not available (or access limited). Running in mock mode instead.", file=sys.stderr)
            print(f"Details: {exc}", file=sys.stderr)
            reddit = None
            mode = "mock"
            forced_mock = True

    for subreddit_name in SUBREDDITS:
        print(f"\nScanning r/{subreddit_name} for keywords: {', '.join(KEYWORDS)}")
        posts = MOCK_POSTS if forced_mock else fetch_posts(reddit, subreddit_name, limit=50)

        for info, raw_post, hits in iter_matches(posts, KEYWORDS, subreddit_name):
            print(
                f"\n[MATCH] ID: {info['id']}\n"
                f"Subreddit: r/{info['subreddit']}\n"
                f"Title: {info['title']}\n"
                f"Matched keywords: {hits}\n"
            )

            reply_text = generate_reply(info, hits)
            print("Suggested reply:\n")
            print(reply_text)
            print()

            decision = input("Post this reply? (y/n): ").strip().lower()
            approved = decision == "y"
            posted = False
            comment_id = ""
            error = ""

            if approved:
                if approved_count >= MAX_APPROVED_PER_RUN:
                    print("Approval cap reached for this run; not posting further replies.")
                    approved = False
                else:
                    approved_count += 1
                    if ENABLE_POSTING and (not forced_mock) and hasattr(raw_post, "reply"):
                        try:
                            reply = raw_post.reply(reply_text)
                            comment_id = getattr(reply, "id", "") or ""
                            posted = True
                            print("Reply posted.")
                        except Exception as exc:
                            error = f"Failed to post: {exc}"
                            print(error, file=sys.stderr)
                    else:
                        print("Posting is disabled (dry-run). Set ENABLE_POSTING=1 to allow replies.")

            log_row = {
                "run_id": RUN_ID,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "mode": mode,
                "subreddit": info["subreddit"],
                "post_id": info["id"],
                "title": info["title"],
                "matched_keywords": ",".join(hits),
                "reply_text": reply_text,
                "approved": str(approved),
                "posted": str(posted),
                "comment_id": comment_id,
                "error": error,
            }
            append_log(log_row)


if __name__ == "__main__":
    main()
