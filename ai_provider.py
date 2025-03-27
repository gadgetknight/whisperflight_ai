"""
Whisper Flight AI - AI Provider Module
Version: 5.1.6 (Corrected for key loading)
Purpose: Handles multiple AI providers with fallback chain
Last Updated: March 26, 2025
Author: Your Name

Changes based on debugging:
- Removed API key storage from __init__ in GrokProvider and OpenAIProvider.
- Moved API key fetching into generate_response methods for just-in-time loading.
- Removed Claude provider
- Set OpenAI as default API
"""

import os
import sys
import time
import logging
import json
import requests
from abc import ABC, abstractmethod
from config_manager import config # Assuming config is the initialized singleton

class AIProvider(ABC):
    """Abstract base class for AI service providers."""
    
    def __init__(self):
        # Initialize logger and common AI settings
        self.logger = logging.getLogger(self.__class__.__name__)
        self.max_tokens = config.getint("AI", "max_tokens", 150)
        self.temperature = config.getfloat("AI", "temperature", 0.7)
    
    @abstractmethod
    def generate_response(self, messages):
        """Generate a response from the AI provider."""
        pass
    
    @abstractmethod
    def get_name(self):
        """Get the name of the AI provider."""
        pass
    
    # _handle_api_error remains the same...
    def _handle_api_error(self, error, endpoint):
        """Handle API errors and log appropriately."""
        provider_name = self.get_name() # Get name dynamically
        if isinstance(error, requests.exceptions.Timeout):
            self.logger.error(f"{provider_name} API timeout for {endpoint}")
            return f"I couldn't connect to {provider_name} in time. Please try again."
        elif isinstance(error, requests.exceptions.ConnectionError):
            self.logger.error(f"{provider_name} API connection error for {endpoint}")
            return f"I'm having trouble connecting to {provider_name}. Please check your internet connection."
        elif isinstance(error, requests.exceptions.HTTPError):
            # Log status code if available
            status_code = error.response.status_code if error.response is not None else 'N/A'
            self.logger.error(f"{provider_name} API HTTP error for {endpoint} ({status_code}): {error}")
            # Provide more specific message for common auth errors
            if status_code == 401:
                 return f"Authentication failed for {provider_name}. Please check your API key."
            elif status_code == 429:
                 return f"{provider_name} API rate limit reached. Please wait or check your plan."
            else:
                 return f"There was a problem with the {provider_name} service (HTTP {status_code}). Please try again later."
        else:
            # Catch other potential exceptions during API call
            self.logger.error(f"{provider_name} API error for {endpoint}: {error}", exc_info=True) # Log traceback for unexpected errors
            return f"Something went wrong while communicating with {provider_name}. Please try again."

class GrokProvider(AIProvider):
    """Implements the Grok AI provider."""
    
    def __init__(self):
        super().__init__()
        # No self.api_key stored here!
        self.model = config.get("API_Models", "grok_model", "grok-beta")
        self.api_url = "https://api.x.ai/v1/chat/completions"
    
    def get_name(self):
        return "Grok"
    
    def generate_response(self, messages):
        """Generate a response from Grok."""
        # Fetch API key just before use
        api_key = config.get_api_key("grok") 
        if not api_key: 
            self.logger.error("Grok API key not found in environment or .env file.")
            # Return the specific error message
            return "Grok API key is missing. Please check your configuration." 

        headers = {
            "Authorization": f"Bearer {api_key}", 
            "Content-Type": "application/json"
        }
            
        data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=data,
                timeout=15 # Slightly increased timeout
            )
            response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
            response_json = response.json()
            
            # Add checks for expected response structure
            if "choices" not in response_json or not response_json["choices"]:
                 self.logger.error("Grok API response missing 'choices'.")
                 return f"Received an unexpected response from {self.get_name()}."
            if "message" not in response_json["choices"][0] or "content" not in response_json["choices"][0]["message"]:
                 self.logger.error("Grok API response missing 'message' or 'content'.")
                 return f"Received an unexpected response from {self.get_name()}."

            content = response_json["choices"][0]["message"]["content"].strip()
            self.logger.info(f"Grok response generated successfully ({len(content)} chars)")
            return content
        except Exception as e:
            # Use the refined error handler
            return self._handle_api_error(e, "chat/completions")

class OpenAIProvider(AIProvider):
    """Implements the OpenAI provider."""
    
    def __init__(self):
        super().__init__()
        # No self.api_key stored here!
        self.model = config.get("API_Models", "openai_model", "gpt-4o")
        self.api_url = "https://api.openai.com/v1/chat/completions"
    
    def get_name(self):
        return "OpenAI"
    
    def generate_response(self, messages):
        """Generate a response from OpenAI."""
        # Fetch API key just before use
        api_key = config.get_api_key("openai") 
        if not api_key: 
            self.logger.error("OpenAI API key not found in environment or .env file.")
            # Return the specific error message
            return "OpenAI API key is missing. Please check your configuration." 

        headers = {
            "Authorization": f"Bearer {api_key}", 
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=data,
                timeout=15 # Slightly increased timeout
            )
            response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
            response_json = response.json()

            # Add checks for expected response structure (similar to Grok)
            if "choices" not in response_json or not response_json["choices"]:
                 self.logger.error("OpenAI API response missing 'choices'.")
                 return f"Received an unexpected response from {self.get_name()}."
            if "message" not in response_json["choices"][0] or "content" not in response_json["choices"][0]["message"]:
                 self.logger.error("OpenAI API response missing 'message' or 'content'.")
                 return f"Received an unexpected response from {self.get_name()}."
                 
            content = response_json["choices"][0]["message"]["content"].strip()
            self.logger.info(f"OpenAI response generated successfully ({len(content)} chars)")
            return content
        except Exception as e:
             # Use the refined error handler
            return self._handle_api_error(e, "chat/completions")

# --- AIProviderFactory (Keep as is) ---
class AIProviderFactory:
    """Factory class for creating AI provider instances."""
    
    @staticmethod
    def create_provider(provider_name):
        """Create an instance of the specified AI provider."""
        provider_name = provider_name.lower()
        
        if provider_name == "grok":
            return GrokProvider()
        elif provider_name == "openai":
            return OpenAIProvider()
        # Removed Claude check
        else:
            logging.error(f"Attempted to create unknown AI provider: {provider_name}")
            return None

# --- AIManager (Keep as is, relies on corrected providers) ---
class AIManager:
    """Manages multiple AI providers with fallback chain."""
    
    def __init__(self):
        self.logger = logging.getLogger("AIManager")
        self.default_provider = config.get("AI", "default_provider", "openai") # Read default from config
        self.active_providers_list = config.get_active_providers() # Get list ["openai", "grok"]
        self.providers = {}
        
        # Initialize configured providers
        for provider_name in self.active_providers_list:
            provider = AIProviderFactory.create_provider(provider_name)
            if provider:
                self.providers[provider_name] = provider
            else:
                 # Log if an active provider couldn't be created
                 self.logger.warning(f"Failed to create configured provider: {provider_name}")
        
        # Ensure default provider is valid and available
        if self.default_provider not in self.providers:
             self.logger.warning(f"Default provider '{self.default_provider}' not available or configured.")
             # Fallback to the first available provider if default is bad
             if self.providers:
                  self.default_provider = next(iter(self.providers))
                  self.logger.warning(f"Setting default provider to first available: '{self.default_provider}'")
             else:
                  # If NO providers loaded, set default to None or handle error state
                  self.default_provider = None 
                  self.logger.error("CRITICAL: No AI providers could be initialized!")

        if self.providers:
             self.logger.info(f"AI Manager initialized. Active providers: {', '.join(self.providers.keys())}. Default: {self.default_provider}")
        # No else needed, error logged above if providers is empty
    
    def generate_response(self, messages, provider=None):
        """Generate a response using the specified or default provider, with fallback."""
        if not self.providers or not self.default_provider: # Check if any providers loaded
            return "No AI providers are available or configured correctly. Please check your configuration and API keys."
        
        provider_name_to_use = provider or self.default_provider
        
        # Check if the specifically requested (or default) provider is actually available
        if provider_name_to_use not in self.providers:
            self.logger.warning(f"Requested provider '{provider_name_to_use}' not available, falling back to default: {self.default_provider}")
            provider_name_to_use = self.default_provider
            # If even the default isn't available (shouldn't happen with __init__ check, but belt-and-suspenders)
            if provider_name_to_use not in self.providers:
                 self.logger.error("Default AI provider is not available. Cannot generate response.")
                 return "The configured default AI provider is not available."


        self.logger.info(f"Attempting response generation with: {provider_name_to_use}")
        primary_provider = self.providers[provider_name_to_use]
        result = primary_provider.generate_response(messages)
        
        # Define error indicators (check if response STARTS with these for more robustness)
        error_indicators = [
            "API key is missing",
            "I couldn't connect",
            "I'm having trouble connecting",
            "There was a problem with",
            "Something went wrong",
            "Authentication failed",
            "API rate limit reached",
            "Received an unexpected response",
        ]
        
        # Check if the result indicates an error
        is_error = any(result.startswith(indicator) for indicator in error_indicators)

        if is_error:
            self.logger.warning(f"{provider_name_to_use} failed with: '{result}'. Attempting fallback.")
            
            # Determine fallback provider (simple toggle for 2 providers)
            fallback_name = None
            if len(self.providers) > 1:
                 # Find a provider that isn't the one that just failed
                 for name in self.providers:
                      if name != provider_name_to_use:
                           fallback_name = name
                           break # Use the first alternative found

            if fallback_name:
                self.logger.info(f"Trying fallback provider: {fallback_name}")
                fallback_provider = self.providers[fallback_name]
                fallback_result = fallback_provider.generate_response(messages)
                
                # Check if fallback also resulted in an error
                is_fallback_error = any(fallback_result.startswith(indicator) for indicator in error_indicators)
                
                if not is_fallback_error:
                    self.logger.info(f"Fallback to {fallback_name} successful.")
                    return fallback_result # Return successful fallback response
                else:
                     self.logger.error(f"Fallback provider {fallback_name} also failed with: '{fallback_result}'")
                     # Return the error from the fallback provider
                     return fallback_result 
            else:
                 self.logger.error("No fallback provider available.")
                 # Return the original error if no fallback exists or was attempted
                 return result 
        
        # If primary attempt was not an error, return the result
        return result

# --- Singleton Instance ---
ai_manager = AIManager()

# --- Example Usage (Keep as is) ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_messages = [
        {"role": "system", "content": "You are a helpful flight assistant."},
        {"role": "user", "content": "What's the weather like in San Francisco?"}
    ]
    
    # Test default provider (or specified if needed)
    print(f"\nTesting default provider ({ai_manager.default_provider})...")
    response = ai_manager.generate_response(test_messages)
    print(f"Response: {response}")

    # Optionally test specific providers if multiple are configured
    if len(ai_manager.providers) > 1:
        for provider_name in ai_manager.providers:
             if provider_name != ai_manager.default_provider: # Test non-default ones
                 print(f"\nTesting specific provider: {provider_name}...")
                 response = ai_manager.generate_response(test_messages, provider=provider_name)
                 print(f"Response: {response}")