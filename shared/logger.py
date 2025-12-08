import logging
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

class UnifiedLogger:
    """Logger that works for both API and Selenium"""
    
    # Class-level tracker to avoid duplicate handlers
    _initialized_loggers = set()
    
    def __init__(self, name: str = "reddit_bot", log_level: str = "INFO"):
        self.logger = logging.getLogger(name)
        
        # Convert string level to logging constant
        level = getattr(logging, log_level.upper(), logging.INFO)
        self.logger.setLevel(level)
        
        # Only add handlers if this logger hasn't been initialized yet
        if name not in UnifiedLogger._initialized_loggers:
            # Create logs directory relative to project root
            project_root = Path(__file__).parent.parent
            logs_dir = project_root / "logs"
            logs_dir.mkdir(exist_ok=True)
            
            # Use daily log files instead of per-instance
            timestamp = datetime.now().strftime("%Y%m%d")
            log_file = logs_dir / f"bot_{timestamp}.log"
            
            # File handler
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(level)
            
            # Console handler with different format
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)  # Console shows INFO and above
            
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
            
            UnifiedLogger._initialized_loggers.add(name)
            self.logger.info(f"Logger initialized. Log file: {log_file}")
        else:
            self.logger.debug(f"Reusing existing logger: {name}")
    
    def get_logger(self) -> logging.Logger:
        """Get the underlying logger instance"""
        return self.logger
    
    def log_activity(self, action: str, details: Dict[str, Any], level: str = "INFO"):
        """Log specific bot activities with structured data"""
        log_level = getattr(logging, level.upper(), logging.INFO)
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details
        }
        
        self.logger.log(log_level, f"ACTIVITY: {json.dumps(log_entry)}")
    
    def log_security_event(self, event_type: str, details: Dict[str, Any]):
        """Log security-related events"""
        self.logger.warning(f"SECURITY: {event_type} - {json.dumps(details)}")
    
    def log_performance(self, operation: str, duration: float):
        """Log performance metrics"""
        self.logger.info(f"PERFORMANCE: {operation} took {duration:.2f}s")