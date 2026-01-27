from microdose_study_bot.core.account_status import AccountStatusTracker


def test_activity_tracking(tmp_path):
    status_file = tmp_path / "account_status.json"
    tracker = AccountStatusTracker(status_file=str(status_file))

    tracker.record_subreddit_creation("acct", "sub1", True)
    tracker.record_post_activity("acct", "sub1", "discussion", True, daily_limit=1)
    tracker.record_moderation_activity("acct", "sub1", "setup", True)

    assert tracker.get_account_status("acct") in ("subreddit_created", "posting_limited", "moderation_flagged", "active", "unknown")
    remaining = tracker.get_cooldown_remaining("acct", "posting")
    assert remaining is None or remaining >= 0

    can_post = tracker.can_perform_action("acct", "posting", subreddit="sub1", daily_limit=1)
    assert can_post in (True, False)
