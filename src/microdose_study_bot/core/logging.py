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
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from contextlib import contextmanager
from typing import Optional, Dict, Any, Union
import traceback

# Public API
class UnifiedLogger:
    """Logger that works for both API and Selenium with structured logging"""
    
    # Class-level tracker to avoid duplicate handlers
    _initialized_loggers = set()
    _lock = threading.Lock()
    
    def __init__(self, name: str = "reddit_bot", log_level: Optional[str] = None):
        self.name = name
        
        # Get log level from env or parameter
        if log_level is None:
            log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        
        # Convert string level to logging constant
        level = getattr(logging, log_level, logging.INFO)
        
        with self._lock:
            self.logger = logging.getLogger(name)
            
            # Only add handlers if this logger hasn't been initialized yet
            if name not in UnifiedLogger._initialized_loggers:
                self.logger.setLevel(level)
                
                # Create logs directory relative to project root
                project_root = Path(__file__).resolve().parents[2]
                logs_dir = project_root / "logs"
                logs_dir.mkdir(exist_ok=True)
                
                # Use daily log files with rotation
                timestamp = datetime.now().strftime("%Y%m%d")
                log_file = logs_dir / f"bot_{timestamp}.log"
                
                # Rotating file handler (10 MB max, keep 5 backups)
                file_handler = RotatingFileHandler(
                    log_file,
                    maxBytes=10*1024*1024,  # 10 MB
                    backupCount=5,
                    encoding='utf-8'
                )
                file_handler.setLevel(level)
                
                # Console handler with different format
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setLevel(
                    getattr(logging, os.getenv('CONSOLE_LOG_LEVEL', 'INFO').upper(), logging.INFO)
                )
                
                # Formatters
                detailed_formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
                )
                simple_formatter = logging.Formatter(
                    '%(asctime)s - %(levelname)s - %(message)s'
                )
                
                file_handler.setFormatter(detailed_formatter)
                console_handler.setFormatter(simple_formatter)
                
                self.logger.addHandler(file_handler)
                self.logger.addHandler(console_handler)
                
                # Optional JSON logging
                if os.getenv('ENABLE_JSON_LOGGING', '0').lower() in ('1', 'true', 'yes'):
                    self._enable_json_logging(logs_dir, timestamp, level)
                
                UnifiedLogger._initialized_loggers.add(name)
                self.logger.info(f"Logger initialized. Log file: {log_file}")
            else:
                self.logger.debug(f"Reusing existing logger: {name}")
    
    def _enable_json_logging(self, logs_dir: Path, timestamp: str, level: int):
        """Enable JSON-structured logging to a separate file"""
        json_log_file = logs_dir / f"bot_json_{timestamp}.log"
        json_handler = RotatingFileHandler(
            json_log_file,
            maxBytes=5*1024*1024,  # 5 MB
            backupCount=3,
            encoding='utf-8'
        )
        json_handler.setLevel(level)
        
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
                    log_obj["action"] = record.action
                if hasattr(record, 'details'):
                    log_obj["details"] = record.details
                if hasattr(record, 'account'):
                    log_obj["account"] = record.account
                
                return json.dumps(log_obj)
        
        json_handler.setFormatter(JsonFormatter())
        self.logger.addHandler(json_handler)
    
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
    
    def log_security_event(self, event_type: str, details: Dict[str, Any]):
        """Log security-related events"""
        self.logger.warning(f"SECURITY: {event_type} - {json.dumps(details)}")
    
    def log_performance(self, operation: str, duration: float):
        """Log performance metrics"""
        self.logger.info(f"PERFORMANCE: {operation} took {duration:.2f}s")
    
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


# Convenience function for backward compatibility
def setup_logger(name: str = "reddit_bot", log_level: Optional[str] = None) -> logging.Logger:
    """Backward compatibility function - returns a logger instance"""
    return UnifiedLogger(name=name, log_level=log_level).get_logger()
