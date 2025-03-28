"""
Whisper Flight AI - Main Module
Version: 5.0.26 (Corrected finally block syntax)
Purpose: Core loop for real-time narration and Q&A in MSFS2024
Last Updated: March 28, 2025
Author: Your Name

Changes:
- Fixed SyntaxError in finally block cleanup logic.
- Uses corrected state_manager import/access.
"""

import os
import sys
import time
import logging
import threading
import pygame
from pathlib import Path
import queue 

# --- Imports and Initial Setup ---
try:
    from logging_system import logging_system
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    logging.warning("Could not import logging_system, using basic config.")
    class DummyLogging:
        def log_startup(self): pass
    logging_system = DummyLogging()

from config_manager import config
from audio_processor import audio_processor
from simconnect_server import sim_server
from ai_provider import ai_manager
from geo_utils import geo_utils
from navigation import navigation_manager
import state_manager # Import module
from efb_integration import efb

try:
    logging_system.log_startup()
except AttributeError:
     logging.info("logging_system object missing log_startup method.")

__version__ = config.get("Version", "app_version", "5.0.0")
__copyright__ = config.get("Version", "copyright", f"Copyright (c) {time.strftime('%Y')}. All rights reserved.")

pygame.init()
if not pygame.mixer.get_init():
     try:
         pygame.mixer.init()
         logging.info("Pygame mixer initialized in main.")
     except Exception as pg_err:
         logging.error(f"Failed to initialize pygame.mixer: {pg_err}")

running = True

# --- Mappings and Joystick Init ---
keyboard_mapping = {
    pygame.K_F8: "sky tour", pygame.K_F9: "where am i",
    pygame.K_F10: "question", pygame.K_F11: "deactivate"
}
keyboard_enabled = config.getboolean("Controls", "keyboard_enabled", True)

joystick_enabled = config.getboolean("Controls", "joystick_enabled", True)
joystick_mapping = {
    config.getint("Controls", "sky_tour_button", 2): "sky tour",
    config.getint("Controls", "where_am_i_button", 3): "where am i",
    config.getint("Controls", "question_button", 1): "question",
    config.getint("Controls", "deactivate_button", 0): "deactivate"
}
joystick_device_index = config.getint("Controls", "joystick_device", 0)
joystick = None

def initialize_joystick():
    global joystick
    if joystick_enabled:
        if not pygame.joystick.get_init(): pygame.joystick.init()
        joystick_count = pygame.joystick.get_count()
        logging.info(f"Found {joystick_count} joystick(s).")
        if joystick_count > joystick_device_index:
            try:
                joystick = pygame.joystick.Joystick(joystick_device_index)
                joystick.init()
                logging.info(f"Joystick '{joystick.get_name()}' initialized (Index: {joystick_device_index})")
            except Exception as e:
                logging.error(f"Failed to initialize joystick index {joystick_device_index}: {e}")
                joystick = None
        else:
            logging.warning(f"Joystick device index {joystick_device_index} not found.")
            joystick = None
    else: joystick = None

# --- Main Loop Function ---
def main_event_loop():
    global running, joystick
    initialize_joystick()

    sm = state_manager.manager 
    AppState = state_manager.AppState 
    ap = audio_processor

    if sm and ap:
        logging.info(f"Application ready. Current state: {sm.current_state.name}")
        # --- Banner Print ---
        print(f"""
╔══════════════════════════════════════════════════════════════════╗
║                                                                      ║
║           🛫 WHISPER FLIGHT AI TOUR GUIDE v{__version__} 🛬           ║
║                                                                      ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  🎙️ Say "Sky Tour" to activate                                       ║
║  🗣️ After activation, say "Where am I?" for location information  ║
║  🧭 Ask for directions like "Take me to the Golden Gate Bridge"    ║
║  🔍 Ask open-ended questions about the area you're flying over     ║
║  🛑 Say "Deactivate" to stop the tour                              ║
║                                                                      ║
║  Function Keys and Joystick Buttons:                                 ║
║    F8 / Joystick Button {config.getint("Controls", "sky_tour_button", 2)} - Sky Tour (Activate)                  ║
║    F9 / Joystick Button {config.getint("Controls", "where_am_i_button", 3)} - Where am I?                      ║
║    F10 / Joystick Button {config.getint("Controls", "question_button", 1)} - Ask a question                     ║
║    F11 / Joystick Button {config.getint("Controls", "deactivate_button", 0)} - Deactivate                       ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════╝
""")
        # --- End Banner Print ---
        print("Listening...")
    else:
        logging.critical("StateManager or AudioProcessor not available. Exiting.")
        running = False

    # --- Main Loop ---
    while running:
        command_to_process = None 

        # 1. Handle Pygame Events
        try:
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT: running = False; break
                
                elif event.type == pygame.KEYDOWN and keyboard_enabled:
                    # Optional: Add F8 debug print here if still needed later
                    # if event.key == pygame.K_F8:
                    #    print("DEBUG: F8 key press DETECTED by Pygame.") 
                    if event.key in keyboard_mapping:
                        command = keyboard_mapping[event.key]
                        logging.info(f"Keyboard input: '{command}'")
                        if ap and hasattr(ap, 'audio_queue'): ap.audio_queue.put(command)
                        else: logging.warning("Audio queue N/A.")

                elif event.type == pygame.JOYBUTTONDOWN and joystick:
                    if joystick and joystick.get_init():
                         button = event.button
                         if button in joystick_mapping:
                             command = joystick_mapping[button]
                             logging.info(f"Joystick input: Btn {button} -> '{command}'")
                             if ap and hasattr(ap, 'audio_queue'): ap.audio_queue.put(command)
                             else: logging.warning("Audio queue N/A.")
            if not running: break

            # 2. Get Command from Audio Queue
            if ap: command_to_process = ap.get_next_command(block=False)
            else: logging.error("Audio processor N/A."); time.sleep(1); continue

            # 3. Process Command using StateManager
            if command_to_process:
                logging.info(f"Processing command: '{command_to_process}' in state {sm.current_state.name}")
                try:
                    result = sm.handle_command(command_to_process) 
                    if result is not None: logging.info(f"handle_command result: {result}")
                except Exception as handler_e:
                     logging.error(f"Error during handle_command: {handler_e}", exc_info=True)
                     sm.change_state(AppState.ERROR, f"Exception: {handler_e}") 

            # 4. Brief Sleep
            time.sleep(0.05)

        except Exception as loop_e:
             logging.critical(f"Critical error in main event loop: {loop_e}", exc_info=True)
             running = False
    # --- End Main Loop ---

    # Cleanup (Ensure this happens outside the loop)
    logging.info("Main loop exited. Cleaning up...")
    if ap:
        try: ap.stop_continuous_listening()
        except Exception as e: logging.error(f"Error stopping audio: {e}")
    if sim_server:
        try: sim_server.stop()
        except Exception as e: logging.error(f"Error stopping SimConnect: {e}")
    pygame.quit() 
    logging.info("Application cleanup finished.")

# --- main() and __main__ block ---
def main():
    logging.info("Main function started")
    # Use renamed instance 'manager' for check
    if not config or not ai_manager or not state_manager.manager or not audio_processor or not sim_server:
         logging.critical("Core components failed to initialize. Exiting.")
         return
    logging.info("Core components initialized.")
    main_event_loop()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        running = False # Ensure loop condition is false
        logging.info("Application terminated by user (KeyboardInterrupt)")
    except Exception as e:
        logging.critical(f"Unhandled exception occurred: {e}", exc_info=True)
    finally:
         # --- CORRECTED CLEANUP LOGIC ---
         # This block runs regardless of how the try block exits
         if running: # Should be false if exited normally or via Ctrl+C
             running = False # Ensure it's false if exited via other exception
             
         logging.info("Entering final cleanup...")
         
         # Try stopping audio processor
         if 'ap' in locals() and ap: # Check if ap was defined
             logging.debug("Attempting to stop audio processor in finally block...")
             try: 
                 ap.stop_continuous_listening()
                 logging.info("Audio processor stopped.")
             except Exception as e: 
                 logging.error(f"Error stopping audio processor in finally: {e}")
         else:
              logging.debug("Audio processor 'ap' not defined in finally block.")

         # Try stopping sim server
         if 'sim_server' in locals() and sim_server: # Check if sim_server was defined
             logging.debug("Attempting to stop SimConnect server in finally block...")
             try: 
                 sim_server.stop()
                 logging.info("SimConnect server stopped.")
             except Exception as e: 
                 logging.error(f"Error stopping SimConnect server in finally: {e}")
         else:
              logging.debug("SimConnect server 'sim_server' not defined in finally block.")

         # Ensure Pygame quits
         logging.debug("Attempting to quit Pygame in finally block...")
         pygame.quit()
         logging.info("Pygame quit called.")
         
         logging.info("Exiting application from finally block.")
         # --- END CORRECTION ---