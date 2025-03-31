"""
Whisper Flight AI - SimConnect Loader
Version: 1.1.0
Purpose: Dynamically load real or mock SimConnect server with runtime toggling
Last Updated: March 31, 2025
Author: Brad Coulter

Changes in v1.1.0:
- Enhanced error handling and recovery mechanisms
- Added connection monitoring and health checks
- Implemented robust toggle state management
- Added diagnostic and reporting functions
- Improved resource management and cleanup
"""

import logging
import importlib
import time
import threading
from typing import Tuple, Dict, Any, Optional, Callable
from functools import wraps

# Constants
REAL_SIMCONNECT_MODULE = "simconnect_server"
MOCK_SIMCONNECT_MODULE = "mock_simconnect_server"
TOGGLE_COOLDOWN = 3.0  # seconds between allowed toggles
CONNECTION_CHECK_INTERVAL = 15.0  # seconds between connection health checks
MAX_RECONNECT_ATTEMPTS = 3  # maximum consecutive reconnection attempts

# Module state
_current_server = None
_is_mock_mode = True
_connection_attempts = 0
_toggle_attempts = 0
_last_toggle_time = 0
_toggle_success = False
_last_error = ""
_monitor_thread = None
_monitoring_active = False
_heartbeat_timestamp = 0
_reconnect_failures = 0

# Lock for thread-safe operations
_lock = threading.RLock()


# Decorators for thread safety
def synchronized(func: Callable) -> Callable:
    """Thread-safety decorator for functions that modify module state"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        with _lock:
            return func(*args, **kwargs)

    return wrapper


# Core SimConnect interface functions
@synchronized
def _try_real_simconnect() -> Tuple[Any, bool]:
    """Attempt to load and validate real SimConnect server"""
    global _last_error, _connection_attempts
    _connection_attempts += 1

    try:
        logging.info("Attempting to connect to real MSFS SimConnect...")
        simconnect_module = importlib.import_module(REAL_SIMCONNECT_MODULE)
        server = simconnect_module.sim_server

        # Validate connection by retrieving aircraft data
        start_time = time.time()
        data = server.get_aircraft_data()
        response_time = time.time() - start_time

        if data and isinstance(data, dict) and "Latitude" in data:
            logging.info(
                f"Real SimConnect connected successfully (response time: {response_time:.3f}s)"
            )
            _last_error = ""
            return server, False
        else:
            _last_error = "Real SimConnect returned invalid data format"
            logging.warning(_last_error)
            return None, True

    except ImportError as ie:
        _last_error = f"Real SimConnect module not found: {ie}"
        logging.warning(_last_error)
        return None, True
    except Exception as e:
        _last_error = f"Real SimConnect connection failed: {e}"
        logging.warning(_last_error)
        return None, True


@synchronized
def _try_mock_simconnect() -> Tuple[Any, bool]:
    """Load mock SimConnect server with validation"""
    global _last_error, _connection_attempts
    _connection_attempts += 1

    try:
        logging.info("Loading mock SimConnect server...")
        mock_module = importlib.import_module(MOCK_SIMCONNECT_MODULE)
        server = mock_module.sim_server

        # Validate mock server has required methods
        required_methods = ["get_aircraft_data", "get_nearby_poi", "stop"]
        for method in required_methods:
            if not hasattr(server, method):
                _last_error = f"Mock SimConnect missing required method: {method}"
                logging.error(_last_error)
                return None, True

        # Test mock data retrieval
        data = server.get_aircraft_data()
        if not data or not isinstance(data, dict):
            _last_error = "Mock SimConnect returned invalid data"
            logging.error(_last_error)
            return None, True

        logging.info("Mock SimConnect initialized successfully")
        _last_error = ""
        return server, True

    except ImportError as ie:
        _last_error = f"Mock SimConnect module not found: {ie}"
        logging.error(_last_error)
        return None, True
    except Exception as e:
        _last_error = f"Mock SimConnect initialization error: {e}"
        logging.error(_last_error)
        return None, True


@synchronized
def _initialize_simconnect() -> bool:
    """Initialize SimConnect with fallback logic"""
    global _current_server, _is_mock_mode, _heartbeat_timestamp, _reconnect_failures

    # Try real SimConnect first (preferred)
    _current_server, _is_mock_mode = _try_real_simconnect()

    # Fall back to mock if real fails
    if not _current_server:
        _current_server, _is_mock_mode = _try_mock_simconnect()

    success = _current_server is not None

    if success:
        _heartbeat_timestamp = time.time()
        _reconnect_failures = 0
        logging.info(
            f"SimConnect initialized: {'Mock' if _is_mock_mode else 'Real'} mode"
        )
    else:
        logging.critical("FAILED TO INITIALIZE ANY SIMCONNECT SERVER")

    return success


# Toggle function with cooldown and state management
@synchronized
def toggle_simconnect() -> bool:
    """
    Toggle between real and mock SimConnect implementations

    Returns:
        bool: True if toggle was successful, False otherwise
    """
    global _current_server, _is_mock_mode, _toggle_attempts
    global _last_toggle_time, _toggle_success, _last_error

    current_time = time.time()

    # Enforce cooldown period
    if current_time - _last_toggle_time < TOGGLE_COOLDOWN:
        _last_error = (
            f"Toggle attempted too quickly. Please wait {TOGGLE_COOLDOWN} seconds."
        )
        logging.warning(_last_error)
        return False

    _last_toggle_time = current_time
    _toggle_attempts += 1
    previous_mode = _is_mock_mode

    # Attempt to toggle
    logging.info(
        f"Toggling SimConnect from {'Mock' if _is_mock_mode else 'Real'} mode..."
    )

    # Clean up existing server if needed
    if _current_server and hasattr(_current_server, "stop"):
        try:
            _current_server.stop()
            logging.info("Previous SimConnect connection closed")
        except Exception as e:
            logging.warning(f"Error closing previous SimConnect connection: {e}")

    # Try to connect to the alternate server type
    if _is_mock_mode:
        # Currently mock, try to switch to real
        _current_server, _is_mock_mode = _try_real_simconnect()
        if not _current_server:
            # Failed to connect to real, stay with mock
            logging.warning("Failed to connect to real SimConnect. Staying with mock.")
            _current_server, _is_mock_mode = _try_mock_simconnect()
    else:
        # Currently real, switch to mock
        _current_server, _is_mock_mode = _try_mock_simconnect()

    # Determine if toggle was successful
    _toggle_success = (previous_mode != _is_mock_mode) or (_current_server is not None)

    if _toggle_success:
        mode_name = "Mock" if _is_mock_mode else "Real"
        logging.info(f"SimConnect toggled to {mode_name} mode successfully")
    else:
        logging.error(f"Failed to toggle SimConnect: {_last_error}")

    return _toggle_success


# Connection monitoring functions
def is_connection_alive() -> bool:
    """
    Check if the current SimConnect connection is working properly

    Returns:
        bool: True if connection is healthy, False otherwise
    """
    if not _current_server:
        return False

    try:
        data = _current_server.get_aircraft_data()
        return data is not None and isinstance(data, dict)
    except Exception as e:
        logging.error(f"Connection check failed: {e}")
        return False


@synchronized
def reconnect_if_needed() -> bool:
    """
    Attempt to reconnect if connection is lost

    Returns:
        bool: True if connection is now working, False otherwise
    """
    global _current_server, _is_mock_mode, _reconnect_failures

    # Check if connection is still alive
    if is_connection_alive():
        _reconnect_failures = 0
        return True

    _reconnect_failures += 1
    logging.warning(
        f"SimConnect connection lost. Attempting to reconnect (attempt {_reconnect_failures})..."
    )

    # Try to reconnect with same type first
    if _is_mock_mode:
        _current_server, _ = _try_mock_simconnect()
    else:
        _current_server, _ = _try_real_simconnect()

    # If reconnect with same type failed, and we've tried a few times, switch to alternate
    if not _current_server and _reconnect_failures >= MAX_RECONNECT_ATTEMPTS:
        if _is_mock_mode:
            logging.warning(
                "Multiple mock reconnect failures. Trying real SimConnect..."
            )
            _current_server, _is_mock_mode = _try_real_simconnect()
        else:
            logging.warning("Multiple real reconnect failures. Falling back to mock...")
            _current_server, _is_mock_mode = _try_mock_simconnect()

    success = _current_server is not None
    if success:
        _reconnect_failures = 0
        logging.info(f"Reconnected to {'Mock' if _is_mock_mode else 'Real'} SimConnect")
    else:
        logging.error("Failed to reconnect to any SimConnect server")

    return success


# Monitor thread function
def _connection_monitor() -> None:
    """Thread function to monitor connection health and perform recovery"""
    global _monitoring_active, _heartbeat_timestamp

    logging.info("Connection monitor thread started")

    while _monitoring_active:
        try:
            # Check connection health periodically
            if _current_server and not is_connection_alive():
                reconnect_if_needed()

            # Update heartbeat timestamp if connection is good
            if _current_server and is_connection_alive():
                _heartbeat_timestamp = time.time()

            # Sleep until next check
            time.sleep(CONNECTION_CHECK_INTERVAL)
        except Exception as e:
            logging.error(f"Error in connection monitor thread: {e}")
            time.sleep(CONNECTION_CHECK_INTERVAL * 2)  # Longer sleep after error

    logging.info("Connection monitor thread exiting")


# Start the monitoring thread
def start_monitoring() -> None:
    """Start the background connection monitoring thread"""
    global _monitor_thread, _monitoring_active

    if _monitor_thread and _monitor_thread.is_alive():
        logging.warning("Monitor thread already running")
        return

    _monitoring_active = True
    _monitor_thread = threading.Thread(target=_connection_monitor, daemon=True)
    _monitor_thread.start()
    logging.info("Connection monitoring started")


# Stop the monitoring thread
def stop_monitoring() -> None:
    """Stop the background connection monitoring thread"""
    global _monitoring_active

    _monitoring_active = False
    logging.info("Connection monitoring stopped")


# Resource cleanup function
@synchronized
def cleanup() -> None:
    """Properly clean up all SimConnect resources"""
    global _current_server, _monitoring_active

    # Stop monitoring
    _monitoring_active = False

    # Clean up server
    if _current_server:
        try:
            if hasattr(_current_server, "stop") and callable(_current_server.stop):
                _current_server.stop()
                logging.info("SimConnect resources released")
        except Exception as e:
            logging.error(f"Error during SimConnect cleanup: {e}")

    _current_server = None


# Diagnostic functions
def get_connection_info() -> Dict[str, Any]:
    """
    Get diagnostic information about the current connection

    Returns:
        dict: Detailed connection status and statistics
    """
    return {
        "mode": "Mock" if _is_mock_mode else "Real",
        "connected": is_connection_alive(),
        "connection_attempts": _connection_attempts,
        "toggle_attempts": _toggle_attempts,
        "toggle_count": _toggle_attempts,
        "last_toggle_success": _toggle_success,
        "last_error": _last_error,
        "uptime": time.time() - _heartbeat_timestamp if _heartbeat_timestamp > 0 else 0,
        "reconnect_failures": _reconnect_failures,
    }


# Initialize on module load
_initialize_simconnect()
start_monitoring()


# Create a proxy class for SimConnect method forwarding
class SimConnectProxy:
    """
    Proxy class to provide safe access to SimConnect methods

    This handles cases where the underlying server might be None
    or might not have the requested method.
    """

    def __getattr__(self, name):
        """Forward method calls to the current server with error handling"""
        if _current_server is None:
            logging.error(f"SimConnect not initialized when accessing {name}")
            # Return dummy function that does nothing
            return lambda *args, **kwargs: None

        if not hasattr(_current_server, name):
            logging.error(
                f"Method {name} not available in current SimConnect implementation"
            )
            return lambda *args, **kwargs: None

        return getattr(_current_server, name)


# Create proxy for external use
sim_server = SimConnectProxy()

# Module exports
__all__ = [
    "sim_server",
    "toggle_simconnect",
    "get_connection_info",
    "reconnect_if_needed",
    "cleanup",
    "is_connection_alive",
    "start_monitoring",
    "stop_monitoring",
]
