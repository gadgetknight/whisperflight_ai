"""
Whisper Flight AI - AI Provider Module
Version: 5.1.6
Purpose: Handles multiple AI providers with fallback chain
Last Updated: March 29, 2025, 12:30 UTC
Author: Your Name

Changes in this version:
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
from config_manager import config

class AIProvider(ABC):
    """Abstract base class for AI service providers."""
    
    def __init__(self):
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
    
    def _handle_api_error(self, error, endpoint):
        """Handle API errors and log appropriately."""
        if isinstance(error, requests.exceptions.Timeout):
            self.logger.error(f"{self.get_name()} API timeout for {endpoint}")
            return f"I couldn't connect to {self.get_name()} in time. Please try again."
        elif isinstance(error, requests.exceptions.ConnectionError):
            self.logger.error(f"{self.get_name()} API connection error for {endpoint}")
            return f"I'm having trouble connecting to {self.get_name()}. Please check your internet connection."
        elif isinstance(error, requests.exceptions.HTTPError):
            self.logger.error(f"{self.get_name()} API HTTP error for {endpoint}: {error}")
            return f"There was a problem with the {self.get_name()} service. Please try again later."
        else:
            self.logger.error(f"{self.get_name()} API error for {endpoint}: {error}")
            return f"Something went wrong with {self.get_name()}. Please try again."

class GrokProvider(AIProvider):
    """Implements the Grok AI provider."""
    
    def __init__(self):
        super().__init__()
        self.api_key = config.get_api_key("grok")
        self.model = config.get("API_Models", "grok_model", "grok-beta")
        self.api_url = "https://api.x.ai/v1/chat/completions"
    
    def get_name(self):
        return "Grok"
    
    def generate_response(self, messages):
        """Generate a response from Grok."""
        if not self.api_key:
            self.logger.error("Grok API key not found")
            return "Grok API key is missing. Please check your configuration."
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
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
                timeout=10
            )
            response.raise_for_status()
            response_json = response.json()
            content = response_json["choices"][0]["message"]["content"].strip()
            self.logger.info(f"Grok response generated successfully ({len(content)} chars)")
            return content
        except Exception as e:
            return self._handle_api_error(e, "chat/completions")

class OpenAIProvider(AIProvider):
    """Implements the OpenAI provider."""
    
    def __init__(self):
        super().__init__()
        self.api_key = config.get_api_key("openai")
        self.model = config.get("API_Models", "openai_model", "gpt-4o")
        self.api_url = "https://api.openai.com/v1/chat/completions"
    
    def get_name(self):
        return "OpenAI"
    
    def generate_response(self, messages):
        """Generate a response from OpenAI."""
        if not self.api_key:
            self.logger.error("OpenAI API key not found")
            return "OpenAI API key is missing. Please check your configuration."
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
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
                timeout=10
            )
            response.raise_for_status()
            response_json = response.json()
            content = response_json["choices"][0]["message"]["content"].strip()
            self.logger.info(f"OpenAI response generated successfully ({len(content)} chars)")
            return content
        except Exception as e:
            return self._handle_api_error(e, "chat/completions")

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
        else:
            logging.error(f"Unknown AI provider: {provider_name}")
            return None

class AIManager:
    """Manages multiple AI providers with fallback chain."""
    
    def __init__(self):
        self.logger = logging.getLogger("AIManager")
        self.default_provider = "openai"  # Set OpenAI as default
        self.active_providers = config.get_active_providers()
        self.providers = {}
        
        # Initialize only OpenAI and Grok providers
        for provider_name in ["openai", "grok"]:
            if provider_name in self.active_providers:
                provider = AIProviderFactory.create_provider(provider_name)
                if provider:
                    self.providers[provider_name] = provider
        
        if not self.providers:
            self.logger.error("No AI providers available")
        else:
            self.logger.info(f"AI Manager initialized with providers: {', '.join(self.providers.keys())}")
    
    def generate_response(self, messages, provider=None):
        """Generate a response using the specified or default provider, with fallback."""
        if not self.providers:
            return "No AI providers are available. Please check your configuration."
        
        provider_name = provider or self.default_provider
        
        if provider_name not in self.providers:
            provider_name = "openai"  # Fallback to OpenAI
            self.logger.warning(f"Requested provider not available, using {provider_name} instead")
        
        self.logger.info(f"Generating response with {provider_name}")
        result = self.providers[provider_name].generate_response(messages)
        
        error_indicators = [
            "API key is missing",
            "I couldn't connect",
            "I'm having trouble connecting",
            "There was a problem with",
            "Something went wrong with"
        ]
        
        if any(indicator in result for indicator in error_indicators):
            self.logger.warning(f"{provider_name} failed, trying fallback")
            fallback_name = "grok" if provider_name == "openai" else "openai"
            if fallback_name in self.providers:
                self.logger.info(f"Trying fallback provider: {fallback_name}")
                fallback_result = self.providers[fallback_name].generate_response(messages)
                if not any(indicator in fallback_result for indicator in error_indicators):
                    self.logger.info(f"Fallback to {fallback_name} successful")
                    return fallback_result
            
            self.logger.error("All AI providers failed")
            return "I'm having trouble connecting to AI services right now. Please check your internet connection and try again later."
        
        return result

# Singleton instance
ai_manager = AIManager()

# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_messages = [
        {"role": "system", "content": "You are a helpful flight assistant."},
        {"role": "user", "content": "What's the weather like in San Francisco?"}
    ]
    for provider in ["openai", "grok"]:
        print(f"\nTesting {provider}...")
        response = ai_manager.generate_response(test_messages, provider)
        print(f"Response: {response}")