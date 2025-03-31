"""
Whisper Flight AI - Main Module
Version: 5.1.0
Purpose: Core loop for real-time narration and Q&A in MSFS2024
Last Updated: March 31, 2025
Author: Brad Coulter

Changes in v5.1.0:
- Complete architectural overhaul of SimConnect integration
- Implemented robust error recovery and state monitoring
- Added comprehensive diagnostic and status reporting
- Enhanced keyboard and joystick control reliability
- Improved application lifecycle management
"""

import os
import sys
import time
import logging
import threading
import pygame
from typing import Optional, Dict, Any, Callable
from enum import Enum
from pathlib import Path

# Core system imports
from logging_system import logging_system
from config_manager import config
from audio_processor import audio_processor
from ai_provider import ai_manager
from geo_utils import geo_utils
from navigation import navigation_manager
import state_manager
from efb_integration import efb

# SimConnect dynamic loader with advanced error handling
from simconnect_loader import (
    sim_server,
    toggle_simconnect,
    get_connection_info,
    reconnect_if_needed,
    cleanup as simconnect_cleanup,
    is_connection_alive,
)

# Version information
__version__ = "5.1.0"
__build_date__ = "2025-03-31"
__copyright__ = f"Copyright (c) {time.strftime('%Y')}. All rights reserved."


# Application state tracking
class AppStatus(Enum):
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"


# Global state
app_status = AppStatus.STARTING
last_status_change = time.time()
error_count = 0
status_message = "Initializing..."


# Initialize pygame subsystems with error handling
def initialize_pygame() -> bool:
    """Initialize pygame with proper error handling"""
    try:
        pygame.init()
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init()
                logging.info("Pygame mixer initialized successfully.")
                return True
            except Exception as pg_err:
                logging.error(f"Failed to initialize pygame.mixer: {pg_err}")
                return False
        return True
    except Exception as e:
        logging.critical(f"Fatal error initializing pygame: {e}")
        return False


# Application control functions
def set_app_status(status: AppStatus, message: str = "") -> None:
    """Update application status with timestamp and message"""
    global app_status, last_status_change, status_message
    app_status = status
    last_status_change = time.time()
    status_message = message
    logging.info(f"Application status changed to {status.name}: {message}")


# Joystick handling
keyboard_mapping = {
    pygame.K_F8: "sky tour",
    pygame.K_F9: "where am i",
    pygame.K_F10: "question",
    pygame.K_F11: "deactivate",
}

keyboard_enabled = config.getboolean("Controls", "keyboard_enabled", True)
joystick_enabled = config.getboolean("Controls", "joystick_enabled", True)
joystick_mapping = {
    config.getint("Controls", "sky_tour_button", 2): "sky tour",
    config.getint("Controls", "where_am_i_button", 3): "where am i",
    config.getint("Controls", "question_button", 1): "question",
    config.getint("Controls", "deactivate_button", 0): "deactivate",
}
joystick_device_index = config.getint("Controls", "joystick_device", 0)
joystick = None


def initialize_joystick() -> Optional[pygame.joystick.Joystick]:
    """Initialize joystick with proper error handling and reporting"""
    if not joystick_enabled:
        logging.info("Joystick support disabled in configuration")
        return None

    if not pygame.joystick.get_init():
        try:
            pygame.joystick.init()
        except Exception as e:
            logging.error(f"Failed to initialize joystick subsystem: {e}")
            return None

    joystick_count = pygame.joystick.get_count()
    logging.info(f"Found {joystick_count} joystick(s).")

    if joystick_count <= joystick_device_index:
        logging.warning(f"Joystick device index {joystick_device_index} not found.")
        return None

    try:
        joystick = pygame.joystick.Joystick(joystick_device_index)
        joystick.init()
        logging.info(
            f"Joystick '{joystick.get_name()}' initialized (Index: {joystick_device_index})"
        )
        return joystick
    except Exception as e:
        logging.error(
            f"Failed to initialize joystick index {joystick_device_index}: {e}"
        )
        return None


# System monitoring thread
def system_monitor_thread() -> None:
    """Monitor system health and perform recovery as needed"""
    monitor_running = True
    check_interval = 5.0  # seconds between checks

    while monitor_running and app_status != AppStatus.STOPPING:
        try:
            # Check SimConnect connection
            if not reconnect_if_needed():
                logging.warning("SimConnect connection issue detected")

            # Check audio processor health
            if audio_processor and not audio_processor.is_healthy():
                logging.warning(
                    "Audio processor health check failed, attempting recovery"
                )
                try:
                    audio_processor.recover()
                except Exception as e:
                    logging.error(f"Failed to recover audio processor: {e}")

            # Sleep until next check
            time.sleep(check_interval)

        except Exception as e:
            logging.error(f"Error in system monitor thread: {e}")
            time.sleep(check_interval * 2)  # longer interval after error

    logging.info("System monitor thread exiting")


# Display application banner
def display_banner() -> None:
    """Display the application banner with version and controls"""
    # Get SimConnect status
    sim_status = get_connection_info()
    sim_mode = sim_status.get("mode", "Unknown")

    print(
        f"""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║           🛫 WHISPER FLIGHT AI TOUR GUIDE v{__version__} 🛬           ║
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  🎙️ Say "Sky Tour" to activate                                   ║
║  🗣️ After activation, say "Where am I?" for location info       ║
║  🧭 Ask for directions like "Take me to the Golden Gate Bridge" ║
║  🔍 Ask open-ended questions about your surroundings             ║
║  🛑 Say "Deactivate" to stop the tour                            ║
║                                                                  ║
║  Function Keys and Joystick Buttons:                             ║
║    F4 - System Status Report                                     ║
║    F5 - Toggle Quiet Mode                                        ║
║    F6 - Toggle Debug Mode                                        ║
║    F7 - Toggle SimConnect Mode (Currently: {sim_mode})            ║
║    F8 / Joystick {config.getint("Controls", "sky_tour_button", 2)} - Sky Tour                  ║
║    F9 / Joystick {config.getint("Controls", "where_am_i_button", 3)} - Where Am I?              ║
║    F10 / Joystick {config.getint("Controls", "question_button", 1)} - Question                  ║
║    F11 / Joystick {config.getint("Controls", "deactivate_button", 0)} - Deactivate               ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""
    )


# System status reporting
def print_system_status() -> None:
    """Generate and display comprehensive system status"""
    sim_status = get_connection_info()

    print("\n==== WHISPER FLIGHT AI SYSTEM STATUS ====")
    print(f"App Version: {__version__}  |  Status: {app_status.name}")
    print(f"Status Message: {status_message}")
    print(f"Uptime: {int(time.time() - last_status_change)} seconds")

    print("\n-- SimConnect Status --")
    print(f"Mode: {sim_status.get('mode', 'Unknown')}")
    print(f"Connected: {sim_status.get('connected', False)}")
    print(f"Toggle Count: {sim_status.get('toggle_count', 0)}")
    print(f"Last Toggle Success: {sim_status.get('last_toggle_success', False)}")

    if sim_server and hasattr(sim_server, "get_aircraft_data"):
        try:
            aircraft_data = sim_server.get_aircraft_data()
            if aircraft_data:
                print("\n-- Aircraft Data --")
                for key, value in aircraft_data.items():
                    if key in ["Latitude", "Longitude", "Altitude", "Heading"]:
                        print(f"{key}: {value}")
        except Exception as e:
            print(f"Error retrieving aircraft data: {e}")

    print("\n-- Audio System --")
    if audio_processor:
        print(f"Listening: {audio_processor.is_listening()}")
        print(
            f"Queue Size: {audio_processor.get_queue_size() if hasattr(audio_processor, 'get_queue_size') else 'Unknown'}"
        )
    else:
        print("Audio processor not available")

    print("\n-- State Manager --")
    if state_manager and state_manager.manager:
        print(f"Current State: {state_manager.manager.current_state.name}")
    else:
        print("State manager not available")

    print("\n===========================================\n")


# Main event loop
def main_event_loop() -> None:
    """Main application event loop with robust error handling"""
    global joystick, app_status

    # Initialize components
    joystick = initialize_joystick()
    sm = state_manager.manager
    AppState = state_manager.AppState
    ap = audio_processor

    # Start system monitor thread
    monitor_thread = threading.Thread(target=system_monitor_thread, daemon=True)
    monitor_thread.start()

    # Validate core components
    if not sm or not ap:
        logging.critical("StateManager or AudioProcessor not available. Exiting.")
        set_app_status(AppStatus.ERROR, "Critical components missing")
        return

    # Initialize application
    logging.info(f"Application ready. Current state: {sm.current_state.name}")
    display_banner()
    print("Listening...")

    # Start audio processing
    ap.start_continuous_listening()
    set_app_status(AppStatus.RUNNING)

    # Main loop
    while app_status != AppStatus.STOPPING:
        command_to_process = None

        try:
            # Process pygame events
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    set_app_status(AppStatus.STOPPING, "User quit application")
                    break

                # Handle keyboard input
                elif event.type == pygame.KEYDOWN and keyboard_enabled:
                    if event.key == pygame.K_F4:
                        print_system_status()
                    elif event.key == pygame.K_F5:
                        logging.info("F5 pressed - toggling quiet mode")
                        # Toggle appropriate state
                    elif event.key == pygame.K_F6:
                        logging.info("F6 pressed - toggling debug mode")
                        # Toggle appropriate state
                    elif event.key == pygame.K_F7:
                        logging.info("F7 pressed - toggling SimConnect mode")
                        toggle_success = toggle_simconnect()
                        print(
                            f"SimConnect toggle {'successful' if toggle_success else 'failed'}"
                        )
                        # Update status if interface changed
                        if toggle_success:
                            sim_info = get_connection_info()
                            print(
                                f"Now using {sim_info.get('mode', 'Unknown')} SimConnect mode"
                            )
                    elif event.key in keyboard_mapping:
                        command = keyboard_mapping[event.key]
                        logging.info(f"Keyboard input: '{command}'")
                        if ap and hasattr(ap, "audio_queue"):
                            ap.audio_queue.put(command)

                # Handle joystick input
                elif event.type == pygame.JOYBUTTONDOWN and joystick:
                    if joystick and joystick.get_init():
                        button = event.button
                        if button in joystick_mapping:
                            command = joystick_mapping[button]
                            logging.info(f"Joystick input: Btn {button} -> '{command}'")
                            if ap and hasattr(ap, "audio_queue"):
                                ap.audio_queue.put(command)

            # Check if we're stopping
            if app_status == AppStatus.STOPPING:
                break

            # Process audio commands
            if ap:
                try:
                    command_to_process = ap.get_next_command(block=False)
                    if command_to_process:
                        sm.handle_command(command_to_process)
                except Exception as cmd_e:
                    logging.error(f"Error processing command: {cmd_e}")

            # Brief pause to prevent CPU hogging
            time.sleep(0.05)

        except Exception as loop_e:
            logging.critical(
                f"Critical error in main event loop: {loop_e}", exc_info=True
            )
            error_count += 1

            if error_count > 10:
                set_app_status(AppStatus.ERROR, f"Too many errors: {loop_e}")
                break

            # Continue running despite errors
            time.sleep(0.5)

    # Cleanup when loop exits
    logging.info("Main loop exiting. Starting cleanup process...")

    # Stop audio processing
    if ap:
        try:
            ap.stop_continuous_listening()
            logging.info("Audio stopped.")
        except Exception as e:
            logging.error(f"Final audio stop error: {e}")

    # Clean up SimConnect
    try:
        simconnect_cleanup()
        logging.info("SimConnect resources released")
    except Exception as e:
        logging.error(f"SimConnect cleanup error: {e}")

    # Clean up pygame
    pygame.quit()
    logging.info("Pygame resources released")


# Main entry point
def main():
    """Application entry point with comprehensive error handling"""
    logging.info(f"Whisper Flight AI v{__version__} starting up")
    logging_system.log_startup()

    # Initialize pygame
    if not initialize_pygame():
        logging.critical("Failed to initialize pygame. Exiting.")
        return 1

    try:
        # Run main loop
        main_event_loop()
    except KeyboardInterrupt:
        logging.info("Application terminated by user (Ctrl+C)")
    except Exception as e:
        logging.critical(f"Unhandled exception in main: {e}", exc_info=True)
        set_app_status(AppStatus.ERROR, f"Fatal error: {e}")
        return 1

    logging.info(f"Whisper Flight AI v{__version__} shutdown complete")
    return 0


# Script entry point
if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
