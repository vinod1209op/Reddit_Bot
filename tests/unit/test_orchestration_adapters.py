import os
from types import SimpleNamespace

import pytest

from microdose_study_bot.orchestration.adapters import RedditBotAdapter


class DummyConfig:
    def __init__(self, enable_posting=True):
        self.bot_settings = {"mode": "api", "enable_posting": enable_posting}
        self.api_creds = {}
        self.rate_limits = {}


class FakeSubmission:
    def __init__(self, comment_id="c1"):
        self._comment_id = comment_id
        self.permalink = f"/r/test/comments/xyz/{comment_id}"

    def reply(self, _text):
        return SimpleNamespace(id=self._comment_id, permalink=self.permalink)


class FakePraw:
    def __init__(self):
        self._submission = FakeSubmission()

    def submission(self, id):  # noqa: A002 - matches PRAW signature
        return self._submission


class FakeSeleniumBot:
    def __init__(self, success=True):
        self.success = success

    def reply_to_post(self, post_url, reply_text, dry_run=False):
        if self.success:
            return {"success": True, "submitted": True, "comment_id": "s1"}
        return {"success": False, "error": "submit failed"}


def test_reply_api_idempotent_skip(tmp_path, monkeypatch):
    idem = tmp_path / "idem.json"
    monkeypatch.setenv("IDEMPOTENCY_PATH", str(idem))

    cfg = DummyConfig(enable_posting=True)
    adapter = RedditBotAdapter(cfg)
    adapter.praw_client = FakePraw()

    post = {"id": "abc123", "subreddit": "test", "title": "hello", "raw": FakeSubmission()}

    result1 = adapter.reply_api(post, "hi")
    assert result1["success"] is True

    result2 = adapter.reply_api(post, "hi again")
    assert result2["success"] is False
    assert result2["code"] == "idempotent_skip"


def test_reply_selenium_idempotent_skip(tmp_path, monkeypatch):
    idem = tmp_path / "idem.json"
    monkeypatch.setenv("IDEMPOTENCY_PATH", str(idem))

    cfg = DummyConfig(enable_posting=True)
    cfg.bot_settings["mode"] = "selenium"
    adapter = RedditBotAdapter(cfg)
    adapter.selenium_bot = FakeSeleniumBot(success=True)

    post = {"id": "abc123", "subreddit": "test", "title": "hello", "url": "https://old.reddit.com/r/test/comments/abc123/"}

    result1 = adapter.reply_selenium(post, "hi")
    assert result1["success"] is True

    result2 = adapter.reply_selenium(post, "hi again")
    assert result2["success"] is False
    assert result2["code"] == "idempotent_skip"
