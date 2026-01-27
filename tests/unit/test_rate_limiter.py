from microdose_study_bot.core.rate_limiter import RateLimiter


def test_rate_limiter_allows_and_blocks():
    rl = RateLimiter()
    limits = {
        "vote": {"per_hour": 1, "per_day": 2, "per_week": 3, "jitter_seconds": 0}
    }

    allowed, wait = rl.check_rate_limit("acct", "vote", limits)
    assert allowed
    assert wait == 0

    rl.record_action("acct", "vote")
    allowed, wait = rl.check_rate_limit("acct", "vote", limits)
    assert not allowed
    assert wait >= 3600
