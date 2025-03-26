"""
Whisper Flight AI - Logging System
Version: 5.0.2
Purpose: Centralized, configurable logging for all components
Last Updated: March 25, 2025
Author: Your Name

Changes in this version:
- Reduced console logging to ERROR level for cleaner output
"""

import os
import sys
import time
import logging
from logging.handlers import RotatingFileHandler
import traceback
from config_manager import config

class LoggingSystem:
    def __init__(self):
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.log_dir = os.path.join(self.script_dir, "logs")
        self.log_path = os.path.join(self.log_dir, "whisper_flight.log")
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        log_level_str = config.get("Logging", "level", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        max_bytes = config.getint("Logging", "max_size_mb", 10) * 1024 * 1024
        backup_count = config.getint("Logging", "file_rotation", 7)
        logger = logging.getLogger()
        logger.setLevel(log_level)
        if logger.handlers:
            for handler in logger.handlers:
                logger.removeHandler(handler)
        file_handler = RotatingFileHandler(
            self.log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.INFO)
        logger.addHandler(file_handler)
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(logging.ERROR)
        logger.addHandler(console_handler)
        logging.info(f"Whisper Flight AI v{config.get('Version', 'app_version', '5.1.6')} logging initialized")
    
    def get_startup_info(self):
        import platform
        info = [
            f"Whisper Flight AI v{config.get('Version', 'app_version', '5.1.6')} starting up",
            f"Python version: {platform.python_version()}",
            f"Platform: {platform.platform()}",
            f"Debug mode: {'Enabled' if config.getboolean('General', 'debug_mode', False) else 'Disabled'}",
            f"Distributed mode: {'Enabled' if config.getboolean('General', 'distributed_mode', False) else 'Disabled'}",
            f"Default AI provider: {config.get('AI', 'default_provider', 'openai')}",
            f"STT engine: {config.get('Speech', 'stt_engine', 'whisper')}",
            f"TTS engine: {config.get('Speech', 'tts_engine', 'elevenlabs')}"
        ]
        return "\n".join(info)
    
    def log_startup(self):
        startup_info = self.get_startup_info()
        for line in startup_info.split("\n"):
            logging.info(line)
    
    def log_exception(self, e, context=""):
        exc_type, exc_value, exc_tb = sys.exc_info()
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        tb_text = "".join(tb_lines)
        if context:
            logging.error(f"Exception in {context}: {str(e)}")
        else:
            logging.error(f"Exception: {str(e)}")
        logging.debug(f"Traceback:\n{tb_text}")
        return tb_text
    
    def create_session_log(self):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        session_log_path = os.path.join(self.log_dir, f"session_{timestamp}.log")
        session_handler = logging.FileHandler(session_log_path, encoding='utf-8')
        session_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        session_handler.setFormatter(session_formatter)
        logging.getLogger().addHandler(session_handler)
        logging.info(f"Session log created at {session_log_path}")
        return session_log_path, session_handler
    
    def close_session_log(self, session_handler):
        if session_handler:
            logging.info("Closing session log")
            logging.getLogger().removeHandler(session_handler)
            session_handler.close()

logging_system = LoggingSystem()

if __name__ == "__main__":
    logging.info("Testing the logging system")
    logging_system.log_startup()
    try:
        result = 1 / 0
    except Exception as e:
        logging_system.log_exception(e, "division test")
    session_path, session_handler = logging_system.create_session_log()
    logging.info("This message should appear in both logs")
    logging_system.close_session_log(session_handler)