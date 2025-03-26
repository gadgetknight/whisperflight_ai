"""
Whisper Flight AI - State Manager
Version: 5.1.13
Purpose: Manages application state transitions and conversation flow
Last Updated: March 25, 2025
Author: Your Name

Changes in this version:
- Updated 'no' handling to stay in WAITING state, keep listening (lines 154-158)
- Retained OpenAI default and no API choice from v5.1.12 (lines 109-118)
- Kept wake word variations from v5.1.11 (lines 109-120)
- Maintained debug logs from v5.1.10 (lines 65, 112)
"""

import os
import sys
import time
import logging
import threading
from enum import Enum, auto
from collections import deque

from config_manager import config
from audio_processor import audio_processor
from ai_provider import ai_manager
from simconnect_server import sim_server
from navigation import navigation_manager
from geo_utils import geo_utils
from efb_integration import efb

class AppState(Enum):
    STANDBY = auto()
    ACTIVE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    RESPONDING = auto()
    WAITING = auto()
    NAVIGATION = auto()
    TOURING = auto()
    ERROR = auto()

class StateManager:
    def __init__(self):
        self.logger = logging.getLogger("StateManager")
        self.current_state = AppState.STANDBY
        self.previous_state = None
        self.state_change_time = time.time()
        self.active_api = "openai"  # Default to OpenAI
        self.last_narration_time = 0
        self.last_location_check = 0
        self.context_length = config.getint("AI", "context_length", 10)
        self.conversation_context = deque(maxlen=self.context_length)
        self.state_change_callbacks = []
        self.navigation_active = False
        self.last_destination = None
        self.last_dest_lat = None
        self.last_dest_lon = None
        self.state_lock = threading.RLock()
        self.logger.info(f"StateManager initialized in {self.current_state} state with default API: {self.active_api}")
        navigation_manager.tracking_callbacks.append(self)
    
    def change_state(self, new_state, reason=None):
        with self.state_lock:
            if new_state == self.current_state:
                return
            self.previous_state = self.current_state
            self.current_state = new_state
            self.state_change_time = time.time()
            if efb:
                efb.update_status(new_state.name.capitalize())
            reason_text = f" - Reason: {reason}" if reason else ""
            self.logger.info(f"State change: {self.previous_state.name} -> {self.current_state.name}{reason_text}")
            for callback in self.state_change_callbacks:
                try:
                    callback(self.previous_state, self.current_state, reason)
                except Exception as e:
                    self.logger.error(f"Error in state change callback: {e}")
    
    def register_state_change_callback(self, callback):
        if callback not in self.state_change_callbacks:
            self.state_change_callbacks.append(callback)
    
    def set_active_api(self, api_provider):
        if api_provider not in ai_manager.providers:
            self.logger.warning(f"Attempted to set unknown API provider: {api_provider}")
            return False
        self.active_api = api_provider
        self.logger.info(f"Active API provider set to: {api_provider}")
        if efb:
            efb.update_api(api_provider.capitalize())
        return True
    
    def add_to_conversation(self, role, content):
        message = {"role": role, "content": content}
        self.conversation_context.append(message)
        if efb:
            efb.add_message(role, content)
    
    def get_conversation_context(self):
        return list(self.conversation_context)
    
    def clear_conversation(self):
        self.conversation_context.clear()
        if efb:
            efb.clear_conversation()
    
    def handle_wake_word(self, wake_word):
        if self.current_state != AppState.STANDBY:
            return False
        wake_word = wake_word.lower()
        wake_variations = ["sky tour", "skye tour", "sky to", "sky tore", "sky tor", "skator", "scatour"]
        if any(variation in wake_word for variation in wake_variations):
            self.set_active_api("openai")  # Default to OpenAI
            self.change_state(AppState.ACTIVE, "Wake word detected")
            self.logger.info("Speaking activation sound")
            audio_processor.speak("", "optimus_prime")
            audio_processor.start_continuous_listening()
            return True
        elif any(phrase in wake_word for phrase in ["sky", "tour", "skye"]) and len(wake_word.split()) <= 4:
            self.logger.info("Speaking wake word clarification")
            audio_processor.speak("Did you mean Sky Tour? Please say Sky Tour to activate.")
            return False
        reactivation_phrases = ["question", "i have a question", "where am i"]
        if any(phrase in wake_word for phrase in reactivation_phrases):
            self.change_state(AppState.ACTIVE, "Reactivated from standby")
            audio_processor.start_continuous_listening()
            self.logger.info(f"Reactivated from standby with phrase: '{wake_word}'")
            return True
        return False
    
    def handle_command(self, command):
        if self.current_state not in [AppState.ACTIVE, AppState.WAITING]:
            return self.handle_wake_word(command)
        command_lower = command.lower()
        self.add_to_conversation("user", command)
        if "deactivate" in command_lower or "shut down" in command_lower:
            self.logger.info("Speaking deactivation sound")
            audio_processor.speak("", "deactivate")
            audio_processor.stop_continuous_listening()
            self.change_state(AppState.STANDBY, "Deactivation requested")
            self.clear_conversation()
            return True
        elif "reset" in command_lower:
            self.logger.info("Speaking reset confirmation")
            audio_processor.speak("Resetting. Ready for a new tour!")
            self.change_state(AppState.ACTIVE, "Reset requested")
            self.clear_conversation()
            return True
        elif "switch to" in command_lower:
            if "grok" in command_lower:
                self.set_active_api("grok")
                self.logger.info("Speaking Grok switch")
                audio_processor.speak("Switched to Grok.")
            elif "open" in command_lower or "chat" in command_lower or "gpt" in command_lower:
                self.set_active_api("openai")
                self.logger.info("Speaking OpenAI switch")
                audio_processor.speak("Switched to OpenAI.")
            else:
                self.logger.info("Speaking unknown provider prompt")
                audio_processor.speak("I didn't recognize that provider. Available options are Grok and OpenAI.")
            return True
        if "where am i" in command_lower:
            self.change_state(AppState.TOURING, "Where am I command with tour info")
            self._handle_where_am_i_with_tour()
            return True
        elif self._is_navigation_query(command_lower):
            self.change_state(AppState.NAVIGATION, "Navigation request")
            self._handle_navigation_request(command)
            return True
        elif self._is_tour_request(command_lower):
            self.change_state(AppState.TOURING, "Tour request")
            self._handle_tour_request(command)
            return True
        elif "tell me when" in command_lower and self.last_destination:
            self._setup_arrival_notification()
            self.logger.info("Speaking arrival notification setup")
            audio_processor.speak(f"I'll let you know when we're approaching {self.last_destination}.")
            self.change_state(AppState.WAITING, "Arrival notification set")
            return True
        elif "no" in command_lower and self.current_state == AppState.WAITING:
            self.logger.info("Speaking wait confirmation")
            audio_processor.speak("Waiting for your next command.")
            self.change_state(AppState.WAITING, "User declined follow-up, staying in wait mode")
            return True
        self.change_state(AppState.PROCESSING, "Processing question")
        self._handle_general_question(command)
        return True
    
    def _handle_where_am_i_with_tour(self):
        self.logger.info("Speaking location check")
        audio_processor.speak("Checking your location...")
        try:
            flight_data = sim_server.get_aircraft_data()
            if not flight_data:
                self.logger.info("Speaking no flight data")
                audio_processor.speak("I couldn't get your current flight data. Please try again.")
                self.change_state(AppState.ACTIVE, "No flight data for tour")
                return
            latitude = flight_data.get("Latitude")
            longitude = flight_data.get("Longitude")
            altitude = flight_data.get("Altitude", 1500)
            altitude = int(round(altitude))
            location_name = geo_utils.reverse_geocode(latitude, longitude)
            parts = location_name.split(', ')
            simplified_parts = []
            for part in parts:
                if any(c.isdigit() for c in part.split()[0]) or (part.strip().isdigit() and len(part.strip()) == 5):
                    continue
                if part.strip() not in simplified_parts and len(simplified_parts) < 3:
                    simplified_parts.append(part.strip())
            simplified_location = ', '.join(simplified_parts)
            prompt = self._create_tour_guide_prompt(simplified_location, altitude)
            system_message = {"role": "system", "content": prompt}
            user_message = {"role": "user", "content": "Where am I?"}
            messages = [system_message, user_message]
            tour_response = ai_manager.generate_response(messages, self.active_api)
            self.logger.info("Speaking tour response")
            audio_processor.speak(tour_response)
            self.add_to_conversation("assistant", tour_response)
            self.logger.info("Speaking more questions prompt")
            audio_processor.speak("Do you have more questions?")
            self.change_state(AppState.WAITING, "Location with tour provided")
        except Exception as e:
            self.logger.error(f"Error handling 'Where am I?' with tour: {e}")
            self.logger.info("Speaking tour error")
            audio_processor.speak("I'm having trouble with that request. Please try again.")
            self.change_state(AppState.ACTIVE, "Tour error")
    
    def _heading_to_cardinal(self, heading):
        directions = [
            "north", "north-northeast", "northeast", "east-northeast",
            "east", "east-southeast", "southeast", "south-southeast",
            "south", "south-southwest", "southwest", "west-southwest",
            "west", "west-northwest", "northwest", "north-northwest"
        ]
        index = round(heading / 22.5) % 16
        return directions[index]
    
    def _is_navigation_query(self, text):
        navigation_keywords = [
            "take me to", "fly to", "go to", "head to", "navigate to",
            "how do i get to", "which way to", "direction to", "heading to"
        ]
        return any(keyword in text for keyword in navigation_keywords)
    
    def _handle_navigation_request(self, query):
        self.logger.info("Speaking navigation calculation")
        audio_processor.speak("Calculating course...")
        try:
            direction_info = navigation_manager.get_direction_to_destination(query)
            if not direction_info:
                self.logger.info("Speaking destination not found")
                audio_processor.speak("I couldn't find that destination. Could you be more specific?")
                self.change_state(AppState.ACTIVE, "Destination not found")
                return
            response = navigation_manager.format_navigation_response(direction_info)
            self.logger.info("Speaking navigation response")
            audio_processor.speak(response)
            self.last_destination = direction_info["destination_name"]
            self.last_dest_lat = direction_info["latitude"]
            self.last_dest_lon = direction_info["longitude"]
            self.add_to_conversation("assistant", response)
            self.logger.info("Speaking more questions prompt")
            audio_processor.speak("Do you have more questions?")
            self.change_state(AppState.WAITING, "Navigation provided")
        except Exception as e:
            self.logger.error(f"Error handling navigation request: {e}")
            self.logger.info("Speaking navigation error")
            audio_processor.speak("I'm having trouble calculating a course. Please try again.")
            self.change_state(AppState.ACTIVE, "Navigation error")
    
    def _setup_arrival_notification(self):
        if not self.last_destination or self.last_dest_lat is None or self.last_dest_lon is None:
            return False
        try:
            success = navigation_manager.start_destination_tracking(
                self.last_destination, self.last_dest_lat, self.last_dest_lon, callbacks=[self]
            )
            if success:
                self.navigation_active = True
                self.logger.info(f"Started tracking destination: {self.last_destination}")
                return True
            else:
                self.logger.warning(f"Failed to start tracking destination: {self.last_destination}")
                return False
        except Exception as e:
            self.logger.error(f"Error setting up arrival notification: {e}")
            return False
    
    def _is_tour_request(self, text):
        tour_keywords = [
            "give me a tour", "show me around", "tell me about this area",
            "what's interesting here", "points of interest", "what can i see",
            "what's below", "what's around here"
        ]
        return any(keyword in text for keyword in tour_keywords)
    
    def _create_tour_guide_prompt(self, location_name, altitude):
        prompt = (
            f"You are an experienced flight tour guide with deep knowledge of geography, history, and points of interest. "
            f"The pilot is currently flying over {location_name} at {altitude} feet. "
            f"Provide an engaging 30-second narration that includes: "
            f"1) A brief description of what they can see below them right now (landmarks, geography, cities, etc.) "
            f"2) One interesting historical fact about this area that's relevant to a pilot "
            f"3) One notable point of interest that would be visible from {altitude} feet "
            f"4) Suggest one nearby location they might want to fly toward, with a specific heading (in degrees) and approximate distance (in miles or nautical miles). "
            f"Keep your tone conversational and enthusiastic, like a real tour guide speaking to a pilot. "
            f"Avoid technical jargon. Focus only on features that would be visible from the air at this altitude. "
            f"Keep your total response to 3-4 short paragraphs."
        )
        return prompt
    
    def _handle_tour_request(self, query):
        self.logger.info("Speaking tour lookup")
        audio_processor.speak("Looking for points of interest...")
        try:
            flight_data = sim_server.get_aircraft_data()
            if not flight_data:
                self.logger.info("Speaking no flight data")
                audio_processor.speak("I couldn't get your current flight data. Please try again.")
                self.change_state(AppState.ACTIVE, "No flight data for tour")
                return
            latitude = flight_data.get("Latitude")
            longitude = flight_data.get("Longitude")
            altitude = flight_data.get("Altitude", 1500)
            altitude = int(round(altitude))
            location_name = geo_utils.reverse_geocode(latitude, longitude)
            prompt = self._create_tour_guide_prompt(location_name, altitude)
            system_message = {"role": "system", "content": prompt}
            user_message = {"role": "user", "content": "What can you tell me about this area?"}
            messages = [system_message, user_message]
            tour_response = ai_manager.generate_response(messages, self.active_api)
            self.logger.info("Speaking tour response")
            audio_processor.speak(tour_response)
            self.add_to_conversation("assistant", tour_response)
            self.logger.info("Speaking more questions prompt")
            audio_processor.speak("Do you have more questions?")
            self.change_state(AppState.WAITING, "Tour provided")
        except Exception as e:
            self.logger.error(f"Error handling tour request: {e}")
            self.logger.info("Speaking tour error")
            audio_processor.speak("I'm having trouble creating a tour for this area. Please try again.")
            self.change_state(AppState.ACTIVE, "Tour error")
    
    def _handle_general_question(self, question):
        try:
            flight_data = sim_server.get_aircraft_data()
            system_prompt = "You are an AI flight tour guide and copilot for Microsoft Flight Simulator 2024. "
            if flight_data:
                latitude = flight_data.get("Latitude")
                longitude = flight_data.get("Longitude")
                altitude = flight_data.get("Altitude")
                if None not in (latitude, longitude, altitude):
                    location = geo_utils.reverse_geocode(latitude, longitude)
                    system_prompt += f"The pilot is currently flying over {location} at {altitude:.0f} feet. "
            system_prompt += "Keep responses clear, informative, and concise. Include interesting facts and context about locations when relevant."
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(self.get_conversation_context())
            response = ai_manager.generate_response(messages, self.active_api)
            self.logger.info("Speaking general question response")
            audio_processor.speak(response)
            self.add_to_conversation("assistant", response)
            self.logger.info("Speaking more questions prompt")
            audio_processor.speak("Do you have more questions?")
            self.change_state(AppState.WAITING, "Question answered")
        except Exception as e:
            self.logger.error(f"Error handling general question: {e}")
            self.logger.info("Speaking question error")
            audio_processor.speak("I'm having trouble answering your question. Please try again.")
            self.change_state(AppState.ACTIVE, "Question handling error")
    
    def on_arrival(self, destination):
        self.logger.info("Speaking arrival notification")
        audio_processor.speak(f"You've arrived at {destination}!")
        self.navigation_active = False
    
    def on_one_minute_away(self, destination, distance):
        self.logger.info("Speaking one-minute warning")
        audio_processor.speak(f"You're about a minute away from {destination}.")
    
    def on_off_course(self, current_heading, target_heading, difference):
        correction = "right" if ((target_heading - current_heading + 360) % 360) < 180 else "left"
        self.logger.info("Speaking off-course correction")
        audio_processor.speak(f"You're off course. Turn {correction} to heading {target_heading:.0f} degrees.")
    
    def on_update(self, distance, heading, eta):
        pass

state_manager = StateManager()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    def test_state_callback(prev_state, new_state, reason):
        print(f"State changed from {prev_state} to {new_state} - Reason: {reason}")
    state_manager.register_state_change_callback(test_state_callback)
    print("\nTesting state transitions:")
    print("Testing wake word handling...")
    result = state_manager.handle_wake_word("Sky Tour, please")
    print(f"Wake word handled: {result}")
    print("\nTesting command handling...")
    commands = [
        "Where am I?",
        "Take me to the Golden Gate Bridge",
        "What's the history of this area?",
        "Tell me when we're close",
        "No",
        "Deactivate"
    ]
    for cmd in commands:
        print(f"\nCommand: {cmd}")
        result = state_manager.handle_command(cmd)
        print(f"Command handled: {result}")
        print(f"Current state: {state_manager.current_state}")