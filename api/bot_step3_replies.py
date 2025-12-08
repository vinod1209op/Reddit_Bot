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

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import praw
from dotenv import load_dotenv
from shared.config_manager import ConfigManager
from shared.safety_checker import SafetyChecker
from shared.api_utils import normalize_post, matched_keywords, fetch_posts, append_log

try:
    from openai import OpenAI  # Optional; used only if USE_LLM=1 and OPENAI_API_KEY is set.
except ImportError:  # Optional dependency; safe to ignore when not installed.
    OpenAI = None


SUBREDDITS: Sequence[str] = []  # populated from ConfigManager at runtime
KEYWORDS: Sequence[str] = []  # populated from ConfigManager at runtime
LOG_PATH = Path("bot_logs.csv")
LOG_HEADER = [
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

# Posting is disabled by default; set ENABLE_POSTING=1 to allow replies.
# These are populated in main() after load_dotenv so .env changes take effect.
ENABLE_POSTING = False
# Optional hard cap to keep volume low per run (reduced to 5 for extra caution).
MAX_APPROVED_PER_RUN = 5
# Optional flag to use LLM; falls back to stub if not configured/available.
USE_LLM = False
# Optional run identifier for grouping logs.
RUN_ID = ""
# Gentle delay between approved posts to respect rate/volume.
POST_DELAY_SECONDS = 60

# Safety prompt for LLM calls (when enabled). Keep this strict and neutral.
SAFETY_PROMPT = """You are an educational assistant focused on harm reduction and neutral information.
Rules:
- Do not give medical or dosing advice.
- Do not encourage illegal activity or acquisition of substances.
- Do not promote products, brands, or websites.
- Do not provide microdosing protocols, schedules, or dose guidance; emphasize legal/health risks and uncertainty.
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
        user_agent=os.environ.get("REDDIT_USER_AGENT", "reddit-bot-research/1.0 (+contact)"),
        requestor_kwargs={"timeout": 10},
    )


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
    if OpenAI is None:
        return None
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    client = OpenAI(api_key=api_key)
    prompt = (
        SAFETY_PROMPT
        + "\n\n"
        + f"Reddit post title: {info['title']}\n"
        + f"Reddit post body: {info['body']}\n"
        + f"Matched keywords: {', '.join(hits)}\n"
        + "Write one short reply (2-5 sentences) that follows the rules."
    )
    try:
        resp = client.completions.create(
            model="gpt-3.5-turbo-instruct",
            prompt=prompt,
            max_tokens=160,
            temperature=0.4,
        )
        text = resp.choices[0].text.strip()
        return text
    except Exception as exc:
        print(f"LLM generation failed; falling back to stub. Details: {exc}", file=sys.stderr)
        return None


def generate_reply(info: Mapping[str, str], hits: Sequence[str]) -> str:
    """Generate a safe reply via LLM when enabled, else use stub."""
    llm_text = llm_reply(info, hits)
    return llm_text if llm_text else stub_reply(info, hits)


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
    # Refresh env-driven toggles after .env is loaded
    global ENABLE_POSTING, USE_LLM, RUN_ID
    ENABLE_POSTING = os.getenv("ENABLE_POSTING") == "1"
    USE_LLM = os.getenv("USE_LLM") == "1"
    RUN_ID = os.getenv("RUN_ID") or datetime.now(timezone.utc).isoformat()
    forced_mock = os.getenv("MOCK_MODE") == "1"
    config = ConfigManager().load_all()
    subreddits = config.bot_settings.get("subreddits") or config.default_subreddits
    keywords = config.bot_settings.get("keywords") or config.default_keywords
    safety_checker = SafetyChecker(config)

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

    for subreddit_name in subreddits:
        print(f"\nScanning r/{subreddit_name} for keywords: {', '.join(keywords)}")
        posts = MOCK_POSTS if forced_mock else fetch_posts(reddit, subreddit_name, limit=50, fallback_posts=MOCK_POSTS)

        for info, raw_post, hits in iter_matches(posts, keywords, subreddit_name):
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
                    allowed, reason = safety_checker.can_perform_action("comment", target=info["title"])
                    if not allowed:
                        error = f"Rate/safety blocked: {reason}"
                        print(error)
                        approved = False
                    else:
                        approved_count += 1
                        if ENABLE_POSTING and (not forced_mock) and hasattr(raw_post, "reply"):
                            try:
                                reply = raw_post.reply(reply_text)
                                comment_id = getattr(reply, "id", "") or ""
                                posted = True
                                print("Reply posted.")
                                safety_checker.record_action("comment", target=info["title"])
                                time.sleep(POST_DELAY_SECONDS)  # be gentle with rate/volume
                            except Exception as exc:
                                error = f"Failed to post: {exc}"
                                print(error, file=sys.stderr)
                        else:
                            print("Posting is disabled (dry-run). Set ENABLE_POSTING=1 to allow replies.")
                            safety_checker.record_action("comment", target=info["title"], success=True)

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
            append_log(LOG_PATH, log_row, LOG_HEADER)


if __name__ == "__main__":
    main()
