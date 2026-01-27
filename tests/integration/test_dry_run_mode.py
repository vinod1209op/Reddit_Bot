from microdose_study_bot.reddit_selenium.automation_base import RedditAutomationBase


def test_dry_run_mode_sets_no_browser():
    base = RedditAutomationBase(account_name="account1", dry_run=True)
    assert base.driver is None
    assert base.logged_in
    base.cleanup()
