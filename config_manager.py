"""
Whisper Flight AI - Configuration Manager
Version: 5.0.1 (Cleaned)
Purpose: Centralized configuration management for AI Flight Tour Guide
Last Updated: March 26, 2025
Author: Your Name

Changes:
- Loads API keys from .env file using python-dotenv.
- Removed API_Keys section from default config generation.
- Removed validation requirement for API_Keys section.
- Removed DEBUG print statements.
"""

import os
import sys
import logging
import configparser
from pathlib import Path
import json
from dotenv import load_dotenv # Import dotenv

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
            
        # Load environment variables from .env file FIRST
        load_dotenv() 
            
        self.logger = logging.getLogger("ConfigManager")
        self.config = configparser.ConfigParser()
        # Determine script directory reliably
        try:
             # If running as script or frozen exe
             self.script_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
        except NameError:
             # Fallback if __file__ is not defined (e.g., interactive session)
             self.script_dir = os.getcwd()

        self.config_path = os.path.join(self.script_dir, "config.ini")
        self._load_config()
        self._initialized = True
        
    def _load_config(self):
        """Load configuration from file, creating default if not exists."""
        if not os.path.exists(self.config_path):
            self.logger.warning(f"Config file not found at {self.config_path}, creating default")
            self._create_default_config() # This writes the file
        
        # Now try to read the config (either existing or the default just written)
        try:
            # Use read_file to handle potential encoding issues more robustly?
            with open(self.config_path, 'r', encoding='utf-8') as f:
                 self.config.read_file(f)
                 
            self._validate_config() # Validate sections exist
            self.logger.info(f"Configuration loaded successfully from {self.config_path}")
            
        except configparser.MissingSectionHeaderError as e:
             self.logger.error(f"Error loading configuration - invalid file format: {e}")
             self.logger.info("Attempting to recreate default configuration.")
             self._create_default_config() # Overwrite potentially corrupt file
             # Try reading again after recreating
             try:
                  with open(self.config_path, 'r', encoding='utf-8') as f:
                      self.config.read_file(f)
                  self._validate_config()
                  self.logger.info("Successfully loaded recreated default configuration.")
             except Exception as e_inner:
                  self.logger.critical(f"Failed to load even default configuration: {e_inner}", exc_info=True)
                  # Application might be unusable state here, raise or exit?
                  raise RuntimeError("Failed to load essential configuration.") from e_inner
                  
        except Exception as e: # Catch other potential errors during read/validate
            self.logger.error(f"Unexpected error loading configuration: {e}", exc_info=True)
            self.logger.info("Attempting fallback to default configuration.")
            self._create_default_config() # Attempt recreate
            # Try reading again
            try:
                 with open(self.config_path, 'r', encoding='utf-8') as f:
                      self.config.read_file(f)
                 self._validate_config()
                 self.logger.info("Successfully loaded recreated default configuration after error.")
            except Exception as e_final:
                 self.logger.critical(f"CRITICAL: Failed to load any configuration: {e_final}", exc_info=True)
                 raise RuntimeError("Failed to load essential configuration.") from e_final


    def _create_default_config(self):
        """Create a default configuration file."""
        # Create a new ConfigParser instance for defaults to avoid merging issues
        default_config = configparser.ConfigParser()

        default_config["Version"] = {
            "app_version": "5.0.0", # Consider updating this dynamically
            "config_version": "1.1", # Updated version
            "copyright": "Copyright © 2025. All rights reserved."
        }
        
        default_config["General"] = {
            "debug_mode": "False",
            "distributed_mode": "False", # Default to False
            "remote_address": "127.0.0.1",
            "remote_port": "9000"
        }
        
        default_config["AI"] = {
            "default_provider": "openai", # Defaulting to openai now
            "active_providers": "grok,openai", # Corrected default list
            "context_length": "10",
            "max_tokens": "150",
            "temperature": "0.7"
        }
        
        # NO [API_Keys] section here anymore
            
        default_config["API_Models"] = {
            "grok_model": "grok-beta",
            "openai_model": "gpt-4o",
            # No claude_model
            "whisper_model": "base",
            "gtts_language": "en" # Added gTTS language
        }
        
        default_config["Speech"] = {
            "stt_engine": "whisper",
            "tts_engine": "elevenlabs",
            "noise_threshold": "0.2", # Default threshold
            "silence_duration": "0.5",
            "recording_seconds": "5"
        }
        
        default_config["Audio"] = {
            "input_device": "default",
            "output_device": "default",
            "elevenlabs_voice_id": "pNInz6obpgDQGcFmaJgB", # Example default ID
            "google_voice_name": "en-US-Neural2-F", # Example Google voice
            "volume": "1.0",
            "playback_speed": "1.0"
        }
        
        default_config["Controls"] = {
            "joystick_enabled": "True",
            "joystick_device": "0",
            "sky_tour_button": "2",
            "where_am_i_button": "3",
            "question_button": "1", # Adjusted default
            "deactivate_button": "0", # Adjusted default
            "keyboard_enabled": "True",
            "sky_tour_key": "F8",
            "where_am_i_key": "F9",
            "question_key": "F10",
            "deactivate_key": "F11"
        }
        
        default_config["SimConnect"] = {
            "update_frequency": "2", # Hz
            "cache_timeout": "30", # seconds
            "geo_cache_size": "50" # entries
        }
        
        default_config["EFB"] = {
            "enabled": "False",
            "ui_scale": "1.0",
            "opacity": "0.8",
            "position_x": "0.7",
            "position_y": "0.3"
        }
        
        default_config["Logging"] = {
            "level": "INFO", # Default level
            "file_rotation": "7", # days/files
            "max_size_mb": "10" # MB
        }
        
        try:
            with open(self.config_path, 'w', encoding='utf-8') as config_file:
                default_config.write(config_file)
            self.logger.info(f"Default configuration file created/overwritten at {self.config_path}")
            # Immediately load the defaults we just wrote into the current instance
            self.config = default_config
        except IOError as e:
            self.logger.error(f"CRITICAL: Failed to write default config file: {e}", exc_info=True)
            # Handle critical error - maybe application can't run?
            raise RuntimeError(f"Unable to write configuration file to {self.config_path}") from e


    def _validate_config(self):
        """Validate that required configuration sections exist."""
        # Corrected required sections list
        required_sections = [
            "Version", "General", "AI", "API_Models", 
            "Speech", "Audio", "Controls", "SimConnect", "EFB", "Logging"
        ]
        
        missing_sections = []
        for section in required_sections:
            if section not in self.config:
                missing_sections.append(section)
                
        if missing_sections:
            self.logger.warning(f"Missing sections in config: {', '.join(missing_sections)}. Will use defaults or may cause errors.")
            # Raise an error here OR rely on fallback in get methods?
            # Raising an error might be safer if sections are critical.
            # For now, just warn. Consider raising configparser.NoSectionError if needed.
            # Example: raise configparser.NoSectionError(missing_sections[0])
            pass # Allow execution but warn

    # --- Get Methods ---

    def get(self, section, key, fallback=None):
        """Get a configuration value by section and key."""
        try:
            # Use fallback mechanism inherent in configparser.get
            return self.config.get(section, key, fallback=fallback) 
        except (configparser.NoSectionError, configparser.NoOptionError):
            # This path might be less likely if _validate_config runs first, 
            # but good as a safety net, especially if validation only warns.
            self.logger.warning(f"Config value {section}.{key} not found, using fallback: {fallback}")
            return fallback
        except ValueError as e: # Catch potential interpolation errors
             self.logger.error(f"Error getting/interpolating config value {section}.{key}: {e}")
             return fallback

    def getboolean(self, section, key, fallback=False):
        """Get a boolean configuration value."""
        try:
            # Provide fallback directly to getboolean
            return self.config.getboolean(section, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            self.logger.warning(f"Boolean config {section}.{key} not found, using fallback: {fallback}")
            return fallback
        except ValueError as e: # Catch incorrect boolean values (e.g., "maybe" instead of "True")
            self.logger.error(f"Invalid boolean value for {section}.{key}: {e}. Using fallback: {fallback}")
            return fallback
    
    def getint(self, section, key, fallback=0):
        """Get an integer configuration value."""
        try:
            return self.config.getint(section, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            self.logger.warning(f"Integer config {section}.{key} not found, using fallback: {fallback}")
            return fallback
        except ValueError as e: # Catch non-integer values
             self.logger.error(f"Invalid integer value for {section}.{key}: {e}. Using fallback: {fallback}")
             return fallback

    def getfloat(self, section, key, fallback=0.0):
        """Get a float configuration value."""
        try:
            return self.config.getfloat(section, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            self.logger.warning(f"Float config {section}.{key} not found, using fallback: {fallback}")
            return fallback
        except ValueError as e: # Catch non-float values
             self.logger.error(f"Invalid float value for {section}.{key}: {e}. Using fallback: {fallback}")
             return fallback
    
    # --- API Key Method (reads from environment) ---
    def get_api_key(self, provider):
        """Get the API key for a specific provider from environment variables."""
        key_name = f"{provider.upper()}_KEY" 
        api_key = os.getenv(key_name) 
        
        if api_key:
            self.logger.debug(f"Found API key for {provider} in environment.") 
            return api_key
        else:
            # Warning only needed once maybe? Or handled by calling code?
            # Keep warning here for now.
            self.logger.warning(f"API key for {provider} (variable: {key_name}) not found in environment.")
            return "" 

    # --- Specific Getters ---
    def get_active_providers(self):
        """Get list of active AI providers from config."""
        providers_str = self.get("AI", "active_providers", "openai,grok") # Default if missing
        # Ensure robustness against extra commas or spaces
        return [p.strip().lower() for p in providers_str.split(',') if p.strip()]

    # --- Set/Save Methods (Use with caution, ensure backups/user confirmation?) ---
    def set(self, section, key, value):
        """Set a configuration value in the runtime config object."""
        # Consider adding validation before setting
        try:
             if not self.config.has_section(section):
                 self.config.add_section(section)
                 self.logger.info(f"Added missing section [{section}] during set operation.")
             self.config.set(section, key, str(value)) # Ensure value is string
             self.logger.info(f"Config value set: [{section}] {key} = {value}")
        except Exception as e:
             self.logger.error(f"Error setting config value {section}.{key}: {e}")

    def save(self):
        """Save the current configuration object to the config.ini file."""
        # Consider adding a backup mechanism before overwriting
        try:
            with open(self.config_path, 'w', encoding='utf-8') as config_file:
                self.config.write(config_file)
            self.logger.info(f"Configuration saved to {self.config_path}")
            return True
        except IOError as e:
            self.logger.error(f"Error saving configuration file: {e}", exc_info=True)
            return False
        except Exception as e: # Catch other potential errors
             self.logger.error(f"Unexpected error saving configuration: {e}", exc_info=True)
             return False

# --- Singleton Instance ---
config = ConfigManager()

# Example usage (keep for potential direct testing)
if __name__ == "__main__":
    # Setup basic logging for the example if run directly
    logging.basicConfig(level=logging.DEBUG) 
    
    # Test reading values
    print(f"App Version: {config.get('Version', 'app_version')}")
    print(f"Debug Mode: {config.getboolean('General', 'debug_mode')}")
    print(f"Active Providers: {config.get_active_providers()}")
    print(f"Default Provider: {config.get('AI', 'default_provider')}")
    print(f"OpenAI Key Loaded: {'Yes' if config.get_api_key('openai') else 'No'}")
    print(f"ElevenLabs Voice ID: {config.get('Audio', 'elevenlabs_voice_id')}")

    # Test setting and saving (Use with caution - modifies file)
    # print("\nTesting set and save...")
    # config.set("General", "debug_mode", "True")
    # print(f"Debug mode after set: {config.getboolean('General', 'debug_mode')}")
    # save_success = config.save()
    # print(f"Save successful: {save_success}")
    # Revert change after testing?
    # config.set("General", "debug_mode", "False") 
    # config.save()