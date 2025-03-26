"""
Whisper Flight AI - Main Module
Version: 5.0.16
Purpose: Core loop for real-time narration and Q&A in MSFS2024
Last Updated: March 25, 2025
Author: Your Name

Changes in this version:
- Removed Pygame display window (lines 54-58 removed)
- Retained event dumping from v5.0.15 (lines 95-97)
- Kept debug log and 'Listening...' from v5.0.14 (lines 116-117, 90)
"""

import os
import sys
import time
import logging
import threading
import pygame
from pathlib import Path

try:
    from logging_system import logging_system
except ImportError:
    import logging_system
    logging_system = logging_system.logging_system
    print("Fallback import used for logging_system")

from config_manager import config
from audio_processor import audio_processor
from simconnect_server import sim_server
from ai_provider import ai_manager
from geo_utils import geo_utils
from navigation import navigation_manager
from state_manager import state_manager, AppState
from efb_integration import efb

logging_system.log_startup()

__version__ = config.get("Version", "app_version", "5.1.6")
__copyright__ = config.get("Version", "copyright", f"Copyright © {time.strftime('%Y')}. All rights reserved.")

pygame.init()  # Initialize Pygame without display

running = True
keyboard_mapping = {
    pygame.K_F8: "sky tour",
    pygame.K_F9: "where am i",
    pygame.K_F10: "question",
    pygame.K_F11: "deactivate"
}

joystick_enabled = config.getboolean("Controls", "joystick_enabled", True)
joystick_mapping = {
    2: "sky tour",      # Button 2 for Sky Tour
    3: "where am i",    # Button 3 for Where am I?
    1: "question",      # Button 1 for Ask a question
    0: "deactivate"     # Button 0 for Deactivate
}

def microphone_event_listener():
    """Listen for audio, keyboard, and joystick events and handle them according to current state."""
    global running
    pygame.mixer.init()
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║              🛫 WHISPER FLIGHT AI TOUR GUIDE v{__version__} 🛬             ║
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  🎙️ Say "Sky Tour" to activate                                   ║
║  🗣️ After activation, say "Where am I?" for location information  ║
║  🧭 Ask for directions like "Take me to the Golden Gate Bridge"   ║
║  🔍 Ask open-ended questions about the area you're flying over    ║
║  🛑 Say "Deactivate" to stop the tour                             ║
║                                                                  ║
║  Function Keys and Joystick Buttons:                             ║
║    F8 / Joystick Button 2 - Sky Tour (Activate)                  ║
║    F9 / Joystick Button 3 - Where am I?                          ║
║    F10 / Joystick Button 1 - Ask a question                      ║
║    F11 / Joystick Button 0 - Deactivate                          ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""")
    print("Listening...")
    logging.info("Starting continuous listening")
    audio_processor.start_continuous_listening()
    logging.info("Continuous listening started")
    joystick = None
    if joystick_enabled and pygame.joystick.get_count() > 0:
        joystick = pygame.joystick.Joystick(config.getint("Controls", "joystick_device", 0))
        joystick.init()
        logging.info(f"Joystick '{joystick.get_name()}' initialized")
    while running:
        logging.info("Entering event loop cycle")
        events = pygame.event.get()
        if events:
            logging.info(f"Pygame events: {[event.type for event in events]}")
        for event in events:
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and config.getboolean("Controls", "keyboard_enabled", True):
                if event.key in keyboard_mapping:
                    command = keyboard_mapping[event.key]
                    logging.info(f"Keyboard input detected: {command}")
                    audio_processor.audio_queue.put(command)
            elif event.type == pygame.JOYBUTTONDOWN and joystick:
                button = event.button
                if button in joystick_mapping:
                    command = joystick_mapping[button]
                    logging.info(f"Joystick input detected: {command}")
                    audio_processor.audio_queue.put(command)
        command = audio_processor.get_next_command(block=False)
        if command:
            logging.info(f"Processing input: {command}")
            result = state_manager.handle_command(command)
            logging.info(f"handle_command result: {result}")
        time.sleep(0.05)
    audio_processor.stop_continuous_listening()
    sim_server.stop()
    pygame.quit()

def joystick_monitor():
    """Separate thread for joystick initialization (no event polling)."""
    if not joystick_enabled or pygame.joystick.get_count() == 0:
        return
    pygame.joystick.init()
    joystick = pygame.joystick.Joystick(config.getint("Controls", "joystick_device", 0))
    joystick.init()
    logging.info("Joystick thread started")
    while running:
        time.sleep(0.05)

def main():
    logging.info("Main loop started")
    logging.info("Initializing SimConnect server")
    sim_server
    logging.info("Initializing AI manager")
    ai_manager
    logging.info("Initializing state manager")
    state_manager
    joystick_thread = threading.Thread(target=joystick_monitor, daemon=True)
    joystick_thread.start()
    microphone_event_listener()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        running = False
        logging.info("Application terminated by user")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        raise