import sys
import tempfile
import unittest
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parents[2]

from microdose_study_bot.core.text_normalization import (  # noqa: E402
    preview_text,
    normalize_post,
    matched_keywords,
)
from microdose_study_bot.core.reddit_client import fetch_posts
from microdose_study_bot.core.storage.csv_log_writer import append_log


class DummyPost:
    def __init__(self):
        self.id = "abc"
        self.subreddit = "testsub"
        self.title = "Hello"
        self.selftext = "World body"
        self.score = 5


class DummySubreddit:
    def __init__(self, payload):
        self.payload = payload

    def new(self, limit):
        return self.payload


class DummyReddit:
    def __init__(self, payload):
        self.payload = payload

    def subreddit(self, name):
        return DummySubreddit(self.payload)


class TextNormalizationTest(unittest.TestCase):
    def test_preview_text_truncates_and_sanitizes(self):
        text = "line1\nline2   with   spaces"
        out = preview_text(text, width=10)
        self.assertNotIn("\n", out)
        self.assertLessEqual(len(out), 13)  # width + ellipsis
        self.assertTrue(out.endswith("..."))

    def test_normalize_post_accepts_attr_and_dict(self):
        post_obj = DummyPost()
        norm_obj = normalize_post(post_obj, "fallback")
        self.assertEqual(norm_obj["id"], "abc")
        self.assertEqual(norm_obj["subreddit"], "testsub")
        post_dict = {"id": "d1", "title": "t", "body": "b"}
        norm_dict = normalize_post(post_dict, "fallback")
        self.assertEqual(norm_dict["subreddit"], "fallback")

    def test_matched_keywords_case_insensitive(self):
        hits = matched_keywords("This Has KeyWord", ["keyword", "other"])
        self.assertEqual(hits, ["keyword"])

    def test_fetch_posts_success_and_fallback(self):
        reddit = DummyReddit(payload=[1, 2, 3])
        self.assertEqual(list(fetch_posts(reddit, "x", 5, fallback_posts=[])), [1, 2, 3])
        class Failer(DummyReddit):
            def subreddit(self, name):
                raise RuntimeError("boom")
        fb = [9]
        self.assertEqual(list(fetch_posts(Failer(fb), "x", 5, fallback_posts=fb)), fb)

    def test_append_log_writes_header_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "log.csv"
            header = ["a", "b"]
            append_log(path, {"a": "1", "b": "2"}, header)
            append_log(path, {"a": "3", "b": "4"}, header)
            content = path.read_text().splitlines()
            self.assertEqual(content[0], "a,b")
            self.assertEqual(len(content), 3)


if __name__ == "__main__":
    unittest.main()
