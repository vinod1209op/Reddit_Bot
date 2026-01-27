"""
Purpose: Shared automation base for Selenium workflows.
Constraints: No posting logic; provide lifecycle and safety helpers.
"""

from __future__ import annotations

import time
import os
import json
import smtplib
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from microdose_study_bot.core.account_status import AccountStatusTracker
from microdose_study_bot.core.config import ConfigManager
from microdose_study_bot.core.logging import UnifiedLogger
from microdose_study_bot.core.rate_limiter import RateLimiter
from microdose_study_bot.reddit_selenium.login import LoginManager
from microdose_study_bot.reddit_selenium.utils.browser_manager import BrowserManager
from microdose_study_bot.reddit_selenium.utils.human_simulator import HumanSimulator


@dataclass
class LoginResult:
    success: bool
    status: str
    method: str


@dataclass
class ActionResult:
    success: bool
    attempts: int
    duration_seconds: float
    result: Any = None
    error: Optional[str] = None


class RedditAutomationBase:
    """
    Base class for Selenium automation scripts.
    Handles browser setup, login, status tracking, retries, and cleanup.
    """

    def __init__(self, account_name: str, config_profile: str = "default", dry_run: bool = False):
        self.logger = UnifiedLogger(self.__class__.__name__).get_logger()
        self.account_name = account_name
        self.config_profile = config_profile
        self.dry_run = dry_run
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_log_path = Path("data/automation_runs") / f"{account_name}_{self.run_id}.json"

        self.config_manager = ConfigManager().load_all()
        self.account = self._load_account(account_name)
        self.status_tracker = AccountStatusTracker()
        self.rate_limiter = RateLimiter()

        self.activity_schedule = self.config_manager.activity_schedule or {}
        self.subreddit_creation = self.config_manager.subreddit_creation or {}
        self.post_scheduling = self.config_manager.post_scheduling or {}
        self.moderation = (self.activity_schedule or {}).get("moderation", {})
        self.profile_name = self._resolve_profile_name()
        self.last_action_result: Optional[ActionResult] = None
        self.action_results: list[ActionResult] = []
        self.failure_counts: Dict[str, int] = {}

        self.browser_manager: Optional[BrowserManager] = None
        self.login_manager: Optional[LoginManager] = None
        self.human_sim: Optional[HumanSimulator] = None
        self.driver = None
        self.logged_in = False
        self.last_login_status = "unknown"

        if not self.dry_run:
            self._setup_browser()
            self._login_with_fallback()
        self._write_run_log(event="start")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.cleanup()
        return False

    def _resolve_profile_name(self) -> str:
        if self.config_profile and self.config_profile != "default":
            return self.config_profile
        return (
            self.subreddit_creation.get("default_profile")
            or self.activity_schedule.get("default_profile")
            or "default"
        )

    def validate_configs(self) -> Tuple[bool, Dict[str, Any]]:
        required = [
            "config/accounts.json",
            "config/activity_schedule.json",
            "config/subreddit_creation.json",
            "config/post_scheduling.json",
        ]
        missing = [path for path in required if not Path(path).exists()]
        return len(missing) == 0, {"missing": missing}

    def validate_account(self) -> Tuple[bool, Dict[str, Any]]:
        cookies_path = self.account.get("cookies_path") or self.config_manager.selenium_settings.get("cookie_file")
        has_cookies = bool(cookies_path and Path(cookies_path).exists())
        return True, {"cookies_path": cookies_path, "cookies_present": has_cookies}

    def validate_rate_limits(self, action_name: str) -> Tuple[bool, Dict[str, Any]]:
        limits_config = (self.activity_schedule or {}).get("rate_limits", {})
        allowed, wait_seconds = self.rate_limiter.check_rate_limit(
            self.account_name, action_name, limits_config
        )
        return allowed, {"wait_seconds": wait_seconds}

    def validate_patterns(self) -> Tuple[bool, Dict[str, Any]]:
        jitter = (self.activity_schedule or {}).get("randomization", {}).get("jitter_percentage", 0)
        return jitter >= 10, {"jitter_percentage": jitter}

    def run_validations(self) -> Dict[str, Any]:
        config_ok, config_info = self.validate_configs()
        acct_ok, acct_info = self.validate_account()
        pattern_ok, pattern_info = self.validate_patterns()
        return {
            "configs": {"ok": config_ok, **config_info},
            "account": {"ok": acct_ok, **acct_info},
            "patterns": {"ok": pattern_ok, **pattern_info},
        }

    def is_feature_enabled(self, feature_key: str) -> Tuple[bool, str]:
        feature = (self.activity_schedule or {}).get(feature_key, {})
        enabled = bool(feature.get("enabled", False))
        if not enabled:
            return False, "feature_disabled"
        if bool(feature.get("require_manual_review", True)) and not bool(feature.get("approved", False)):
            return False, "manual_approval_required"
        return True, "ok"

    def _load_account(self, account_name: str) -> Dict[str, Any]:
        accounts = self.config_manager.load_accounts_config() or []
        for account in accounts:
            if account.get("name") == account_name:
                return account
        raise ValueError(f"Account {account_name} not found in config/accounts.json")

    def _setup_browser(self) -> None:
        settings = self.config_manager.selenium_settings or {}
        headless = bool(settings.get("headless", False))
        use_undetected = settings.get("use_undetected", True)
        stealth_mode = settings.get("stealth_mode", True)
        randomize_fingerprint = settings.get("randomize_fingerprint", True)

        self.browser_manager = BrowserManager(
            headless=headless,
            stealth_mode=stealth_mode,
            randomize_fingerprint=randomize_fingerprint,
            use_undetected=use_undetected,
        )
        self.driver = self.browser_manager.create_driver(use_undetected=use_undetected)
        self.login_manager = LoginManager(browser_manager=self.browser_manager, driver=self.driver, headless=headless)
        self.human_sim = HumanSimulator(self.driver, browser_manager=self.browser_manager)

    def _login_with_fallback(self) -> LoginResult:
        if self.dry_run:
            self.logged_in = True
            self.last_login_status = "dry_run"
            return LoginResult(True, "dry_run", "dry_run")
        if not self.login_manager:
            return LoginResult(False, "error", "none")

        cookie_file = self.account.get("cookies_path") or self.config_manager.selenium_settings.get("cookie_file")
        google_email = self._resolve_credential(self.account.get("google_email_env_var")) or self.config_manager.google_creds.get("google_email")
        google_password = self._resolve_credential(self.account.get("google_password_env_var")) or self.config_manager.google_creds.get("google_password")
        reddit_user = self._resolve_credential(self.account.get("email_env_var")) or self.config_manager.api_creds.get("username")
        reddit_pass = self._resolve_credential(self.account.get("password_env_var")) or self.config_manager.api_creds.get("password")

        if cookie_file and self.login_manager.login_with_cookies(cookie_file):
            status = self.login_manager.check_account_status()
            self._update_status(status, method="cookies")
            return LoginResult(True, status, "cookies")

        if google_email and google_password:
            if self.login_manager.login_with_google(google_email, google_password):
                status = self.login_manager.check_account_status()
                self._update_status(status, method="google")
                return LoginResult(True, status, "google")

        if reddit_user and reddit_pass:
            if self.login_manager.login_with_credentials(reddit_user, reddit_pass):
                status = self.login_manager.check_account_status()
                self._update_status(status, method="credentials")
                return LoginResult(True, status, "credentials")

        status = "error"
        self._update_status(status, method="failed")
        return LoginResult(False, status, "failed")

    def _resolve_credential(self, env_var: Optional[str]) -> Optional[str]:
        if not env_var:
            return None
        return os.getenv(env_var) or None

    def _update_status(self, status: str, method: str) -> None:
        self.last_login_status = status
        self.logged_in = status in ("active", "captcha", "unknown")
        self.status_tracker.update_account_status(
            self.account_name,
            status,
            {"login_method": method, "dry_run": self.dry_run},
        )

    def check_account_eligibility(self) -> Tuple[bool, str]:
        if self.status_tracker.should_skip_account(self.account_name):
            return False, "status_skip"

        requirements = (self.subreddit_creation or {}).get("profiles", {}).get(
            (self.subreddit_creation or {}).get("default_profile", "conservative"),
            {},
        ).get("safety_check_requirements", {})

        if not requirements:
            return True, "ok"

        min_age = requirements.get("account_min_age_days")
        min_karma = requirements.get("account_min_karma")
        account_age = self.account.get("account_age_days")
        account_karma = self.account.get("account_karma")

        if min_age is not None and account_age is not None and account_age < min_age:
            return False, "account_too_new"
        if min_karma is not None and account_karma is not None and account_karma < min_karma:
            return False, "insufficient_karma"

        return True, "ok"

    def execute_safely(
        self,
        action_func: Callable[[], Any],
        max_retries: int = 3,
        login_required: bool = True,
        action_name: Optional[str] = None,
    ) -> ActionResult:
        if self.dry_run:
            self.logger.info("Dry-run enabled; skipping action execution.")
            result = ActionResult(True, 0, 0.0, result={"dry_run": True})
            self.last_action_result = result
            self.action_results.append(result)
            return result

        if login_required and not self.logged_in:
            login_result = self._login_with_fallback()
            if not login_result.success:
                result = ActionResult(False, 1, 0.0, error="login_failed")
                self.last_action_result = result
                self.action_results.append(result)
                return result

        action_key = action_name or getattr(action_func, "__name__", "unknown")
        limits_config = (self.activity_schedule or {}).get("rate_limits", {})
        allowed, wait_seconds = self.rate_limiter.check_rate_limit(
            self.account_name, action_key, limits_config
        )
        if not allowed:
            self.logger.warning("Rate limited for %s; wait %ss", action_key, wait_seconds)
            self.status_tracker.update_account_status(
                self.account_name,
                "posting_limited" if action_key.startswith("post") else "rate_limited",
                {"action": action_key, "wait_seconds": wait_seconds},
            )
            result = ActionResult(False, 0, 0.0, error="rate_limited")
            self.last_action_result = result
            self.action_results.append(result)
            return result

        attempt = 0
        last_exc: Optional[Exception] = None
        start_time = time.time()
        while attempt < max_retries:
            try:
                value = action_func()
                self.rate_limiter.record_action(self.account_name, action_key)
                self.failure_counts[action_key] = 0
                self.status_tracker.update_account_status(
                    self.account_name,
                    "active",
                    {"action": action_key, "attempt": attempt + 1},
                )
                result = ActionResult(True, attempt + 1, time.time() - start_time, result=value)
                self.last_action_result = result
                self.action_results.append(result)
                return result
            except Exception as exc:
                last_exc = exc
                attempt += 1
                self.failure_counts[action_key] = self.failure_counts.get(action_key, 0) + 1
                backoff = min(2 ** attempt, 30)
                self.logger.warning("Action failed (attempt %s/%s): %s", attempt, max_retries, exc)
                time.sleep(backoff)

        self.status_tracker.update_account_status(
            self.account_name,
            "error",
            {"action": action_key, "error": str(last_exc)},
        )
        self._apply_failure_backoff(action_key)
        result = ActionResult(False, attempt, time.time() - start_time, error=str(last_exc) if last_exc else None)
        self.last_action_result = result
        self.action_results.append(result)
        return result

    def human_delay(self, min_seconds: float, max_seconds: float) -> None:
        if self.browser_manager:
            self.browser_manager.add_human_delay(min_seconds, max_seconds)

    def simulate_human_behavior(self, element=None) -> None:
        if not self.human_sim:
            return
        if element is not None:
            self.human_sim.random_mouse_movements(element)
        else:
            self.human_sim.mouse_wander()

    def rate_limit_guard(self) -> Tuple[bool, str]:
        if self.status_tracker.should_skip_account(self.account_name):
            return False, "status_skip"
        return True, "ok"

    def health_snapshot(self) -> Dict[str, Any]:
        cookies_path = self.account.get("cookies_path") or self.config_manager.selenium_settings.get("cookie_file")
        cookies_age = None
        if cookies_path and Path(cookies_path).exists():
            cookies_age = datetime.now().timestamp() - Path(cookies_path).stat().st_mtime
        return {
            "account": self.account_name,
            "status": self.last_login_status,
            "logged_in": self.logged_in,
            "profile": self.profile_name,
            "cookies_path": cookies_path,
            "cookies_age_seconds": cookies_age,
        }

    def cleanup(self) -> None:
        if self.login_manager and self.logged_in:
            cookie_file = self.account.get("cookies_path") or self.config_manager.selenium_settings.get("cookie_file")
            if cookie_file:
                try:
                    self.login_manager.save_login_cookies(cookie_file)
                except Exception as exc:
                    self.logger.warning("Failed to save cookies: %s", exc)

        if self.browser_manager and self.driver:
            try:
                self.browser_manager.close_driver(self.driver)
            except Exception:
                pass

        final_status = self.last_login_status or "unknown"
        self.status_tracker.update_account_status(
            self.account_name,
            final_status,
            {"cleanup": True, "dry_run": self.dry_run},
        )
        self._write_run_log(event="end")

    def _write_run_log(self, event: str) -> None:
        try:
            self.run_log_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "event": event,
                "timestamp": datetime.now().isoformat(),
                "account": self.account_name,
                "status": self.last_login_status,
                "dry_run": self.dry_run,
                "profile": self.profile_name,
            }
            if event == "end":
                payload["health_snapshot"] = self.health_snapshot()
                if self.action_results:
                    total = len(self.action_results)
                    success = len([r for r in self.action_results if r.success])
                    payload["metrics"] = {
                        "actions_total": total,
                        "actions_success": success,
                        "success_rate": round(success / total, 3) if total else 0.0,
                    }
            with self.run_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception:
            pass

    def _apply_failure_backoff(self, action_key: str) -> None:
        count = self.failure_counts.get(action_key, 0)
        if count >= 5:
            self.status_tracker.set_cooldown(self.account_name, action_key, 86400)
            os.environ["ENABLE_POSTING"] = "0"
            self.logger.error("Repeated failures for %s; pausing 24h and forcing read-only mode", action_key)
            self._send_alert(f"Repeated failures for {action_key} on {self.account_name}. Posting disabled.")
        elif count >= 3:
            self.status_tracker.set_cooldown(self.account_name, action_key, 3600)
            self.logger.warning("Repeated failures for %s; pausing 1h", action_key)
        elif count >= 1:
            self.status_tracker.set_cooldown(self.account_name, action_key, 300)

    def _send_alert(self, message: str) -> None:
        host = os.getenv("SMTP_HOST")
        port = int(os.getenv("SMTP_PORT", "587"))
        username = os.getenv("SMTP_USERNAME")
        password = os.getenv("SMTP_PASSWORD")
        to_email = os.getenv("ALERT_EMAIL_TO")
        if not all([host, username, password, to_email]):
            return
        try:
            subject = f"[Automation Alert] {self.account_name}"
            body = f"Subject: {subject}\n\n{message}\n"
            with smtplib.SMTP(host, port, timeout=10) as server:
                server.starttls()
                server.login(username, password)
                server.sendmail(username, [to_email], body)
        except Exception as exc:
            self.logger.warning("Failed to send alert email: %s", exc)
