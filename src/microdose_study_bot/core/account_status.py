"""
Purpose: Track account status across automation runs.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from microdose_study_bot.core.logging import UnifiedLogger


class AccountStatusTracker:
    """Tracks account health status across sessions."""

    def __init__(self, status_file: str = "data/account_status.json"):
        self.logger = UnifiedLogger("AccountStatusTracker").get_logger()
        self.status_file = Path(status_file)
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        self.status_data = self._load_status_data()

    def _load_status_data(self) -> Dict[str, Any]:
        """Load account status data from file."""
        try:
            if self.status_file.exists():
                with self.status_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.logger.info(
                        "Loaded account status for %s accounts from %s",
                        len(data),
                        self.status_file,
                    )
                    return data
        except Exception as exc:
            self.logger.warning("Could not load account status data: %s", exc)
        return {}

    def _save_status_data(self) -> None:
        """Save account status data to file."""
        try:
            with self.status_file.open("w", encoding="utf-8") as f:
                json.dump(self.status_data, f, indent=2)
            self.logger.debug("Saved account status data to %s", self.status_file)
        except Exception as exc:
            self.logger.error("Failed to save account status data: %s", exc)

    def update_account_status(self, account_name: str, status: str, details: Dict[str, Any] = None):
        """Update status for an account with details."""
        if account_name not in self.status_data:
            self.status_data[account_name] = {
                "current_status": "unknown",
                "status_history": [],
                "first_seen": datetime.now().isoformat(),
                "total_login_attempts": 0,
                "failed_login_attempts": 0,
                "last_success": None,
                "activity_stats": {},
                "cooldowns": {},
                "subreddits": {"created": [], "moderated": []},
            }

        # Update counters
        self.status_data[account_name]["total_login_attempts"] = (
            self.status_data[account_name].get("total_login_attempts", 0) + 1
        )

        if status not in ("active", "captcha"):
            self.status_data[account_name]["failed_login_attempts"] = (
                self.status_data[account_name].get("failed_login_attempts", 0) + 1
            )

        previous_status = self.status_data[account_name].get("current_status", "unknown")
        self.status_data[account_name]["current_status"] = status
        self.status_data[account_name]["last_updated"] = datetime.now().isoformat()

        if status == "active":
            self.status_data[account_name]["last_success"] = datetime.now().isoformat()

        status_entry = {
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "previous_status": previous_status,
        }
        if details:
            status_entry["details"] = details

        history = self.status_data[account_name].setdefault("status_history", [])
        history.append(status_entry)
        if len(history) > 50:
            self.status_data[account_name]["status_history"] = history[-50:]

        self._save_status_data()

        if previous_status != status:
            if status == "suspended":
                self.logger.error("🚨 ACCOUNT SUSPENDED: %s", account_name)
            elif status == "rate_limited":
                self.logger.warning("⏳ Account rate limited: %s", account_name)
            elif status == "captcha":
                self.logger.warning("🔒 CAPTCHA required: %s", account_name)
            else:
                self.logger.info(
                    "Updated account status for %s: %s -> %s",
                    account_name,
                    previous_status,
                    status,
                )

    def should_skip_account(self, account_name: str) -> bool:
        """Check if an account should be skipped based on its status."""
        if account_name not in self.status_data:
            return False

        current_status = self.status_data[account_name].get("current_status", "unknown")
        skip_statuses = ["suspended", "permanently_banned"]
        if current_status in skip_statuses:
            self.logger.warning("🚫 Skipping account %s - Status: %s", account_name, current_status)
            return True

        if current_status == "rate_limited":
            last_updated_str = self.status_data[account_name].get("last_updated")
            if last_updated_str:
                try:
                    last_updated = datetime.fromisoformat(last_updated_str)
                    hours_since = (datetime.now() - last_updated).total_seconds() / 3600
                    if hours_since < 24:
                        self.logger.info(
                            "⏳ Skipping rate-limited account %s (%.1f hours ago)",
                            account_name,
                            hours_since,
                        )
                        return True
                    self.update_account_status(account_name, "unknown", {"reason": "rate_limit_expired"})
                except Exception:
                    pass

        if current_status == "captcha":
            last_updated_str = self.status_data[account_name].get("last_updated")
            if last_updated_str:
                try:
                    last_updated = datetime.fromisoformat(last_updated_str)
                    hours_since = (datetime.now() - last_updated).total_seconds() / 3600
                    if hours_since < 6:
                        self.logger.info(
                            "🔒 Skipping account with CAPTCHA %s (%.1f hours ago)",
                            account_name,
                            hours_since,
                        )
                        return True
                    self.update_account_status(account_name, "unknown", {"reason": "captcha_cooldown_expired"})
                except Exception:
                    pass

        failed_count = self.status_data[account_name].get("failed_login_attempts", 0)
        total_count = self.status_data[account_name].get("total_login_attempts", 0)
        if total_count > 5 and failed_count >= 5 and failed_count == total_count:
            self.logger.warning("⚠️ Account %s has %s consecutive failed logins", account_name, failed_count)
            last_updated_str = self.status_data[account_name].get("last_updated")
            if last_updated_str:
                try:
                    last_updated = datetime.fromisoformat(last_updated_str)
                    hours_since = (datetime.now() - last_updated).total_seconds() / 3600
                    if hours_since < 48:
                        self.logger.info("Skipping account with consecutive failures %s", account_name)
                        return True
                except Exception:
                    pass

        return False

    def record_subreddit_creation(self, account_name: str, subreddit_name: str, success: bool) -> None:
        """Track subreddit creation attempts and apply cooldowns."""
        entry = self.status_data.setdefault(
            account_name,
            {
                "current_status": "unknown",
                "status_history": [],
                "first_seen": datetime.now().isoformat(),
                "total_login_attempts": 0,
                "failed_login_attempts": 0,
                "last_success": None,
                "activity_stats": {},
                "cooldowns": {},
                "subreddits": {"created": [], "moderated": []},
            },
        )

        stats = entry.setdefault("activity_stats", {})
        creations = stats.setdefault("subreddit_creations", [])
        creations.append(
            {
                "timestamp": datetime.now().isoformat(),
                "subreddit": subreddit_name,
                "success": bool(success),
            }
        )

        if success:
            entry.setdefault("subreddits", {}).setdefault("created", []).append(subreddit_name)
            self.update_account_status(
                account_name,
                "subreddit_created",
                {"subreddit": subreddit_name},
            )
            # Default cooldown 7 days
            cooldowns = entry.setdefault("cooldowns", {})
            cooldowns["creation"] = (
                datetime.now() + timedelta(days=7)
            ).isoformat()
        else:
            self.update_account_status(
                account_name,
                "creation_cooldown",
                {"subreddit": subreddit_name, "success": False},
            )

        self._save_status_data()

    def record_post_activity(
        self,
        account_name: str,
        subreddit: str,
        post_type: str,
        success: bool,
        daily_limit: int = 3,
    ) -> None:
        """Track posting frequency and enforce basic daily limits."""
        entry = self.status_data.setdefault(
            account_name,
            {
                "current_status": "unknown",
                "status_history": [],
                "first_seen": datetime.now().isoformat(),
                "total_login_attempts": 0,
                "failed_login_attempts": 0,
                "last_success": None,
                "activity_stats": {},
                "cooldowns": {},
                "subreddits": {"created": [], "moderated": []},
            },
        )

        stats = entry.setdefault("activity_stats", {})
        posts = stats.setdefault("posts", [])
        posts.append(
            {
                "timestamp": datetime.now().isoformat(),
                "subreddit": subreddit,
                "post_type": post_type,
                "success": bool(success),
            }
        )

        today = datetime.now().strftime("%Y-%m-%d")
        daily = stats.setdefault("posts_by_day", {})
        daily[today] = daily.get(today, 0) + (1 if success else 0)

        if daily[today] >= daily_limit:
            entry.setdefault("cooldowns", {})["posting"] = (
                datetime.now().replace(hour=23, minute=59, second=59, microsecond=0)
            ).isoformat()
            self.update_account_status(
                account_name,
                "posting_limited",
                {"daily_count": daily[today], "daily_limit": daily_limit},
            )

        self._save_status_data()

    def get_cooldown_remaining(self, account_name: str, activity_type: str) -> Optional[int]:
        """Return seconds remaining before next allowed action."""
        entry = self.status_data.get(account_name, {})
        cooldowns = entry.get("cooldowns", {})
        end = cooldowns.get(activity_type)
        if not end:
            return None
        try:
            end_dt = datetime.fromisoformat(end)
            remaining = int((end_dt - datetime.now()).total_seconds())
            return max(0, remaining)
        except Exception:
            return None

    def can_perform_action(
        self,
        account_name: str,
        action_type: str,
        subreddit: Optional[str] = None,
        daily_limit: Optional[int] = None,
    ) -> bool:
        """Check account status, cooldowns, and basic quotas before action."""
        if self.should_skip_account(account_name):
            return False

        remaining = self.get_cooldown_remaining(account_name, action_type)
        if remaining and remaining > 0:
            return False

        if action_type == "posting" and daily_limit is not None:
            entry = self.status_data.get(account_name, {})
            daily = entry.get("activity_stats", {}).get("posts_by_day", {})
            today = datetime.now().strftime("%Y-%m-%d")
            if daily.get(today, 0) >= daily_limit:
                return False

        if action_type == "creation" and subreddit:
            entry = self.status_data.get(account_name, {})
            created = entry.get("subreddits", {}).get("created", [])
            if subreddit in created:
                return False

        return True

    def set_cooldown(self, account_name: str, activity_type: str, seconds: int) -> None:
        entry = self.status_data.setdefault(
            account_name,
            {
                "current_status": "unknown",
                "status_history": [],
                "first_seen": datetime.now().isoformat(),
                "total_login_attempts": 0,
                "failed_login_attempts": 0,
                "last_success": None,
                "activity_stats": {},
                "cooldowns": {},
                "subreddits": {"created": [], "moderated": []},
            },
        )
        entry.setdefault("cooldowns", {})[activity_type] = (
            datetime.now() + timedelta(seconds=seconds)
        ).isoformat()
        self._save_status_data()

    def record_moderation_activity(
        self,
        account_name: str,
        subreddit: str,
        action: str,
        success: bool,
    ) -> None:
        """Track moderation activity and moderated subreddit relationships."""
        entry = self.status_data.setdefault(
            account_name,
            {
                "current_status": "unknown",
                "status_history": [],
                "first_seen": datetime.now().isoformat(),
                "total_login_attempts": 0,
                "failed_login_attempts": 0,
                "last_success": None,
                "activity_stats": {},
                "cooldowns": {},
                "subreddits": {"created": [], "moderated": []},
            },
        )

        stats = entry.setdefault("activity_stats", {})
        moderation = stats.setdefault("moderation", [])
        moderation.append(
            {
                "timestamp": datetime.now().isoformat(),
                "subreddit": subreddit,
                "action": action,
                "success": bool(success),
            }
        )

        if success:
            entry.setdefault("subreddits", {}).setdefault("moderated", []).append(subreddit)
            self.update_account_status(
                account_name,
                "moderation_flagged",
                {"subreddit": subreddit, "action": action},
            )

        self._save_status_data()

    def get_account_status(self, account_name: str) -> str:
        """Get current status of an account."""
        return self.status_data.get(account_name, {}).get("current_status", "unknown")

    def get_status_report(self) -> Dict[str, Any]:
        """Get a summary report of all account statuses."""
        report = {
            "total_accounts": len(self.status_data),
            "active": 0,
            "suspended": 0,
            "rate_limited": 0,
            "captcha": 0,
            "unknown": 0,
            "error": 0,
            "accounts": {},
        }

        for account_name, data in self.status_data.items():
            status = data.get("current_status", "unknown")
            report["accounts"][account_name] = status

            if status == "active":
                report["active"] += 1
            elif status == "suspended":
                report["suspended"] += 1
            elif status == "rate_limited":
                report["rate_limited"] += 1
            elif status == "captcha":
                report["captcha"] += 1
            elif status == "unknown":
                report["unknown"] += 1
            elif status == "error":
                report["error"] += 1

        return report

    def reset_account_status(self, account_name: str, reason: str = "manual_reset") -> None:
        """Reset an account's status to unknown."""
        if account_name in self.status_data:
            self.update_account_status(account_name, "unknown", {"reason": reason})
            self.logger.info("Reset account %s status to unknown", account_name)
