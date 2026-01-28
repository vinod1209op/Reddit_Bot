"""
Purpose: Typed configuration models with validation.
Constraints: Pure models; no file I/O or side effects.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field, ConfigDict


class ApiCreds(BaseModel):
    model_config = ConfigDict(extra="allow")
    client_id: str = ""
    client_secret: str = ""
    username: str = ""
    password: str = ""
    user_agent: str = "bot:reddit-automation:v1.0"


class SeleniumSettings(BaseModel):
    model_config = ConfigDict(extra="allow")
    headless: bool = False
    wait_time: int = 10
    browser: str = "chrome"
    chrome_binary: str = ""
    chromedriver_path: str = ""
    chromedriver_version: str = ""
    cookie_file: str = "data/cookies_account1.pkl"
    use_undetected: bool = True
    stealth_mode: bool = True
    randomize_fingerprint: bool = True


class BotSettings(BaseModel):
    model_config = ConfigDict(extra="allow")
    mode: str = "selenium"
    enable_posting: bool = False
    mock_mode: bool = False
    use_llm: bool = False
    log_level: str = "INFO"
    human_approval: str = "all"
    auto_submit_limit: int = 0
    subreddits: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)


class AutomationSettings(BaseModel):
    model_config = ConfigDict(extra="allow")
    max_daily_sessions: int = 3
    session_cooldown: int = 7200
    headless_mode: bool = False
    human_delays: bool = True
    randomization_factor: float = 0.3


class SafetySettings(BaseModel):
    model_config = ConfigDict(extra="allow")
    enable_rate_limiting: bool = True
    enable_cookie_login: bool = True
    enable_activity_logging: bool = True
    max_consecutive_errors: int = 3


class ActivitySchedule(BaseModel):
    model_config = ConfigDict(extra="allow")
    timezone: str = "America/Los_Angeles"
    login_method: str = "cookies_then_google"
    time_windows: List[Dict[str, Any]] = Field(default_factory=list)
    activity_mix: Dict[str, Any] = Field(default_factory=dict)
    profiles: Dict[str, Any] = Field(default_factory=dict)
    randomization: Dict[str, Any] = Field(default_factory=dict)
    safety_limits: Dict[str, Any] = Field(default_factory=dict)
    humanization: Dict[str, Any] = Field(default_factory=dict)
    subreddit_creation: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "profile": "conservative",
            "max_total_subreddits": 3,
            "cooldown_days": 7,
            "require_manual_review": True,
            "allow_retries": False,
        }
    )
    post_scheduling: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "profile": "low_frequency",
            "max_posts_per_day": 1,
            "max_posts_per_week": 3,
            "dry_run": True,
            "schedule_window_local": {"start": "09:00", "end": "21:00"},
        }
    )
    moderation: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "auto_approve_trusted": True,
            "remove_spam": True,
            "setup_on_creation": True,
            "auto_remove_reported": False,
            "notify_on_flags": True,
            "max_actions_per_run": 25,
        }
    )


class SubredditCreation(BaseModel):
    model_config = ConfigDict(extra="allow")
    default_profile: str = "conservative"
    profiles: Dict[str, Any] = Field(default_factory=dict)
    template_sets: Dict[str, Any] = Field(default_factory=dict)


class PostScheduling(BaseModel):
    model_config = ConfigDict(extra="allow")
    posting_settings: Dict[str, Any] = Field(default_factory=dict)
    content_strategy: Dict[str, Any] = Field(default_factory=dict)
    subreddit_distribution: Dict[str, Any] = Field(default_factory=dict)
    safety_settings: Dict[str, Any] = Field(default_factory=dict)
    automation_settings: Dict[str, Any] = Field(default_factory=dict)


class RateLimits(BaseModel):
    model_config = ConfigDict(extra="allow")
    comment: Dict[str, Any] = Field(default_factory=dict)
    post: Dict[str, Any] = Field(default_factory=dict)
