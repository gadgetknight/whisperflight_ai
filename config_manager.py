"""
Whisper Flight AI - Configuration Manager
Version: 5.0.0
Purpose: Centralized configuration management for AI Flight Tour Guide
Last Updated: March 25, 2025, 09:00 UTC
Author: Your Name

This module handles loading, validating, and accessing application configuration.
It provides a singleton ConfigManager that can be imported across all modules.
"""

import os
from dotenv import load_dotenv
import sys
import logging
import configparser
from pathlib import Path
import json

class ConfigManager:
    """Singleton configuration manager for the Whisper AI application."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.logger = logging.getLogger("ConfigManager")
        self.config = configparser.ConfigParser()
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(self.script_dir, "config.ini")
        self._load_config()
        self._initialized = True
        
    def _load_config(self):
        """Load configuration from file, creating default if not exists."""
        if not os.path.exists(self.config_path):
            self.logger.warning(f"Config file not found at {self.config_path}, creating default")
            self._create_default_config()
        
        try:
            self.config.read(self.config_path)
            self._validate_config()
            self._load_api_keys()
            self.logger.info(f"Configuration loaded from {self.config_path}")
        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}")
            self.logger.info("Falling back to default configuration")
            self._create_default_config()
    
    def _create_default_config(self):
        """Create a default configuration file."""
        self.config["Version"] = {
            "app_version": "5.0.0",
            "config_version": "1.0",
            "copyright": "Copyright © 2025. All rights reserved."
        }
        
        self.config["General"] = {
            "debug_mode": "False",
            "distributed_mode": "False",
            "remote_address": "127.0.0.1",
            "remote_port": "9000"
        }
        
        self.config["AI"] = {
            "default_provider": "grok",
            "active_providers": "grok,openai,claude",
            "context_length": "10",
            "max_tokens": "150",
            "temperature": "0.7"
        }
                       
        self.config["API_Models"] = {
            "grok_model": "grok-beta",
            "openai_model": "gpt-4o",
            "whisper_model": "base"
        }
        
        self.config["Speech"] = {
            "stt_engine": "whisper",
            "tts_engine": "elevenlabs",
            "noise_threshold": "0.2",
            "silence_duration": "0.5",
            "recording_seconds": "5"
        }
        
        self.config["Audio"] = {
            "input_device": "default",
            "output_device": "default",
            "elevenlabs_voice_id": "pNInz6obpgDQGcFmaJgB",
            "google_voice_name": "en-US-Neural2-F",
            "volume": "1.0",
            "playback_speed": "1.0"
        }
        
        self.config["Controls"] = {
            "joystick_enabled": "True",
            "joystick_device": "0",
            "sky_tour_button": "2",
            "where_am_i_button": "3",
            "question_button": "4",
            "deactivate_button": "5",
            "keyboard_enabled": "True",
            "sky_tour_key": "F8",
            "where_am_i_key": "F9",
            "question_key": "F10",
            "deactivate_key": "F11"
        }
        
        self.config["SimConnect"] = {
            "update_frequency": "2",
            "cache_timeout": "30",
            "geo_cache_size": "50"
        }
        
        self.config["EFB"] = {
            "enabled": "False",
            "ui_scale": "1.0",
            "opacity": "0.8",
            "position_x": "0.7",
            "position_y": "0.3"
        }
        
        self.config["Logging"] = {
            "level": "INFO",
            "file_rotation": "7",
            "max_size_mb": "10"
        }
        
        with open(self.config_path, 'w') as config_file:
            self.config.write(config_file)
    
    def _validate_config(self):
        """Validate that all required configuration sections and keys exist."""
        required_sections = [
            "Version", "General", "AI", "API_Keys", "API_Models", 
            "Speech", "Audio", "Controls", "SimConnect", "EFB", "Logging"
        ]
        
        for section in required_sections:
            if section not in self.config:
                self.logger.warning(f"Missing section {section} in config, adding default")
                self._create_default_config()
                return
    
    def get(self, section, key, fallback=None):
        """Get a configuration value by section and key."""
        try:
            return self.config.get(section, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            self.logger.warning(f"Config value {section}.{key} not found, using fallback: {fallback}")
            return fallback
    
    def getboolean(self, section, key, fallback=False):
        """Get a boolean configuration value."""
        try:
            return self.config.getboolean(section, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            self.logger.warning(f"Boolean config {section}.{key} not found, using fallback: {fallback}")
            return fallback
    
    def getint(self, section, key, fallback=0):
        """Get an integer configuration value."""
        try:
            return self.config.getint(section, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            self.logger.warning(f"Integer config {section}.{key} not found, using fallback: {fallback}")
            return fallback
    
    def getfloat(self, section, key, fallback=0.0):
        """Get a float configuration value."""
        try:
            return self.config.getfloat(section, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            self.logger.warning(f"Float config {section}.{key} not found, using fallback: {fallback}")
            return fallback
    
    def get_api_key(self, provider):
        """Get the API key for a specific provider from environment variables."""
         # Construct the environment variable name (e.g., "GROK_KEY", "OPENAI_KEY")
        key_name = f"{provider.upper()}_KEY" 
        api_key = os.getenv(key_name) # Use os.getenv to read the environment variable

        if api_key:
            Optional: Log only part of the key for verification, NEVER the full key
            self.logger.debug(f"Found API key for {provider} in environment.")
            return api_key
        else:
            self.logger.warning(f"API key for {provider} (variable: {key_name}) not found in environment variables or .env file.")
            return "" # Return empty string if not found
    
    def get_active_providers(self):
        """Get list of active AI providers."""
        providers_str = self.get("AI", "active_providers", "grok,openai,claude")
        return [p.strip() for p in providers_str.split(",") if p.strip()]
    
    def set(self, section, key, value):
        """Set a configuration value."""
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = str(value)
    
    def save(self):
        """Save the current configuration to file."""
        try:
            with open(self.config_path, 'w') as config_file:
                self.config.write(config_file)
            self.logger.info(f"Configuration saved to {self.config_path}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")
            return False

# Create a singleton instance
config = ConfigManager()

# Example usage:
if __name__ == "__main__":
    # Setup basic logging for the example
    logging.basicConfig(level=logging.INFO)
    
    # Access configuration values
    print(f"Active AI provider: {config.get('AI', 'default_provider')}")
    print(f"Debug mode: {config.getboolean('General', 'debug_mode')}")
    print(f"Active providers: {config.get_active_providers()}")
    
    # Test setting and saving a value
    config.set("General", "debug_mode", "True")
    config.save()