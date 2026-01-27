from microdose_study_bot.reddit_selenium.automation_base import RedditAutomationBase


def test_automation_base_dry_run_executes_without_browser():
    base = RedditAutomationBase(account_name="account1", dry_run=True)

    result = base.execute_safely(lambda: "ok", action_name="noop")
    assert result.success
    assert result.attempts == 0

    validation = base.run_validations()
    assert "configs" in validation
    base.cleanup()
