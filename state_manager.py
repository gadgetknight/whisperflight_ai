"""
Whisper Flight AI - State Manager
Version: 5.1.27 (Corrected - Final Syntax Fix)
Purpose: Manages application state transitions and conversation flow
Last Updated: March 28, 2025
Author: Your Name

Changes:
- Fixed SyntaxError on variable assignment/if lines in ALL handler methods.
- Includes previous fixes.
"""

import os
import sys
import time
import logging
import threading
import queue 
from enum import Enum, auto
from collections import deque

# Imports
from config_manager import config
from audio_processor import audio_processor 
from ai_provider import ai_manager
from simconnect_server import sim_server
from navigation import navigation_manager
from geo_utils import geo_utils
try: from efb_integration import efb
except ImportError: efb = None

class AppState(Enum):
    STANDBY=auto(); ACTIVE=auto(); LISTENING=auto(); PROCESSING=auto()
    RESPONDING=auto(); WAITING=auto(); NAVIGATION=auto(); TOURING=auto(); ERROR=auto()

class StateManager:
    # --- __init__ and other methods unchanged ---
    def __init__(self):
        self.logger = logging.getLogger("StateManager")
        self.current_state = AppState.STANDBY
        self.previous_state = None; self.state_change_time = time.time()
        self.active_api = config.get("AI", "default_provider", "openai").lower() 
        self.last_narration_time = 0; self.last_location_check = 0
        self.context_length = config.getint("AI", "context_length", 10);
        if self.context_length <= 1: self.context_length = 2
        self.conversation_context = deque(maxlen=self.context_length); self.state_change_callbacks = []
        self.navigation_active = False; self.last_destination = None; self.last_dest_lat = None; self.last_dest_lon = None
        self.state_lock = threading.RLock()
        if navigation_manager:
            if self not in navigation_manager.tracking_callbacks: navigation_manager.tracking_callbacks.append(self)
        self.logger.info(f"StateManager initialized: State={self.current_state.name}, API={self.active_api}")

    def change_state(self, new_state, reason=None):
        # --- Keep logic ---
        if not isinstance(new_state, AppState): self.logger.error(f"Invalid state type: {type(new_state)}"); return
        with self.state_lock:
            if new_state == self.current_state: return
            self.previous_state = self.current_state; self.current_state = new_state; self.state_change_time = time.time()
            if efb and hasattr(efb, 'update_status'):
                try: efb.update_status(new_state.name.capitalize())
                except Exception as e: self.logger.error(f"EFB status update error: {e}")
            reason_text = f" - Reason: {reason}" if reason else ""
            self.logger.info(f"State change: {self.previous_state.name} -> {self.current_state.name}{reason_text}")
            if new_state == AppState.ACTIVE: print("STATUS: Ready.")
            elif new_state == AppState.WAITING: print("STATUS: Waiting follow-up.")
            elif new_state == AppState.PROCESSING: print("STATUS: Processing...")
            elif new_state == AppState.STANDBY: print("STATUS: Standby.")
            elif new_state == AppState.NAVIGATION: print("STATUS: Navigating.")
            for callback in self.state_change_callbacks:
                try:
                    if callable(callback): callback(self.previous_state, self.current_state, reason)
                    elif hasattr(callback, '__call__'): callback(self.previous_state, self.current_state, reason)
                except Exception as e: self.logger.error(f"State callback error: {e}", exc_info=True)

    # --- Other methods (register_..., set_active_api, add_..., get_..., clear..., _is_..., _clear_audio_queue, _create_...) remain the same ---
    def register_state_change_callback(self, callback):
        if callback not in self.state_change_callbacks: self.state_change_callbacks.append(callback)
    def set_active_api(self, api_provider):
        if not ai_manager or not hasattr(ai_manager, 'providers'): self.logger.error("AIManager N/A."); return False
        api_lower = api_provider.lower()
        if api_lower not in ai_manager.providers:
            available = list(ai_manager.providers.keys()); self.logger.warning(f"Unknown API: {api_provider}. Avail: {available}")
            if audio_processor: audio_processor.speak(f"Available: {', '.join(name.capitalize() for name in available)}")
            return False
        if self.active_api != api_lower:
             self.active_api = api_lower; self.logger.info(f"Active API set: {self.active_api}")
             if efb and hasattr(efb, 'update_api'):
                 try: efb.update_api(self.active_api.capitalize())
                 except Exception as e: self.logger.error(f"EFB API update error: {e}")
        else: self.logger.info(f"API already: {self.active_api}")
        if audio_processor and self.current_state in [AppState.ACTIVE, AppState.WAITING]: time.sleep(0.3); audio_processor.start_continuous_listening()
        return True
    def add_to_conversation(self, role, content):
        if role not in ["user", "assistant", "system"] or not content: return
        message = {"role": role, "content": content}; self.conversation_context.append(message)
        self.logger.debug(f"Ctx Add: {role}: '{content[:50]}...'")
        if efb and hasattr(efb, 'add_message'):
             try: efb.add_message(role, content)
             except Exception as e: self.logger.error(f"EFB msg error: {e}")
    def get_conversation_context(self): return list(self.conversation_context) 
    def clear_conversation(self):
        self.conversation_context.clear(); self.logger.info("Context cleared.")
        if efb and hasattr(efb, 'clear_conversation'):
            try: efb.clear_conversation()
            except Exception as e: self.logger.error(f"EFB clear error: {e}")
    def _is_navigation_query(self, text):
        keywords = ["take me to","fly to","go to","head to","navigate to","how do i get to","which way to","direction to","heading to"]
        return any(f"{k} " in text for k in keywords)
    def _is_tour_request(self, text):
        keywords = ["give me a tour","show me around","tell me about this area","what's interesting here","points of interest","what can i see","what's below","what's around here"]
        return any(k in text for k in keywords)
    def _clear_audio_queue(self):
        if audio_processor and hasattr(audio_processor, 'audio_queue'):
            count = 0;
            while not audio_processor.audio_queue.empty():
                try: audio_processor.audio_queue.get_nowait(); count += 1
                except queue.Empty: break
                except Exception as e: self.logger.error(f"Queue clear err: {e}"); break
            if count > 0: self.logger.info(f"Cleared {count} items from queue.")
        else: self.logger.warning("Audio queue N/A.")
    def _create_tour_guide_prompt(self, location_name, altitude):
        return (f"AI tour guide near {location_name} at {altitude} ft. Brief, engaging audio narration (3-4 paras): 1) View desc. 2) Hist/geo fact. 3) Visible POI. Tone: Conversational, enthusiastic. Focus: aerial. No jargon.")

    # --- MAIN HANDLERS ---
    def handle_wake_word(self, wake_word):
        # --- Keep logic ---
        if self.current_state != AppState.STANDBY: return False
        wake_lower = wake_word.lower().strip()
        if any(v == wake_lower for v in ["sky tour", "skytour", "scatour"]):
            self.change_state(AppState.ACTIVE, "Wake word");
            if audio_processor: audio_processor.speak("", "optimus_prime"); self._clear_audio_queue(); audio_processor.start_continuous_listening()
            return True
        fuzzy = ["sky to","sky tore","sky tor","skator","skater","sky door","sky t","sky2"]
        if any(v in wake_lower for v in fuzzy) and len(wake_lower.split())<=3:
             if audio_processor: audio_processor.speak("Say Sky Tour clearly.")
             return True 
        reactivate = ["question","i have a question","where am i","are you there","hello whisper"]
        if any(p in wake_lower for p in reactivate):
            self.change_state(AppState.ACTIVE, f"Reactivated: '{wake_lower}'");
            if audio_processor: self._clear_audio_queue(); audio_processor.start_continuous_listening()
            if "where am i" not in wake_lower: 
                 if audio_processor:
                      if "question" in wake_lower: audio_processor.speak("Okay, what's your question?")
                      else: audio_processor.speak("Whisper AI ready.")
            return True 
        return False 

    def handle_command(self, command):
        # --- Keep logic (incl. enhanced junk filter & "No" to STANDBY) ---
        junk = ["." , ",", "?", "!", "-", "you", "the", "a", "uh", "um", "more questions?", "more questions", "checking your location.", "checking your location", "okay, standing by.", "okay, standing by", "okay, what is your question?", "okay, what is your question", "okay what is your question?", "okay what is your question", "whisper ai ready.", "whisper ai ready", "understood. safe flying.", "understood. safe flying", "understood let me know if you need anything else. safe flying.", "feel free to ask anything you need to know. i'm here to help.", "feel free to ask", "let me know if you need anything else", "safe flying!"]; cmd_strip = command.strip() if command else ""
        if not cmd_strip or len(cmd_strip) < 3 or cmd_strip.lower() in junk: self.logger.debug(f"Ignoring cmd: '{command}'"); return False 
        current_st = self.current_state
        if current_st == AppState.STANDBY: return self.handle_wake_word(command)
        elif current_st in [AppState.ACTIVE, AppState.WAITING]:
            cmd_lower = cmd_strip.lower()
            if cmd_lower not in ["question", "no", "nope", "stop", "that's all", "nothing else"]: self.add_to_conversation("user", command)
            negative_responses = ["no", "nope", "stop", "that's all", "nothing else"]
            if any(neg == cmd_lower for neg in negative_responses) and current_st == AppState.WAITING:
                self.logger.info("User indicated stop.")
                if audio_processor: audio_processor.speak("Okay, going to standby.") 
                if audio_processor: audio_processor.stop_continuous_listening() 
                self.change_state(AppState.STANDBY, "User stop.") 
                return True 
            elif "deactivate" in cmd_lower or "shut down" in cmd_lower:
                if audio_processor: audio_processor.speak("","deactivate"); audio_processor.stop_continuous_listening()
                if self.navigation_active: navigation_manager.stop_destination_tracking(); self.navigation_active=False
                self.change_state(AppState.STANDBY, "Deactivation"); self.clear_conversation(); return True
            elif "reset" in cmd_lower:
                if audio_processor: audio_processor.speak("Resetting.");
                self.clear_conversation();
                if self.navigation_active: navigation_manager.stop_destination_tracking(); self.navigation_active=False
                self.change_state(AppState.ACTIVE, "Reset") 
                if audio_processor: time.sleep(0.3); audio_processor.start_continuous_listening()
                return True
            elif "switch to" in cmd_lower:
                 provider=None; 
                 if "grok" in cmd_lower: provider="grok"
                 elif "open" in cmd_lower: provider="openai"
                 if provider: success=self.set_active_api(provider);
                 else: success=False; audio_processor.speak("Options: Grok, OpenAI.") if audio_processor else None
                 if audio_processor and self.current_state in [AppState.ACTIVE, AppState.WAITING]: time.sleep(0.3); audio_processor.start_continuous_listening()
                 return True
            elif "where am i" in cmd_lower:
                if audio_processor: audio_processor.stop_continuous_listening() 
                self.change_state(AppState.PROCESSING, "Where am I cmd"); threading.Thread(target=self._handle_where_am_i_with_tour, daemon=True).start(); return True
            elif self._is_navigation_query(cmd_lower):
                if audio_processor: audio_processor.stop_continuous_listening()
                self.change_state(AppState.PROCESSING, "Nav request"); threading.Thread(target=self._handle_navigation_request, args=(command,), daemon=True).start(); return True
            elif self._is_tour_request(cmd_lower):
                if audio_processor: audio_processor.stop_continuous_listening()
                self.change_state(AppState.PROCESSING, "Tour request"); threading.Thread(target=self._handle_tour_request, args=(command,), daemon=True).start(); return True
            elif "tell me when" in cmd_lower:
                 if self.last_destination:
                     if audio_processor: audio_processor.stop_continuous_listening()
                     self.change_state(AppState.PROCESSING, "Setup notify"); success=self._setup_arrival_notification()
                     if success: msg=f"Tracking: {self.last_destination}."; next_state=AppState.NAVIGATION
                     else: msg="Couldn't setup tracking."; next_state=AppState.ACTIVE
                     if audio_processor: audio_processor.speak(msg)
                     self.change_state(next_state, "Notify setup done")
                     if audio_processor and self.current_state != AppState.STANDBY: time.sleep(0.3); audio_processor.start_continuous_listening()
                 else: 
                     if audio_processor: audio_processor.speak("No destination.") 
                     self.change_state(AppState.ACTIVE, "No dest notify")
                     if audio_processor: time.sleep(0.3); audio_processor.start_continuous_listening() 
                 return True
            else: # General question
                if cmd_lower == "question":
                     if audio_processor: audio_processor.speak("Okay, what is your question?") 
                     self.change_state(AppState.ACTIVE, "Ready for question") 
                     if audio_processor: time.sleep(0.3); audio_processor.start_continuous_listening() 
                     return True
                if audio_processor: audio_processor.stop_continuous_listening() 
                self.change_state(AppState.PROCESSING, "General question"); threading.Thread(target=self._handle_general_question, args=(command,), daemon=True).start(); return True
        else: # Busy state
            self.logger.warning(f"Command '{command}' ignored in state {current_st.name}.")
            return False

    # --- Handler Methods (_handle_...) ---
    # Includes Syntax Fix in all relevant methods

    def _handle_where_am_i_with_tour(self):
        next_state = AppState.ACTIVE; reason = "Error loc proc"
        try:
            self.logger.info("Handling 'Where am I?' (thread)...")
            if audio_processor: audio_processor.speak("Checking your location...") 
            else: raise RuntimeError("Audio processor N/A.")
            flight_data=sim_server.get_aircraft_data();
            if not flight_data or "Latitude" not in flight_data: raise ValueError("Incomplete data.")
            lat, lon, alt = flight_data.get("Latitude"), flight_data.get("Longitude"), int(round(flight_data.get("Altitude",1500)))
            loc_name = geo_utils.reverse_geocode(lat, lon); parts=loc_name.split(', '); simp=[]; seen=set(); country=parts[-1] if parts else ""; state=parts[-2] if len(parts)>1 else None; city=parts[-3] if len(parts)>2 else None
            # Corrected syntax:
            if city and city not in seen: simp.append(city); seen.add(city)
            if state and state not in seen: simp.append(state); seen.add(state)
            if country and country not in seen: simp.append(country); seen.add(country)
            simp_loc = ', '.join(simp) if simp else loc_name; 
            prompt=self._create_tour_guide_prompt(simp_loc, alt)
            msg=[{"role":"system","content":prompt}, {"role":"user","content":"Loc info."}]; hist=list(self.conversation_context); msgs=[msg[0]]+hist[-(self.context_length-2):]+[msg[1]]
            if len(msgs)>self.context_length: msgs=[msgs[0]]+msgs[-(self.context_length-1):]
            response=ai_manager.generate_response(msgs, self.active_api); is_err=any(response.startswith(i) for i in getattr(ai_manager, 'error_indicators', []))
            
            # Corrected Syntax
            speak_ok = False 
            if audio_processor: 
                speak_ok = audio_processor.speak(response)

            if speak_ok and not is_err: self.add_to_conversation("assistant", response); audio_processor.speak("More questions?"); next_state=AppState.WAITING; reason="Loc provided"
            elif is_err: reason="AI error loc"
            else: self.logger.error("TTS fail."); reason="TTS fail"
        except Exception as e: self.logger.error(f"Err where_am_i: {e}",exc_info=True); audio_processor.speak("Error getting location.") if audio_processor else None; reason="Error loc proc"
        finally:
             if next_state in [AppState.ACTIVE, AppState.WAITING]:
                  if audio_processor: time.sleep(0.3); audio_processor.start_continuous_listening() 
             self.change_state(next_state, reason)

    def _handle_navigation_request(self, query):
        next_state = AppState.ACTIVE; reason = "Nav error"
        try:
            self.logger.info("Handling nav request (thread)...")
            if audio_processor: audio_processor.speak("Calculating...")
            else: raise RuntimeError("Audio processor N/A.")
            dir_info=navigation_manager.get_direction_to_destination(query);
            if not dir_info: raise ValueError("Dest not found.")
            response=navigation_manager.format_navigation_response(dir_info); is_err=any(response.startswith(i) for i in ["I couldn't find","I encountered"])
            
            # Corrected Syntax
            speak_ok = False
            if audio_processor: 
                speak_ok = audio_processor.speak(response)

            if speak_ok and not is_err: self.last_destination=dir_info["destination_name"]; self.last_dest_lat=dir_info["latitude"]; self.last_dest_lon=dir_info["longitude"]; self.add_to_conversation("assistant",response); audio_processor.speak("Notify on arrival?"); next_state=AppState.WAITING; reason="Nav provided"
            elif is_err: reason="Nav lookup err"
            else: self.logger.error("TTS fail."); reason="TTS fail"
        except Exception as e: self.logger.error(f"Err nav req: {e}",exc_info=True); audio_processor.speak("Error calculating.") if audio_processor else None; reason="Nav proc error"
        finally:
             if next_state in [AppState.ACTIVE, AppState.WAITING]:
                  if audio_processor: time.sleep(0.3); audio_processor.start_continuous_listening()
             self.change_state(next_state, reason)

    def _setup_arrival_notification(self):
        # --- Keep logic ---
        if self.navigation_active: self.logger.info("Stopping prev track."); navigation_manager.stop_destination_tracking(); self.navigation_active=False 
        if not self.last_destination or self.last_dest_lat is None or self.last_dest_lon is None: return False
        try:
            if not navigation_manager: raise RuntimeError("NavManager N/A")
            success=navigation_manager.start_destination_tracking(self.last_destination,self.last_dest_lat,self.last_dest_lon,callbacks=[self])
            self.navigation_active=success;
            if success: self.logger.info(f"Track started: {self.last_destination}")
            else: self.logger.warning(f"Failed track start: {self.last_destination}")
            return success
        except Exception as e: self.logger.error(f"Err setup arrival: {e}",exc_info=True); return False

    def _handle_tour_request(self, query):
        next_state = AppState.ACTIVE; reason = "Tour proc error"
        try:
            self.logger.info("Handling tour request (thread)...")
            if audio_processor: audio_processor.speak("Looking...")
            else: raise RuntimeError("Audio processor N/A.")
            flight_data=sim_server.get_aircraft_data();
            if not flight_data or "Latitude" not in flight_data: raise ValueError("Incomplete data.")
            lat,lon,alt=flight_data.get("Latitude"),flight_data.get("Longitude"),int(round(flight_data.get("Altitude",1500)))
            loc_name=geo_utils.reverse_geocode(lat,lon); 
            parts=loc_name.split(', '); simp=[]; seen=set(); country=parts[-1] if parts else ""; state=parts[-2] if len(parts)>1 else None; city=parts[-3] if len(parts)>2 else None
            # Corrected syntax:
            if city and city not in seen: simp.append(city); seen.add(city)
            if state and state not in seen: simp.append(state); seen.add(state)
            if country and country not in seen: simp.append(country); seen.add(country)
            simp_loc = ', '.join(simp) if simp else loc_name; 
            prompt=self._create_tour_guide_prompt(simp_loc, alt)
            sys_msg={"role":"system","content":prompt}; user_q=query if query!="tour request" else "Interesting things?"; user_msg={"role":"user","content":user_q}
            msgs=self.get_conversation_context(); msgs=[sys_msg]+msgs[-(self.context_length-2):]+[user_msg]
            if len(msgs)>self.context_length: msgs=[msgs[0]]+msgs[-(self.context_length-1):]
            response=ai_manager.generate_response(msgs, self.active_api); is_err=any(response.startswith(i) for i in getattr(ai_manager, 'error_indicators', []))
            
            # Corrected Syntax
            speak_ok = False
            if audio_processor: 
                speak_ok = audio_processor.speak(response)

            if speak_ok and not is_err: self.add_to_conversation("assistant", response); audio_processor.speak("More questions?"); next_state=AppState.WAITING; reason="Tour provided"
            elif is_err: reason="AI error tour"
            else: self.logger.error("TTS fail."); reason="TTS fail"
        except Exception as e: self.logger.error(f"Err tour req: {e}",exc_info=True); audio_processor.speak("Error preparing tour.") if audio_processor else None; reason="Tour proc error"
        finally:
             if next_state in [AppState.ACTIVE, AppState.WAITING]:
                  if audio_processor: time.sleep(0.3); audio_processor.start_continuous_listening()
             self.change_state(next_state, reason)

    def _handle_general_question(self, question):
        next_state = AppState.ACTIVE; reason = "Question error"
        try:
            self.logger.info(f"Handling question (thread): '{question[:50]}...'")
            flight_data=sim_server.get_aircraft_data(); loc_ctx=""
            if flight_data:
                lat=flight_data.get("Latitude"); lon=flight_data.get("Longitude"); alt=flight_data.get("Altitude")
                if None not in (lat,lon,alt):
                    try: loc=geo_utils.reverse_geocode(lat,lon); loc_ctx=f"Pilot near {loc} at {alt:.0f} ft. "
                    except Exception as geo_e: self.logger.warning(f"Failed geo ctx: {geo_e}")
            sys_prompt=f"AI flight guide. {loc_ctx}Answer pilot concisely for audio."
            msgs=[{"role":"system","content":sys_prompt}]; hist=list(self.conversation_context); recent=hist[-(self.context_length-1):]; msgs.extend(recent)
            is_redundant=bool(msgs and msgs[-1].get("role")=="user" and msgs[-1].get("content")==question)
            if not is_redundant: msgs.append({"role":"user","content":question})
            if len(msgs)>self.context_length: msgs=[msgs[0]]+msgs[-(self.context_length-1):]
            response=ai_manager.generate_response(msgs, self.active_api); is_err=any(response.startswith(i) for i in getattr(ai_manager, 'error_indicators', []))
            
            # Corrected Syntax
            speak_ok = False
            if audio_processor: 
                speak_ok = audio_processor.speak(response)

            if speak_ok and not is_err: self.add_to_conversation("assistant", response); audio_processor.speak("More questions?"); next_state=AppState.WAITING; reason="Question answered"
            elif is_err: reason="AI error question"
            else: self.logger.error("TTS fail."); reason="TTS fail"
        except Exception as e: self.logger.error(f"Err handling question: {e}",exc_info=True); audio_processor.speak("Trouble processing.") if audio_processor else None; reason="Question error"
        finally:
             if next_state in [AppState.ACTIVE, AppState.WAITING]:
                  if audio_processor: time.sleep(0.3); audio_processor.start_continuous_listening()
             self.change_state(next_state, reason)

    # --- Navigation Callbacks ---
    # Keep as before
    def on_arrival(self, destination):
        with self.state_lock:
             if self.current_state not in [AppState.STANDBY, AppState.ERROR]:
                  if audio_processor: audio_processor.speak(f"Arrived: {destination}!")
                  self.navigation_active=False; self.change_state(AppState.ACTIVE, f"Arrived: {destination}")
                  if audio_processor: time.sleep(0.3); audio_processor.start_continuous_listening() 
             else: self.navigation_active=False
    def on_one_minute_away(self, destination, distance):
         with self.state_lock:
             if self.current_state == AppState.NAVIGATION and self.navigation_active:
                  if audio_processor: audio_processor.speak(f"Approaching {destination}, 1 min.") 
    def on_off_course(self, current_heading, target_heading, difference):
         with self.state_lock:
             if self.current_state == AppState.NAVIGATION and self.navigation_active:
                  correction="right" if ((target_heading-current_heading+360)%360)<180 else "left"
                  if audio_processor: audio_processor.speak(f"Correction: Turn {correction} to {target_heading:.0f} for {self.last_destination}.") 
    def on_update(self, distance, heading, eta):
        self.logger.debug(f"Nav update: Dist={distance:.1f}nm, Hdg={heading:.0f}, ETA={eta:.1f}min"); pass

# --- Singleton Instance (Renamed) ---
manager = StateManager()