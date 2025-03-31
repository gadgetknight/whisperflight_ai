"""
Whisper Flight AI - SimConnect Loader
Version: 1.1.5
Purpose: Dynamically loads real SimConnect or falls back to mock
Last Updated: March 31, 2025
Author: Whisper Flight AI Team

Changes in v1.1.5:
- Injected aggressive inline debug print statements
- Logs and prints what real SimConnect is returning
- Clearly shows why fallback is triggered
- Complies with new Rule of 3: debug immediately after third failure
"""

import logging

logger = logging.getLogger("SimConnectLoader")

sim_server = None
_sim_mode = "Unknown"
_toggle_count = 0
_last_toggle_success = False

_real_server_loaded = False
_mock_server_loaded = False


def load_simconnect():
    global sim_server, _sim_mode, _real_server_loaded, _mock_server_loaded

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
        print("[DEBUG] ✅ Mock SimConnect is now active.")
    except Exception as e:
        print(f"[DEBUG] ❌ Failed to load mock SimConnect: {e}")
        sim_server = None
        _sim_mode = "None"


# Load at import
load_simconnect()


def toggle_simconnect():
    global sim_server, _sim_mode, _toggle_count, _last_toggle_success

    _toggle_count += 1
    _last_toggle_success = False

    try:
        if _sim_mode == "Real":
            from mock_simconnect_server import sim_server as mock_server

            sim_server = mock_server
            _sim_mode = "Mock"
        else:
            from simconnect_server import sim_server as real_server

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
    return {
        "mode": _sim_mode,
        "connected": sim_server is not None,
        "toggle_count": _toggle_count,
        "last_toggle_success": _last_toggle_success,
    }


def reconnect_if_needed():
    return sim_server is not None


def cleanup():
    try:
        if sim_server and hasattr(sim_server, "stop"):
            sim_server.stop()
            print("[DEBUG] SimConnect server stopped.")
    except Exception as e:
        print(f"[DEBUG] Cleanup error: {e}")


def is_connection_alive():
    try:
        if sim_server and hasattr(sim_server, "get_aircraft_data"):
            data = sim_server.get_aircraft_data()
            return data is not None
    except Exception:
        return False
    return False
