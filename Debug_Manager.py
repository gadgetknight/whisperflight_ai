"""
Whisper Flight AI - Debug Manager
Version: 5.0.1
Purpose: Centralized debugging controls and output management
Last Updated: March 30, 2025
Author: Brad Coulter

This module provides a central system for controlling debug output,
filtering verbosity levels, and handling logging across components.

Changes in this version:
- Initial implementation with support for toggling debug output
- Added quiet mode for minimal console output
- Implemented debug statistics tracking
- Added UTF-8 safe logging to handle emoji and special characters
"""

import os
import sys
import time
import logging
import threading
from enum import Enum


class DebugCategory(Enum):
    AUDIO = "AUDIO"
    STT = "STT"
    TTS = "TTS"
    AI = "AI"
    STATE = "STATE"
    NAV = "NAV"
    SIM = "SIM"
    SYSTEM = "SYSTEM"


class DebugLevel(Enum):
    NONE = 0
    ERROR = 1
    WARNING = 2
    INFO = 3
    DEBUG = 4
    TRACE = 5


class DebugManager:
    """Centralized debug manager for WhisperFlight AI."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DebugManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Set up basic variables
        self.debug_mode = True  # Start with debug enabled until UI is ready
        self.console_output = True
        self.file_output = True
        self.quiet_mode = False  # Set to True to silence most outputs

        # Set up logging
        self.logger = logging.getLogger("DebugManager")
        self.log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        self.log_file = os.path.join(
            self.log_dir, f"debug_{time.strftime('%Y%m%d_%H%M%S')}.log"
        )

        # Configure file handler with UTF-8 encoding
        self.file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        self.file_handler.setFormatter(formatter)

        # Set up logger
        self.debug_logger = logging.getLogger("DEBUG")
        self.debug_logger.setLevel(logging.DEBUG)
        self.debug_logger.addHandler(self.file_handler)

        # Don't propagate to root logger
        self.debug_logger.propagate = False

        # Default verbosity levels by category
        self.verbosity_levels = {cat: DebugLevel.INFO for cat in DebugCategory}

        # Track output stats
        self.output_count = 0
        self.start_time = time.time()

        self._initialized = True

        # Log initialization
        self.log(DebugCategory.SYSTEM, DebugLevel.INFO, "Debug Manager initialized")
        print("Debug Manager initialized")

    def toggle_debug(self):
        """Toggle debug mode on/off"""
        self.debug_mode = not self.debug_mode
        status = "enabled" if self.debug_mode else "disabled"
        message = f"Debug mode {status}"

        # Always show toggle message
        print(f"\n=== {message} ===\n")

        # Log to file
        self.debug_logger.info(message)

        return self.debug_mode

    def toggle_quiet_mode(self):
        """Toggle quiet mode (minimal console output)"""
        self.quiet_mode = not self.quiet_mode
        status = "enabled" if self.quiet_mode else "disabled"
        message = f"Quiet mode {status}"

        # Always show toggle message
        print(f"\n=== {message} ===\n")

        # Log to file
        self.debug_logger.info(message)

        return self.quiet_mode

    def set_verbosity(self, category, level):
        """
        Set verbosity level for a category

        Args:
            category: DebugCategory or string
            level: DebugLevel or int
        """
        if isinstance(category, str):
            try:
                category = DebugCategory[category.upper()]
            except KeyError:
                self.log(
                    DebugCategory.SYSTEM,
                    DebugLevel.ERROR,
                    f"Unknown debug category: {category}",
                )
                return False

        if isinstance(level, int):
            try:
                level = DebugLevel(level)
            except ValueError:
                self.log(
                    DebugCategory.SYSTEM,
                    DebugLevel.ERROR,
                    f"Invalid debug level: {level}",
                )
                return False

        self.verbosity_levels[category] = level
        return True

    def set_all_verbosity(self, level):
        """Set verbosity level for all categories"""
        if isinstance(level, int):
            try:
                level = DebugLevel(level)
            except ValueError:
                self.log(
                    DebugCategory.SYSTEM,
                    DebugLevel.ERROR,
                    f"Invalid debug level: {level}",
                )
                return False

        for cat in DebugCategory:
            self.verbosity_levels[cat] = level

        return True

    def log(self, category, level, message):
        """
        Log a debug message

        Args:
            category: DebugCategory enum or string
            level: DebugLevel enum or int
            message: Message string
        """
        # Skip if debug mode is off and this isn't an error
        if not self.debug_mode and (
            isinstance(level, DebugLevel) and level != DebugLevel.ERROR
        ):
            return

        # Convert string category to enum
        if isinstance(category, str):
            try:
                category = DebugCategory[category.upper()]
            except KeyError:
                category = DebugCategory.SYSTEM

        # Convert int level to enum
        if isinstance(level, int):
            try:
                level = DebugLevel(level)
            except ValueError:
                level = DebugLevel.INFO

        # Check verbosity level
        if level.value > self.verbosity_levels[category].value:
            return

        # Format message
        prefix = f"[{category.value}] "
        formatted = f"{prefix}{message}"

        # Log to file (always)
        log_level = logging.INFO
        if level == DebugLevel.ERROR:
            log_level = logging.ERROR
        elif level == DebugLevel.WARNING:
            log_level = logging.WARNING
        elif level == DebugLevel.DEBUG:
            log_level = logging.DEBUG

        try:
            self.debug_logger.log(log_level, formatted)
        except Exception as e:
            print(f"Error logging to file: {e}")

        # Print to console if enabled
        if self.console_output and (not self.quiet_mode or level == DebugLevel.ERROR):
            try:
                # Use safe printing to handle Unicode
                print(formatted)
            except UnicodeEncodeError:
                # Fall back to ASCII-only if necessary
                safe_msg = formatted.encode("ascii", "replace").decode("ascii")
                print(safe_msg)

        # Track stats
        self.output_count += 1

    def print_stats(self):
        """Print debug statistics"""
        elapsed = time.time() - self.start_time
        messages_per_second = self.output_count / max(1, elapsed)

        stats = (
            f"Debug Stats: {self.output_count} messages in {elapsed:.1f}s "
            f"({messages_per_second:.1f} msgs/sec)"
        )

        print(f"\n=== {stats} ===\n")
        self.debug_logger.info(stats)

    def cleanup(self):
        """Perform cleanup operations"""
        # Close file handler
        if hasattr(self, "file_handler"):
            self.file_handler.close()
            self.debug_logger.removeHandler(self.file_handler)

        # Print final stats
        self.print_stats()


# Create singleton instance
debug_manager = DebugManager()


# Helper functions for convenient logging
def log_audio(level, message):
    debug_manager.log(DebugCategory.AUDIO, level, message)


def log_stt(level, message):
    debug_manager.log(DebugCategory.STT, level, message)


def log_tts(level, message):
    debug_manager.log(DebugCategory.TTS, level, message)


def log_ai(level, message):
    debug_manager.log(DebugCategory.AI, level, message)


def log_state(level, message):
    debug_manager.log(DebugCategory.STATE, level, message)


def log_nav(level, message):
    debug_manager.log(DebugCategory.NAV, level, message)


def log_sim(level, message):
    debug_manager.log(DebugCategory.SIM, level, message)


def log_system(level, message):
    debug_manager.log(DebugCategory.SYSTEM, level, message)


# Compatibility layer for existing code
def debug_log(message, level="INFO"):
    """Legacy function to maintain compatibility with existing code"""
    debug_level = DebugLevel.INFO
    if level == "DEBUG":
        debug_level = DebugLevel.DEBUG
    elif level == "ERROR":
        debug_level = DebugLevel.ERROR
    elif level == "WARNING":
        debug_level = DebugLevel.WARNING

    debug_manager.log(DebugCategory.AUDIO, debug_level, message)


# Print startup banner when imported directly
if __name__ == "__main__":
    print("=== WhisperFlight AI Debug Manager ===")
    print("Run this module directly to test debug output.")

    # Test debug output
    debug_manager.log(DebugCategory.SYSTEM, DebugLevel.INFO, "Debug test started")
    debug_manager.log(DebugCategory.AUDIO, DebugLevel.INFO, "Audio test message")
    debug_manager.log(DebugCategory.STT, DebugLevel.DEBUG, "STT debug message")
    debug_manager.log(DebugCategory.TTS, DebugLevel.ERROR, "TTS error message")

    # Test helper functions
    log_audio(DebugLevel.INFO, "Audio helper function test")
    log_stt(DebugLevel.INFO, "STT helper function test")

    # Test unicode handling
    log_system(DebugLevel.INFO, "Unicode test: ✓ ❌ 🛫 🔊")

    # Test legacy function
    debug_log("Legacy debug_log function test", "INFO")

    # Test stats
    debug_manager.print_stats()
