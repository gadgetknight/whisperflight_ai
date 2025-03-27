"""
Whisper Flight AI - State Manager
Version: 5.1.19 (Corrected - No instance creation)
Purpose: Defines StateManager class and AppState enum. Instance created in main.py.
Last Updated: March 27, 2025
Author: Your Name
"""

import os
import sys
import time
import logging
import threading
import queue
from enum import Enum, auto
from collections import deque

# Assuming these imports are correct relative to your project structure
from config_manager import config
from audio_processor import audio_processor
from ai_provider import ai_manager
from simconnect_server import sim_server
from navigation import navigation_manager
from geo_utils import geo_utils
try:
    from efb_integration import efb
except ImportError:
    efb = None

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
    # --- Keep the entire StateManager class definition exactly as in v4 ---
    # (Includes __init__, change_state, helper methods, handle_wake_word, 
    #  handle_command, _handle_ methods, navigation callbacks etc.)
    # Make sure the __init__ and other methods DO NOT try to access 
    # a non-existent global instance. They should only use 'self'.
    def __init__(self):
        self.logger = logging.getLogger("StateManager")
        self.current_state = AppState.STANDBY
        self.previous_state = None
        self.state_change_time = time.time()
        self.active_api = config.get("AI", "default_provider", "openai").lower() 
        self.last_narration_time = 0
        self.last_location_check = 0
        self.context_length = config.getint("AI", "context_length", 10)
        if self.context_length <= 1: 
             self.logger.warning(f"Context length ({self.context_length}) too small, setting to 2.")
             self.context_length = 2
        self.conversation_context = deque(maxlen=self.context_length)
        self.state_change_callbacks = []
        self.navigation_active = False
        self.last_destination = None
        self.last_dest_lat = None
        self.last_dest_lon = None
        self.state_lock = threading.RLock()
        if navigation_manager:
            if self not in navigation_manager.tracking_callbacks:
                 navigation_manager.tracking_callbacks.append(self)
        else: self.logger.warning("NavigationManager not available.")
        self.logger.info(f"StateManager initialized in {self.current_state.name} state with default API: {self.active_api}")

    def change_state(self, new_state, reason=None):
        if not isinstance(new_state, AppState):
             self.logger.error(f"Invalid state type: {type(new_state)}")
             return
        with self.state_lock:
            if new_state == self.current_state: return
            self.previous_state = self.current_state
            self.current_state = new_state
            self.state_change_time = time.time()
            if efb and hasattr(efb, 'update_status'):
                try: efb.update_status(new_state.name.capitalize())
                except Exception as efb_e: self.logger.error(f"EFB status update error: {efb_e}")
            reason_text = f" - Reason: {reason}" if reason else ""
            self.logger.info(f"State change: {self.previous_state.name} -> {self.current_state.name}{reason_text}")
            if new_state == AppState.ACTIVE: print("STATUS: Ready for command.")
            elif new_state == AppState.WAITING: print("STATUS: Waiting for follow-up.")
            elif new_state == AppState.PROCESSING: print("STATUS: Processing...")
            elif new_state == AppState.STANDBY: print("STATUS: Deactivated (Standby).")
            elif new_state == AppState.NAVIGATION: print("STATUS: Navigation active.")
            for callback in self.state_change_callbacks:
                try:
                    if callable(callback): callback(self.previous_state, self.current_state, reason)
                    elif hasattr(callback, '__call__'): callback(self.previous_state, self.current_state, reason)
                    else: self.logger.warning(f"Non-callable callback: {callback}")
                except Exception as e: self.logger.error(f"State change callback error: {e}", exc_info=True)

    def register_state_change_callback(self, callback):
        if callback not in self.state_change_callbacks:
            self.state_change_callbacks.append(callback)

    def set_active_api(self, api_provider):
        if not ai_manager or not hasattr(ai_manager, 'providers'):
             self.logger.error("AIManager N/A."); return False
        api_provider_lower = api_provider.lower()
        if api_provider_lower not in ai_manager.providers:
            self.logger.warning(f"Unknown API provider: {api_provider}")
            available = list(ai_manager.providers.keys())
            if audio_processor: audio_processor.speak(f"Available: {', '.join(name.capitalize() for name in available)}.")
            return False
        if self.active_api != api_provider_lower:
             self.active_api = api_provider_lower
             self.logger.info(f"Active API set to: {self.active_api}")
             if efb and hasattr(efb, 'update_api'):
                 try: efb.update_api(self.active_api.capitalize())
                 except Exception as efb_e: self.logger.error(f"EFB API update error: {efb_e}")
        else: self.logger.info(f"API already: {self.active_api}")
        return True

    def add_to_conversation(self, role, content):
        if role not in ["user", "assistant", "system"]: return
        if not content: return
        message = {"role": role, "content": content}
        self.conversation_context.append(message)
        self.logger.debug(f"Ctx Add: {role}: '{content[:50]}...'")
        if efb and hasattr(efb, 'add_message'):
             try: efb.add_message(role, content)
             except Exception as efb_e: self.logger.error(f"EFB msg error: {efb_e}")

    def get_conversation_context(self):
        return list(self.conversation_context) 

    def clear_conversation(self):
        self.conversation_context.clear()
        self.logger.info("Conversation context cleared.")
        if efb and hasattr(efb, 'clear_conversation'):
            try: efb.clear_conversation()
            except Exception as efb_e: self.logger.error(f"EFB clear error: {efb_e}")

    def _is_navigation_query(self, text):
        navigation_keywords = ["take me to","fly to","go to","head to","navigate to","how do i get to","which way to","direction to","heading to"]
        return any(f"{keyword} " in text for keyword in navigation_keywords)

    def _is_tour_request(self, text):
        tour_keywords = ["give me a tour","show me around","tell me about this area","what's interesting here","points of interest","what can i see","what's below","what's around here"]
        return any(keyword in text for keyword in tour_keywords)

    def _clear_audio_queue(self):
        if audio_processor and hasattr(audio_processor, 'audio_queue'):
            cleared_count = 0
            while not audio_processor.audio_queue.empty():
                try: audio_processor.audio_queue.get_nowait(); cleared_count += 1
                except queue.Empty: break
                except Exception as q_e: self.logger.error(f"Queue clear error: {q_e}"); break
            if cleared_count > 0: self.logger.info(f"Cleared {cleared_count} items from audio queue.")
        else: self.logger.warning("Audio queue N/A to clear.")

    def _create_tour_guide_prompt(self, location_name, altitude):
        prompt = (f"You are an AI flight tour guide. Pilot near {location_name} at {altitude} ft. Give brief, engaging audio narration (3-4 paragraphs): 1) Current view. 2) Relevant historical/geo fact. 3) Notable POI visible from {altitude} ft. Tone: Conversational, enthusiastic. Focus on aerial view. Avoid jargon.")
        return prompt

    def handle_wake_word(self, wake_word):
        if self.current_state != AppState.STANDBY: return False
        wake_word_lower = wake_word.lower().strip()
        wake_variations = ["sky tour", "skytour", "scatour"]
        if any(variation == wake_word_lower for variation in wake_variations):
            self.change_state(AppState.ACTIVE, "Wake word detected")
            if audio_processor:
                audio_processor.speak("", "optimus_prime")
                self._clear_audio_queue()
                audio_processor.start_continuous_listening()
            else: self.logger.error("Audio Processor N/A.")
            return True
        fuzzy_wake_variations = ["sky to", "sky tore", "sky tor", "skator", "skater", "sky door", "sky t", "sky2"]
        if any(variation in wake_word_lower for variation in fuzzy_wake_variations) and len(wake_word_lower.split()) <= 3:
             if audio_processor: audio_processor.speak("Did you say Sky Tour? Please repeat.")
             return True 
        reactivation_phrases = ["question", "i have a question", "where am i", "are you there", "hello whisper"]
        if any(phrase in wake_word_lower for phrase in reactivation_phrases):
            self.change_state(AppState.ACTIVE, f"Reactivated: '{wake_word_lower}'")
            if audio_processor: self._clear_audio_queue(); audio_processor.start_continuous_listening()
            if "where am i" not in wake_word_lower: 
                 if audio_processor:
                      if "question" in wake_word_lower: audio_processor.speak("Okay, what is your question?")
                      else: audio_processor.speak("Whisper AI ready.")
            return True 
        return False 

    def handle_command(self, command):
        junk = [".", ",", "?", "!", "-", "you", "the", "a", "uh", "um"]
        command_strip = command.strip() if command else ""
        if not command_strip or len(command_strip) < 2 or command_strip.lower() in junk:
            self.logger.debug(f"Ignoring short/junk command: '{command}'")
            return False 

        current_processing_state = self.current_state
        if current_processing_state == AppState.STANDBY: return self.handle_wake_word(command)
        elif current_processing_state in [AppState.ACTIVE, AppState.WAITING]:
            command_lower = command_strip.lower()
            if command_lower not in ["question", "no"]: self.add_to_conversation("user", command)
            if "deactivate" in command_lower or "shut down" in command_lower:
                if audio_processor: audio_processor.speak("","deactivate"); audio_processor.stop_continuous_listening()
                if self.navigation_active: navigation_manager.stop_destination_tracking(); self.navigation_active=False
                self.change_state(AppState.STANDBY, "Deactivation"); self.clear_conversation(); return True
            elif "reset" in command_lower:
                if audio_processor: audio_processor.speak("Resetting."); self.clear_conversation()
                if self.navigation_active: navigation_manager.stop_destination_tracking(); self.navigation_active=False
                self.change_state(AppState.ACTIVE, "Reset"); return True
            elif "switch to" in command_lower:
                 provider=None;
                 if "grok" in command_lower: provider="grok"
                 elif "open" in command_lower: provider="openai"
                 if provider: self.set_active_api(provider) # Speak confirm inside method
                 else:
                      if audio_processor: audio_processor.speak("Options: Grok, OpenAI.")
                 return True
            elif command_lower == "no" and current_processing_state == AppState.WAITING:
                if audio_processor: audio_processor.speak("Okay, standing by.")
                self.change_state(AppState.ACTIVE, "User declined follow-up"); return True
            elif "where am i" in command_lower:
                self.change_state(AppState.PROCESSING, "Where am I cmd"); threading.Thread(target=self._handle_where_am_i_with_tour, daemon=True).start(); return True
            elif self._is_navigation_query(command_lower):
                self.change_state(AppState.PROCESSING, "Nav request"); threading.Thread(target=self._handle_navigation_request, args=(command,), daemon=True).start(); return True
            elif self._is_tour_request(command_lower):
                self.change_state(AppState.PROCESSING, "Tour request"); threading.Thread(target=self._handle_tour_request, args=(command,), daemon=True).start(); return True
            elif "tell me when" in command_lower:
                 if self.last_destination:
                     self.change_state(AppState.PROCESSING, "Setup notify"); success=self._setup_arrival_notification()
                     if success: self.change_state(AppState.NAVIGATION, "Notify set"); audio_processor.speak(f"Tracking: {self.last_destination}.")
                     else: self.change_state(AppState.ACTIVE, "Notify fail"); audio_processor.speak("Couldn't setup tracking.")
                 else: audio_processor.speak("No destination."); self.change_state(AppState.ACTIVE, "No dest notify")
                 return True
            else: # General question
                if command_lower == "question":
                     if audio_processor: audio_processor.speak("Okay, what is your question?")
                     self.change_state(AppState.ACTIVE, "Ready for question"); return True
                self.change_state(AppState.PROCESSING, "General question"); threading.Thread(target=self._handle_general_question, args=(command,), daemon=True).start(); return True
        else: # Busy state
            self.logger.warning(f"Command '{command}' ignored in state {current_processing_state.name}.")
            return False

    # --- Handler Methods (_handle_...) ---
    def _handle_where_am_i_with_tour(self):
        # --- Keep logic from previous version ---
        # (Includes speak("Checking location..."), context TypeError fix, etc.)
        self.logger.info("Handling 'Where am I?' (thread)...")
        if audio_processor: audio_processor.speak("Checking your location...") 
        else: self.logger.error("Audio processor N/A."); self.change_state(AppState.ACTIVE, "Audio error"); return
        try:
            flight_data=sim_server.get_aircraft_data()
            if not flight_data or "Latitude" not in flight_data: raise ValueError("Incomplete flight data.")
            lat, lon, alt = flight_data.get("Latitude"), flight_data.get("Longitude"), int(round(flight_data.get("Altitude",1500)))
            loc_name = geo_utils.reverse_geocode(lat, lon)
            parts=loc_name.split(', '); simp=[]; seen=set(); country=parts[-1] if parts else ""; state=parts[-2] if len(parts)>1 else None; city=parts[-3] if len(parts)>2 else None
            if city and city not in seen: simp.append(city); seen.add(city);
            if state and state not in seen: simp.append(state); seen.add(state);
            if country and country not in seen: simp.append(country); seen.add(country);
            simp_loc = ', '.join(simp) if simp else loc_name
            prompt = self._create_tour_guide_prompt(simp_loc, alt)
            msg = [{"role":"system","content":prompt}, {"role":"user","content":"Tell me about my current location."}]
            hist=list(self.conversation_context); recent=hist[-(self.context_length-1):]; msgs=[msg[0]]+recent+[msg[1]] # Build messages safely
            if len(msgs)>self.context_length: msgs=[msgs[0]]+msgs[-(self.context_length-1):]
            response=ai_manager.generate_response(msgs, self.active_api)
            is_err=any(response.startswith(i) for i in getattr(ai_manager, 'error_indicators', []))
            if audio_processor:
                speak_ok=audio_processor.speak(response)
                if speak_ok and not is_err:
                     self.add_to_conversation("assistant", response); audio_processor.speak("Do you have more questions?")
                     self.change_state(AppState.WAITING, "Location provided")
                elif is_err: self.change_state(AppState.ACTIVE, "AI error location")
                else: self.logger.error("TTS fail."); self.change_state(AppState.ACTIVE, "TTS fail")
            else: self.logger.error("Audio error."); self.change_state(AppState.ACTIVE, "Audio error")
        except Exception as e:
            self.logger.error(f"Err in _handle_where_am_i: {e}", exc_info=True)
            if audio_processor: audio_processor.speak("Error getting location details.")
            self.change_state(AppState.ACTIVE, "Error location processing")

    def _handle_navigation_request(self, query):
        # --- Keep logic from previous version ---
        self.logger.info("Handling nav request (thread)...")
        if audio_processor: audio_processor.speak("Calculating...")
        else: self.logger.error("Audio processor N/A."); self.change_state(AppState.ACTIVE, "Audio error"); return
        try:
            dir_info=navigation_manager.get_direction_to_destination(query)
            if not dir_info: raise ValueError("Dest not found.")
            response=navigation_manager.format_navigation_response(dir_info)
            is_err=any(response.startswith(i) for i in ["I couldn't find", "I encountered"])
            if audio_processor:
                speak_ok=audio_processor.speak(response)
                if speak_ok and not is_err:
                     self.last_destination=dir_info["destination_name"]; self.last_dest_lat=dir_info["latitude"]; self.last_dest_lon=dir_info["longitude"]
                     self.add_to_conversation("assistant",response); audio_processor.speak("Setup arrival notification?")
                     self.change_state(AppState.WAITING, "Nav provided")
                elif is_err: self.change_state(AppState.ACTIVE, "Nav lookup error")
                else: self.logger.error("TTS fail."); self.change_state(AppState.ACTIVE, "TTS fail")
            else: self.logger.error("Audio error."); self.change_state(AppState.ACTIVE, "Audio error")
        except Exception as e:
            self.logger.error(f"Err handling nav req: {e}", exc_info=True)
            if audio_processor: audio_processor.speak("Error calculating course.")
            self.change_state(AppState.ACTIVE, "Nav processing error")

    def _setup_arrival_notification(self):
        # --- Keep logic from previous version ---
        if self.navigation_active: self.logger.info("Stopping prev nav track."); navigation_manager.stop_destination_tracking(); self.navigation_active=False 
        if not self.last_destination or self.last_dest_lat is None or self.last_dest_lon is None: return False
        try:
            if not navigation_manager: raise RuntimeError("NavManager N/A")
            success=navigation_manager.start_destination_tracking(self.last_destination, self.last_dest_lat, self.last_dest_lon, callbacks=[self])
            self.navigation_active = success
            if success: self.logger.info(f"Track started: {self.last_destination}")
            else: self.logger.warning(f"Failed track start: {self.last_destination}")
            return success
        except Exception as e: self.logger.error(f"Err setup arrival: {e}", exc_info=True); return False

    def _handle_tour_request(self, query):
        # --- Keep logic from previous version ---
        self.logger.info("Handling tour request (thread)...")
        if audio_processor: audio_processor.speak("Looking...")
        else: self.logger.error("Audio processor N/A."); self.change_state(AppState.ACTIVE, "Audio error"); return
        try:
            flight_data=sim_server.get_aircraft_data()
            if not flight_data or "Latitude" not in flight_data: raise ValueError("Incomplete data.")
            lat,lon,alt=flight_data.get("Latitude"),flight_data.get("Longitude"),int(round(flight_data.get("Altitude",1500)))
            loc_name=geo_utils.reverse_geocode(lat,lon)
            parts=loc_name.split(', '); simp=[]; seen=set(); country=parts[-1] if parts else ""; state=parts[-2] if len(parts)>1 else None; city=parts[-3] if len(parts)>2 else None
            if city and city not in seen: simp.append(city); seen.add(city);
            if state and state not in seen: simp.append(state); seen.add(state);
            if country and country not in seen: simp.append(country); seen.add(country);
            simp_loc = ', '.join(simp) if simp else loc_name
            prompt = self._create_tour_guide_prompt(simp_loc, alt) 
            system_message={"role":"system","content":prompt}; user_query=query if query!="tour request" else "Interesting things?"; user_message={"role":"user","content":user_query}
            msgs=self.get_conversation_context(); msgs=[system_message]+msgs[-(self.context_length-2):]+[user_message]
            if len(msgs)>self.context_length: msgs=[msgs[0]]+msgs[-(self.context_length-1):]
            response=ai_manager.generate_response(msgs, self.active_api)
            is_err=any(response.startswith(i) for i in getattr(ai_manager, 'error_indicators', []))
            if audio_processor:
                speak_ok=audio_processor.speak(response)
                if speak_ok and not is_err:
                     self.add_to_conversation("assistant", response); audio_processor.speak("Do you have more questions?")
                     self.change_state(AppState.WAITING, "Tour provided")
                elif is_err: self.change_state(AppState.ACTIVE, "AI error tour")
                else: self.logger.error("TTS fail."); self.change_state(AppState.ACTIVE, "TTS fail")
            else: self.logger.error("Audio error."); self.change_state(AppState.ACTIVE, "Audio error")
        except Exception as e:
            self.logger.error(f"Err handling tour: {e}", exc_info=True)
            if audio_processor: audio_processor.speak("Error preparing tour.")
            self.change_state(AppState.ACTIVE, "Tour processing error")

    def _handle_general_question(self, question):
        # --- Keep logic from previous version (with TypeError fix) ---
        self.logger.info(f"Handling question (thread): '{question[:50]}...'")
        try:
            flight_data=sim_server.get_aircraft_data(); loc_ctx=""
            if flight_data:
                lat=flight_data.get("Latitude"); lon=flight_data.get("Longitude"); alt=flight_data.get("Altitude")
                if None not in (lat,lon,alt):
                    try: loc=geo_utils.reverse_geocode(lat,lon); loc_ctx=f"Pilot near {loc} at {alt:.0f} ft. "
                    except Exception as geo_e: self.logger.warning(f"Failed geo ctx: {geo_e}")
            sys_prompt=f"AI flight guide. {loc_ctx}Answer pilot concisely for audio. Add local context."
            msgs=[{"role":"system","content":sys_prompt}]
            hist=list(self.conversation_context); recent=hist[-(self.context_length-1):]; msgs.extend(recent)
            is_redundant=bool(msgs and msgs[-1].get("role")=="user" and msgs[-1].get("content")==question)
            if not is_redundant: msgs.append({"role":"user","content":question})
            if len(msgs)>self.context_length: msgs=[msgs[0]]+msgs[-(self.context_length-1):]
            response=ai_manager.generate_response(msgs, self.active_api)
            is_err=any(response.startswith(i) for i in getattr(ai_manager, 'error_indicators', []))
            if audio_processor:
                speak_ok=audio_processor.speak(response)
                if speak_ok and not is_err:
                     self.add_to_conversation("assistant", response); audio_processor.speak("Do you have more questions?")
                     self.change_state(AppState.WAITING, "Question answered")
                elif is_err: self.change_state(AppState.ACTIVE, "AI error question")
                else: self.logger.error("TTS fail."); self.change_state(AppState.ACTIVE, "TTS fail")
            else: self.logger.error("Audio error."); self.change_state(AppState.ACTIVE, "Audio error")
        except Exception as e:
            self.logger.error(f"Err handling question: {e}", exc_info=True)
            if audio_processor: audio_processor.speak("Trouble processing question.")
            self.change_state(AppState.ACTIVE, "Question handling error")

    # --- Navigation Callbacks ---
    def on_arrival(self, destination):
        with self.state_lock:
             if self.current_state not in [AppState.STANDBY, AppState.ERROR]:
                  if audio_processor: audio_processor.speak(f"Arrived at {destination}!")
                  self.navigation_active = False; self.change_state(AppState.ACTIVE, f"Arrived: {destination}")
             else: self.logger.info("Ignoring arrival CB."); self.navigation_active = False
    def on_one_minute_away(self, destination, distance):
         with self.state_lock:
             if self.current_state == AppState.NAVIGATION and self.navigation_active:
                  if audio_processor: audio_processor.speak(f"Approaching {destination}, 1 minute.")
             else: self.logger.info("Ignoring 1-min CB.")
    def on_off_course(self, current_heading, target_heading, difference):
         with self.state_lock:
             if self.current_state == AppState.NAVIGATION and self.navigation_active:
                  correction="right" if ((target_heading-current_heading+360)%360)<180 else "left"
                  if audio_processor: audio_processor.speak(f"Correction: Turn {correction} to {target_heading:.0f} for {self.last_destination}.")
             else: self.logger.info("Ignoring off-course CB.")
    def on_update(self, distance, heading, eta):
        self.logger.debug(f"Nav update: Dist={distance:.1f}nm, Hdg={heading:.0f}, ETA={eta:.1f}min")
        pass

# --- Singleton Instance (Renamed) ---
manager = StateManager() # Use 'manager' as the instance name

# --- Example Usage / Test Harness (Removed - Rely on main.py for testing) ---
# if __name__ == "__main__":
#     # ... test code removed ...
#     pass