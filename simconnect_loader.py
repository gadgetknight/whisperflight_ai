"""
Whisper Flight AI - SimConnect Loader
Version: 1.1.6
Purpose: Dynamically loads real SimConnect or falls back to mock
Last Updated: March 31, 2025
Author: Whisper Flight AI Team

Changes in v1.1.6:
- Added module-level flag to track current SimConnect mode
- Implemented notification system for mode changes
- Enhanced error handling and recovery logic
- Fixed conflicts with direct imports in other modules
"""

import logging
import sys
import time

logger = logging.getLogger("SimConnectLoader")

sim_server = None
_sim_mode = "Unknown"
_toggle_count = 0
_last_toggle_success = False

_real_server_loaded = False
_mock_server_loaded = False

# Add a module flag to track if we're using real or mock
USING_REAL_SIMCONNECT = False

# Callback registry for mode change notifications
_mode_change_callbacks = []


def register_mode_change_callback(callback):
    """Register a callback function to be called when SimConnect mode changes"""
    if callable(callback) and callback not in _mode_change_callbacks:
        _mode_change_callbacks.append(callback)
        return True
    return False


def _notify_mode_change(new_mode):
    """Notify all registered callbacks about mode change"""
    for callback in _mode_change_callbacks:
        try:
            callback(new_mode)
        except Exception as e:
            logger.error(f"Error in mode change callback: {e}")


def load_simconnect():
    """Load the appropriate SimConnect implementation"""
    global sim_server, _sim_mode, _real_server_loaded, _mock_server_loaded, USING_REAL_SIMCONNECT

    print("\n[DEBUG] Trying real SimConnect...")
    try:
        from simconnect_server import sim_server as real_server

        print("[DEBUG] Successfully imported simconnect_server.")
        try:
            test_data = real_server.get_aircraft_data()
            print(f"[DEBUG] real_server.get_aircraft_data() returned: {test_data}")
        except Exception as e:
            print(f"[DEBUG] Exception while calling get_aircraft_data(): {e}")
            test_data = None

        if test_data is None:
            print("[DEBUG] test_data is None. Real SimConnect is not responding.")
        elif not isinstance(test_data, dict):
            print(f"[DEBUG] test_data is not a dict: {type(test_data)}")
        elif "Latitude" not in test_data or "Longitude" not in test_data:
            print("[DEBUG] test_data missing required keys: Latitude and/or Longitude")
        else:
            print("[DEBUG] ✅ Real SimConnect passed all checks — using it.")
            sim_server = real_server
            _sim_mode = "Real"
            _real_server_loaded = True
            USING_REAL_SIMCONNECT = True
            _notify_mode_change("Real")
            return

    except Exception as e:
        print(f"[DEBUG] Failed to import or connect to real SimConnect: {e}")

    # Fallback
    print("[DEBUG] Falling back to mock SimConnect server...")
    try:
        from mock_simconnect_server import sim_server as mock_server

        sim_server = mock_server
        _sim_mode = "Mock"
        _mock_server_loaded = True
        USING_REAL_SIMCONNECT = False
        print("[DEBUG] ✅ Mock SimConnect is now active.")
        _notify_mode_change("Mock")
    except Exception as e:
        print(f"[DEBUG] ❌ Failed to load mock SimConnect: {e}")
        sim_server = None
        _sim_mode = "None"
        _notify_mode_change("None")


# Load at import
load_simconnect()


def toggle_simconnect():
    """Toggle between real and mock SimConnect"""
    global sim_server, _sim_mode, _toggle_count, _last_toggle_success, USING_REAL_SIMCONNECT

    _toggle_count += 1
    _last_toggle_success = False

    try:
        if _sim_mode == "Real":
            # Switch to mock
            from mock_simconnect_server import sim_server as mock_server

            sim_server = mock_server
            _sim_mode = "Mock"
            USING_REAL_SIMCONNECT = False
            _notify_mode_change("Mock")
        else:
            # Try to switch to real
            from simconnect_server import sim_server as real_server

            # Test if real server is working
            test_data = real_server.get_aircraft_data()
            print(f"[DEBUG] Toggle check returned: {test_data}")

            if (
                test_data
                and isinstance(test_data, dict)
                and "Latitude" in test_data
                and "Longitude" in test_data
            ):
                sim_server = real_server
                _sim_mode = "Real"
                USING_REAL_SIMCONNECT = True
                _notify_mode_change("Real")
            else:
                print(
                    "[DEBUG] Toggle: real SimConnect returned invalid data. Staying in mock."
                )
                return False

        _last_toggle_success = True
        print(f"[DEBUG] SimConnect toggled to {_sim_mode}")
        return True
    except Exception as e:
        print(f"[DEBUG] Toggle failed: {e}")
        return False


def get_connection_info():
    """Get information about the current SimConnect connection"""
    return {
        "mode": _sim_mode,
        "connected": sim_server is not None,
        "toggle_count": _toggle_count,
        "last_toggle_success": _last_toggle_success,
        "using_real": USING_REAL_SIMCONNECT,
    }


def reconnect_if_needed():
    """Check connection and reconnect if needed"""
    global sim_server

    if sim_server is None:
        print("[DEBUG] SimConnect server is None, attempting to reload")
        load_simconnect()
        return sim_server is not None

    try:
        # Try to get data to verify connection
        data = sim_server.get_aircraft_data()
        if data is None:
            print("[DEBUG] SimConnect returned None data, attempting to reload")
            load_simconnect()
    except Exception as e:
        print(f"[DEBUG] SimConnect error: {e}, attempting to reload")
        load_simconnect()

    return sim_server is not None


def cleanup():
    """Clean up SimConnect resources"""
    global sim_server

    try:
        if sim_server and hasattr(sim_server, "stop"):
            sim_server.stop()
            print("[DEBUG] SimConnect server stopped.")
            sim_server = None
    except Exception as e:
        print(f"[DEBUG] Cleanup error: {e}")


def is_connection_alive():
    """Check if the SimConnect connection is alive"""
    try:
        if sim_server and hasattr(sim_server, "get_aircraft_data"):
            data = sim_server.get_aircraft_data()
            return data is not None
    except Exception:
        return False
    return False


def get_sim_server():
    """Returns the current active SimConnect server instance"""
    return sim_server


def is_using_real_simconnect():
    """Returns True if using real SimConnect, False if using mock"""
    return USING_REAL_SIMCONNECT
