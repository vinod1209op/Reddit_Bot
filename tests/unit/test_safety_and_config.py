import sys
import types
import unittest
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parents[2]

from microdose_study_bot.core.config import ConfigManager
from microdose_study_bot.core.safety.checker import SafetyChecker


class DummyConfig(ConfigManager):
    """Minimal config stub that keeps rate_limits in-memory."""

    def __init__(self):
        super().__init__()
        # Tight limits for test speed
        self.rate_limits = {
            "comment": {"max_per_hour": 1, "min_interval": 1, "daily_limit": 2}
        }

    def load_all(self):
        return self


class SafetyCheckerTests(unittest.TestCase):
    def test_rate_limit_blocks_after_max(self):
        cfg = DummyConfig()
        checker = SafetyChecker(cfg)
        allowed, _ = checker.can_perform_action("comment")
        self.assertTrue(allowed)
        checker.record_action("comment")
        # Second action should hit hourly max_per_hour=1
        allowed, reason = checker.can_perform_action("comment")
        self.assertFalse(allowed)
        self.assertIn("Rate limit", reason)

    def test_cooldown_respected(self):
        cfg = DummyConfig()
        cfg.rate_limits["comment"]["max_per_hour"] = 5
        cfg.rate_limits["comment"]["min_interval"] = 2
        checker = SafetyChecker(cfg)
        checker.record_action("comment")
        allowed, reason = checker.can_perform_action("comment")
        self.assertFalse(allowed)
        self.assertIn("Cooldown", reason)

    def test_content_safety_filters_personal_info(self):
        cfg = DummyConfig()
        checker = SafetyChecker(cfg)
        allowed, reason = checker.can_perform_action("comment", target="Call me at 555-123-4567")
        self.assertFalse(allowed)
        self.assertIn("Content failed", reason)


class ConfigManagerTests(unittest.TestCase):
    def test_load_all_returns_defaults_when_files_missing(self):
        cfg = ConfigManager().load_all()
        self.assertTrue(cfg.bot_settings.get("subreddits"))
        self.assertTrue(cfg.bot_settings.get("keywords"))
        self.assertIsInstance(cfg.rate_limits, dict)
        self.assertTrue(cfg.api_creds is not None)


if __name__ == "__main__":
    unittest.main()
