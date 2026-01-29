"""
Purpose: Centralized logging configuration with structured output support.
Constraints: Logging only; no business logic.
"""

# Imports
import logging
import sys
import json
import os
import threading
import time
import re
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from contextlib import contextmanager
from typing import Optional, Dict, Any, Union
import traceback

from microdose_study_bot.core.metrics import get_metrics

_REDACTED = "[redacted]"

_TOKEN_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bsk-or-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgho_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\beyJ[a-zA-Z0-9_\-]+=*\.[a-zA-Z0-9_\-]+=*\.[a-zA-Z0-9_\-]+=*\b"),
]

_URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_USERNAME_PATTERN = re.compile(r"(?:^|[\s/])(?:u/|/u/)([A-Za-z0-9_-]{3,20})", re.IGNORECASE)


def _redact_text(text: str) -> str:
    if not text:
        return text
    redacted = text
    for pattern in _TOKEN_PATTERNS:
        redacted = pattern.sub(_REDACTED, redacted)
    if os.getenv("REDACT_URLS", "1").lower() not in ("0", "false", "no"):
        redacted = _URL_PATTERN.sub(_REDACTED, redacted)
    if os.getenv("REDACT_USERNAMES", "1").lower() not in ("0", "false", "no"):
        redacted = _USERNAME_PATTERN.sub(lambda m: m.group(0).replace(m.group(1), _REDACTED), redacted)
    return redacted


def _redact_obj(value):
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_obj(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_obj(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_redact_obj(v) for v in value)
    return value
# Public API
class UnifiedLogger:
    """Logger that works for both API and Selenium with structured logging"""
    
    # Class-level tracker to avoid duplicate handlers
    _initialized_loggers = set()
    _lock = threading.Lock()
    _sentry_initialized = False
    _metrics_thread_started = False
    _global_initialized = False
    
    def __init__(self, name: str = "reddit_bot", log_level: Optional[str] = None):
        self.name = name
        
        # Get log level from env or parameter
        if log_level is None:
            log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        
        # Convert string level to logging constant
        level = getattr(logging, log_level, logging.INFO)
        
        with self._lock:
            self.logger = logging.getLogger(name)
            self.logger.setLevel(level)
            # Configure root logger once; all loggers propagate to root
            if not UnifiedLogger._global_initialized:
                # Create logs directory relative to repo root
                path_parts = Path(__file__).resolve().parents
                project_root = path_parts[3] if len(path_parts) > 3 else path_parts[2]
                logs_dir = project_root / "logs"
                logs_dir.mkdir(exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d")
                log_file = logs_dir / f"bot_{timestamp}.log"

                # Configure root handlers once
                self._ensure_root_logger(logs_dir, timestamp, level)

                if os.getenv("METRICS_ENABLED", "1").lower() not in ("0", "false", "no"):
                    self._start_metrics_thread(logs_dir)

                # Optional Sentry integration (once)
                self._maybe_init_sentry()

                UnifiedLogger._global_initialized = True
                self.logger.info(f"Logger initialized. Log file: {log_file}")
            # Let all loggers propagate to root handlers
            self.logger.propagate = True
    
    def _enable_json_logging(self, logs_dir: Path, timestamp: str, level: int, target_logger: Optional[logging.Logger] = None):
        """Enable JSON-structured logging to a separate file"""
        json_log_file = logs_dir / f"bot_json_{timestamp}.log"
        json_handler = RotatingFileHandler(
            json_log_file,
            maxBytes=5*1024*1024,  # 5 MB
            backupCount=3,
            encoding='utf-8'
        )
        json_handler.setLevel(level)
        if os.getenv("LOG_REDACTION", "1").lower() not in ("0", "false", "no"):
            json_handler.setFormatter(_RedactingJsonFormatter())
        
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_obj = {
                    "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno
                }
                
                # Add extra fields if present
                if hasattr(record, 'action'):
                    log_obj["action"] = _redact_obj(record.action)
                if hasattr(record, 'details'):
                    log_obj["details"] = _redact_obj(record.details)
                if hasattr(record, 'account'):
                    log_obj["account"] = _redact_obj(record.account)
                if hasattr(record, "action_type"):
                    log_obj["action_type"] = _redact_obj(record.action_type)
                if hasattr(record, "metric_snapshot"):
                    log_obj["metric_snapshot"] = _redact_obj(record.metric_snapshot)
                
                return json.dumps(log_obj)
        if not isinstance(json_handler.formatter, _RedactingJsonFormatter):
            json_handler.setFormatter(JsonFormatter())
        (target_logger or self.logger).addHandler(json_handler)
    
    def get_logger(self) -> logging.Logger:
        """Get the underlying logger instance"""
        return self.logger
    
    def log_activity(self, action: str, details: Dict[str, Any], level: str = "INFO", account: Optional[str] = None):
        """Log specific bot activities with structured data"""
        log_level = getattr(logging, level.upper(), logging.INFO)
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details
        }
        if account:
            log_entry["account"] = account
        
        # Create a log record with extra fields
        extra = {'action': action, 'details': details}
        if account:
            extra['account'] = account
        
        self.logger.log(log_level, f"ACTIVITY: {action}", extra=extra)
        get_metrics().record(f"activity.{action}", success=log_level < logging.ERROR)
    
    def log_security_event(self, event_type: str, details: Dict[str, Any]):
        """Log security-related events"""
        self.logger.warning(f"SECURITY: {event_type} - {json.dumps(details)}")
        get_metrics().record("security_event", success=False)
    
    def log_performance(self, operation: str, duration: float):
        """Log performance metrics"""
        self.logger.info(f"PERFORMANCE: {operation} took {duration:.2f}s")
        get_metrics().record(f"performance.{operation}", success=True)
    
    def log_error_with_context(self, error: Exception, context: Dict[str, Any], level: str = "ERROR"):
        """Log errors with additional context"""
        error_details = {
            "timestamp": datetime.now().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context
        }
        
        if self.logger.isEnabledFor(logging.ERROR):
            error_details["traceback"] = traceback.format_exc()
        
        self.logger.log(
            getattr(logging, level.upper(), logging.ERROR),
            f"ERROR: {type(error).__name__}: {str(error)}",
            extra={'details': error_details}
        )
        get_metrics().record_error("exception")
    
    @contextmanager
    def time_operation(self, operation_name: str):
        """Context manager for timing operations"""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.log_performance(operation_name, duration)
    
    def log_bot_action(self, 
                       action_type: str, 
                       subreddit: Optional[str] = None,
                       post_id: Optional[str] = None,
                       result: Optional[str] = None,
                       account: Optional[str] = None,
                       extra_details: Optional[Dict[str, Any]] = None):
        """Standardized bot action logging"""
        details = {
            "action_type": action_type,
            "subreddit": subreddit,
            "post_id": post_id,
            "result": result
        }
        
        if extra_details:
            details.update(extra_details)
        
        self.log_activity(
            action=f"bot.{action_type}",
            details=details,
            level="INFO",
            account=account
        )
        get_metrics().record(f"action.{action_type}", success=True)
        if str(action_type).lower() in ("post", "comment", "reply", "submit", "post_attempt"):
            get_metrics().record_post_attempt(success=True)

    def log_metrics_snapshot(self):
        """Emit a metrics snapshot into the JSON log."""
        snapshot = get_metrics().snapshot()
        self.logger.info(
            "METRICS_SNAPSHOT",
            extra={"metric_snapshot": snapshot, "_metrics_internal": True},
        )

    def _start_metrics_thread(self, logs_dir: Path) -> None:
        if UnifiedLogger._metrics_thread_started:
            return
        interval = int(os.getenv("METRICS_SNAPSHOT_INTERVAL_SEC", "60"))
        if interval <= 0:
            return
        metrics_path = logs_dir / "metrics.jsonl"

        def _loop():
            while True:
                time.sleep(interval)
                try:
                    get_metrics().write_snapshot(metrics_path)
                except Exception:
                    # Best-effort; avoid hard failures on metrics writes
                    pass

        t = threading.Thread(target=_loop, daemon=True, name="metrics-snapshotter")
        t.start()
        UnifiedLogger._metrics_thread_started = True

    def _maybe_init_sentry(self) -> None:
        if UnifiedLogger._sentry_initialized:
            return
        dsn = os.getenv("SENTRY_DSN", "").strip()
        if not dsn:
            return
        try:
            import sentry_sdk
            from sentry_sdk.integrations.logging import LoggingIntegration
        except Exception:
            return

        sentry_logging = LoggingIntegration(
            level=logging.INFO,
            event_level=logging.ERROR,
        )
        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
            release=os.getenv("SENTRY_RELEASE"),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
            integrations=[sentry_logging],
        )
        UnifiedLogger._sentry_initialized = True

    def _ensure_root_logger(self, logs_dir: Path, timestamp: str, level: int) -> None:
        if os.getenv("ENABLE_ROOT_LOGGER", "1").lower() in ("0", "false", "no"):
            return
        root_logger = logging.getLogger()
        if root_logger.handlers:
            return

        log_file = logs_dir / f"bot_{timestamp}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(level)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(
            getattr(logging, os.getenv("CONSOLE_LOG_LEVEL", "INFO").upper(), logging.INFO)
        )

        detailed_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
        )
        simple_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )

        file_handler.setFormatter(detailed_formatter)
        console_handler.setFormatter(simple_formatter)

        root_logger.setLevel(level)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

        if os.getenv('ENABLE_JSON_LOGGING', '1').lower() not in ('0', 'false', 'no'):
            self._enable_json_logging(logs_dir, timestamp, level, target_logger=root_logger)
        if os.getenv("METRICS_ENABLED", "1").lower() not in ("0", "false", "no"):
            root_logger.addHandler(_MetricsHandler())


# Convenience function for backward compatibility
def setup_logger(name: str = "reddit_bot", log_level: Optional[str] = None) -> logging.Logger:
    """Backward compatibility function - returns a logger instance"""
    return UnifiedLogger(name=name, log_level=log_level).get_logger()


class _MetricsHandler(logging.Handler):
    """Update counters and rates for every log record."""

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "_metrics_internal", False):
            return
        metrics = get_metrics()
        level_name = record.levelname.lower()
        metrics.record(f"log.{level_name}", success=record.levelno < logging.ERROR)
        if record.levelno >= logging.ERROR:
            metrics.record_error("log.error")
        action_type = getattr(record, "action_type", None) or getattr(record, "action", None)
        if action_type:
            action_str = str(action_type).lower()
            metrics.record(f"action.{action_str}", success=record.levelno < logging.ERROR)
            if action_str in ("post", "comment", "reply", "submit", "post_attempt"):
                metrics.record_post_attempt(success=record.levelno < logging.ERROR)


class _RedactingFormatter(logging.Formatter):
    def __init__(self, base: logging.Formatter):
        style = getattr(base, "style", "%")
        super().__init__(base._fmt, base.datefmt, style)
        self._base = base

    def format(self, record: logging.LogRecord) -> str:
        original_msg = record.getMessage()
        redacted_msg = _redact_text(original_msg)
        record.msg = redacted_msg
        record.args = ()
        formatted = self._base.format(record)
        record.msg = original_msg
        record.args = ()
        return formatted


class _RedactingJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_text(record.getMessage()),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if hasattr(record, "action"):
            log_obj["action"] = _redact_obj(record.action)
        if hasattr(record, "details"):
            log_obj["details"] = _redact_obj(record.details)
        if hasattr(record, "account"):
            log_obj["account"] = _redact_obj(record.account)
        if hasattr(record, "action_type"):
            log_obj["action_type"] = _redact_obj(record.action_type)
        if hasattr(record, "metric_snapshot"):
            log_obj["metric_snapshot"] = _redact_obj(record.metric_snapshot)
        return json.dumps(log_obj)
